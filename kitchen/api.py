"""The API the phone app talks to. Every view takes and returns JSON.

Two groups:
  * accounts and family data: sign-in, sync, family code, voting, download/delete my data
  * the "brain": the screens send what they know (kitchen, family, diary) and Python does the thinking
"""
import functools
import json
import logging
import re
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie

from . import ai, assistant, catalog, engine, planner, retention
from .models import AiUsage, ChatThread, FamilyData, Household, Poll, Profile, Vote
from .security import ApiError, auth_config, check_code, clear_limit, client_ip, limited, request_code

log = logging.getLogger('kitchen')
SMALL, STATE, PHOTO = 200 * 1024, 1024 * 1024, 8 * 1024 * 1024
CONSENT_ERROR = "Please agree to how Ballava stores your family's food and health details."


# ---------------------------------------------------------------- plumbing
def endpoint(methods=('POST',), limit=SMALL):
    """Turns a function(request, body) into a JSON API view with friendly errors."""
    def wrap(fn):
        @functools.wraps(fn)
        def view(request, *args, **kwargs):
            if request.method not in methods:
                return JsonResponse({'error': 'Use ' + ' or '.join(methods)}, status=405)
            try:
                body = {}
                if request.method == 'POST':
                    if len(request.body) > limit:
                        raise ApiError(413, 'Request too large')
                    try:
                        body = json.loads(request.body or b'{}')
                    except ValueError:
                        raise ApiError(400, 'Invalid JSON') from None
                    if not isinstance(body, dict):
                        raise ApiError(400, 'Invalid JSON')
                result = fn(request, body, *args, **kwargs)
                return JsonResponse(result, safe=False)
            except ApiError as err:
                return JsonResponse(err.payload or {'error': err.message}, status=err.status)
            except ValueError as err:
                return JsonResponse({'error': str(err) or 'Something was not right with that request.'}, status=400)
            except Exception:  # noqa: BLE001  never show internals to the user
                log.exception('API error on %s', request.path)
                return JsonResponse({'error': 'Something went wrong on the server.'}, status=500)
        # Every API response also hands the browser its CSRF cookie, which it sends back on changes.
        return ensure_csrf_cookie(view)
    return wrap


def app_user(request):
    """The signed-in family user, or None. Admin logins are kept out of the family app."""
    user = request.user
    if not user.is_authenticated or user.is_staff or not hasattr(user, 'profile'):
        return None
    return user


def require_user(request):
    user = app_user(request)
    if not user:
        raise ApiError(401, 'Please sign in first.')
    return user


def clean_name(value):
    return str(value or '').strip()[:60]


def public_user(user):
    return {'id': str(user.pk), 'name': user.first_name, 'email': user.email or None, 'phone': user.profile.phone, 'role': 'user'}


def household_info(user):
    h = user.profile.household
    if not h:
        return None
    people = list(h.people.order_by('user__date_joined').values_list('user__first_name', flat=True))
    return {'id': str(h.pk), 'name': h.name, 'inviteCode': h.invite_code, 'people': people}


def new_family_user(name, *, email=None, phone=None, password=None):
    username = email or f'phone:{phone}'
    user = User(username=username, email=email or '', first_name=name)
    if password:
        user.set_password(password)
    else:
        user.set_unusable_password()
    user.save()
    household = Household.objects.create(name=f"{name}'s family")
    Profile.objects.create(user=user, household=household, phone=phone, consent_at=timezone.now())
    return user


# ---------------------------------------------------------------- basics
@endpoint(methods=('GET',))
def health(request, body):
    on = bool(ai.ai_key())
    return {'ok': True, 'ai': on, 'aiProvider': ai.provider_label() if on else None, 'retentionDays': retention.days(),
            'catalog': catalog.stamp(), 'version': '2.3.0'}  # `catalog` changes whenever admins change something


@endpoint(methods=('GET',))
def catalog_view(request, body):
    return catalog.public_catalog()


@endpoint(methods=('GET',))
def config_view(request, body):
    return auth_config()


# ---------------------------------------------------------------- sign-in
@endpoint()
def signup(request, body):
    ip = client_ip(request)
    if limited('signup:' + ip, settings.SIGNUP_RATE_LIMIT, 3600):
        raise ApiError(429, 'Too many sign-ups from here. Please try again later.')
    name = clean_name(body.get('name'))
    email = str(body.get('email') or '').strip().lower()
    password = str(body.get('password') or '')
    if not name:
        raise ApiError(400, 'Please enter your name.')
    try:
        from django.core.validators import validate_email
        validate_email(email)
    except ValidationError:
        raise ApiError(400, 'Please enter a valid email address.') from None
    if len(password) > 200:
        raise ApiError(400, 'That password is too long.')
    try:
        validate_password(password, User(username=email, email=email, first_name=name))
    except ValidationError as err:
        raise ApiError(400, ' '.join(err.messages)) from None
    if not body.get('consent'):
        raise ApiError(400, CONSENT_ERROR)
    if User.objects.filter(username=email).exists():
        raise ApiError(409, 'An account with this email already exists. Please sign in.')
    user = new_family_user(name, email=email, password=password)
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return {'user': public_user(user), 'isNew': True}


@endpoint()
def login_view(request, body):
    email = str(body.get('email') or '').strip().lower()
    key = f'login:{email}:{client_ip(request)}'
    if limited(key, 6, 900):
        raise ApiError(429, 'Too many tries. Please wait 15 minutes and try again.')
    user = authenticate(request, username=email, password=str(body.get('password') or ''))
    if not user or user.is_staff or not hasattr(user, 'profile'):
        raise ApiError(401, 'That email or password is not right.')
    clear_limit(key)
    login(request, user)
    return {'user': public_user(user)}


@endpoint()
def otp_request(request, body):
    return request_code(body.get('phone'), client_ip(request))


@endpoint()
def otp_verify(request, body):
    phone = check_code(body.get('phone'), body.get('code'))
    profile = Profile.objects.select_related('user').filter(phone=phone).first()
    if profile and (not profile.user.is_active or profile.user.is_staff):
        raise ApiError(403, 'This account cannot sign in here.')
    is_new = profile is None
    if is_new:
        if not body.get('consent'):
            raise ApiError(400, CONSENT_ERROR)
        name = clean_name(body.get('name'))
        if not name:
            raise ApiError(400, 'Please enter your name.')
        user = new_family_user(name, phone=phone)
    else:
        user = profile.user
    from .models import PhoneCode
    PhoneCode.objects.filter(phone=phone).delete()
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return {'user': public_user(user), 'isNew': is_new}


@endpoint()
def logout_view(request, body):
    if app_user(request):
        logout(request)
    return {'ok': True}


@endpoint(methods=('GET',))
def me(request, body):
    retention.maybe_cleanup()  # once a day: remove what's older than 6 months
    user = app_user(request)
    if not user:
        return {'user': None}
    Profile.objects.filter(pk=user.profile.pk).update(last_seen=timezone.now())
    return {'user': public_user(user), 'household': household_info(user)}


# ---------------------------------------------------------------- family data
def read_state(user):
    return {'items': {row.key: {'value': row.value, 'version': row.version} for row in FamilyData.objects.filter(household=user.profile.household)}}


@endpoint(methods=('GET', 'POST'), limit=STATE)
def state(request, body):
    """GET: all of the family's data. POST {key, value, baseVersion}: save one piece.
    If someone else saved first, the answer is 409 with the latest copy, so the phone can merge and retry."""
    user = require_user(request)
    if request.method == 'GET':
        return read_state(user)
    key, value, base = body.get('key'), body.get('value'), body.get('baseVersion', 0)
    if key not in FamilyData.KEYS:
        raise ApiError(400, 'Unknown data type.')
    if value is None:
        raise ApiError(400, 'Nothing to save.')
    # Anything older than 6 months is never stored again, even if an old phone still has it.
    saved_ids = None
    if key == 'aiRecipes':
        saved = FamilyData.objects.filter(household=user.profile.household, key='savedDishes').values_list('value', flat=True).first()
        saved_ids = {s.get('id') for s in (saved or []) if isinstance(s, dict)}
    value = retention.prune_value(key, value, saved_ids=saved_ids)
    with transaction.atomic():
        row = FamilyData.objects.select_for_update().filter(household=user.profile.household, key=key).first()
        current = row.version if row else 0
        if current != base:
            raise ApiError(409, 'Someone else updated this.', {'error': 'Someone else updated this.', 'value': row.value if row else None, 'version': current})
        if row:
            row.value, row.version = value, current + 1
            row.save()
        else:
            row = FamilyData.objects.create(household=user.profile.household, key=key, value=value, version=1)
    return {'version': row.version}


def _leave_household(user):
    """Returns the household to delete if this user was the last one in it."""
    h = user.profile.household
    return h if h and not h.people.exclude(pk=user.profile.pk).exists() else None


@endpoint()
def join_household(request, body):
    user = require_user(request)
    if limited('join:' + client_ip(request), 15, 3600):
        raise ApiError(429, 'Too many tries. Please try again later.')
    target = Household.objects.filter(invite_code=str(body.get('code') or '').strip().upper()).first()
    if not target:
        raise ApiError(404, 'That family code is not right.')
    if target != user.profile.household:
        with transaction.atomic():
            orphan = _leave_household(user)
            Profile.objects.filter(pk=user.profile.pk).update(household=target)
            if orphan:
                orphan.delete()
    return {'ok': True}


@endpoint()
def rename_household(request, body):
    user = require_user(request)
    name = clean_name(body.get('name'))
    if not name:
        raise ApiError(400, 'Please enter a name.')
    Household.objects.filter(pk=user.profile.household_id).update(name=name)
    return {'ok': True}


@endpoint(methods=('GET',))
def export_account(request, body):
    user = require_user(request)
    polls = list(Poll.objects.filter(household=user.profile.household).values('title', 'date', 'slot', 'options'))
    return {'exportedAt': timezone.now().isoformat(), 'account': public_user(user), 'household': household_info(user),
            'data': read_state(user)['items'], 'polls': polls, 'chats': [chat_json(t) for t in user.chats.all()]}


@endpoint()
def delete_account(request, body):
    user = require_user(request)
    if body.get('confirm') != 'DELETE':
        raise ApiError(400, 'Please type DELETE to confirm.')
    with transaction.atomic():
        orphan = _leave_household(user)
        logout(request)
        user.delete()
        if orphan:
            orphan.delete()
    return {'ok': True}


# ---------------------------------------------------------------- Ballava Chef: your saved chats
MAX_CHATS, MAX_CHAT_MESSAGES = 50, 100
CHAT_ID = re.compile(r'[a-z0-9]{4,40}')
# What a saved message may hold (the same fields the phone shows). Anything else is dropped.
MESSAGE_TEXT = {'from': 10, 'text': 4000, 'recipeId': 60, 'warning': 200, 'source': 20, 'note': 300}
MESSAGE_LISTS = {'dishes': 60, 'shopping': 60, 'followups': 80, 'found': 60, 'added': 60}


def clean_message(m):
    if not isinstance(m, dict) or m.get('from') not in ('me', 'bot'):
        return None
    out = {k: str(m[k])[:n] for k, n in MESSAGE_TEXT.items() if m.get(k) not in (None, '')}
    out.update({k: [str(x)[:n] for x in m[k][:15]] for k, n in MESSAGE_LISTS.items() if isinstance(m.get(k), list) and m[k]})
    for k in ('error', 'done', 'undone', 'planned'):
        if m.get(k) is True:
            out[k] = True
    plan = m.get('plan')
    if isinstance(plan, dict) and isinstance(plan.get('days'), dict):  # a plan Chef made: dates and dish ids only
        out['plan'] = {'kind': 'week' if plan.get('kind') == 'week' else 'day',
                       'days': {str(d)[:10]: {s: str(v)[:60] for s, v in day.items() if s in planner.SLOTS and isinstance(v, str)}
                                for d, day in list(plan['days'].items())[:7] if isinstance(day, dict)}}
    if isinstance(m.get('at'), (int, float)):
        out['at'] = int(m['at'])
    return out


def chat_json(thread):
    return {'id': thread.chat_id, 'title': thread.title, 'at': thread.at, 'messages': thread.messages}


@endpoint(methods=('GET', 'POST'), limit=STATE)
def chats(request, body):
    """GET: your saved chats with Ballava Chef, newest first. POST {id, title, at, messages}: save one."""
    user = require_user(request)
    if request.method == 'GET':
        return {'chats': [chat_json(t) for t in user.chats.all()[:MAX_CHATS]]}
    chat_id = str(body.get('id') or '')
    if not CHAT_ID.fullmatch(chat_id):
        raise ApiError(400, 'Unknown chat.')
    messages = [m for m in map(clean_message, _list(body.get('messages'))[-MAX_CHAT_MESSAGES:]) if m]
    try:
        at = int(body.get('at') or 0)
    except (TypeError, ValueError):
        at = 0
    thread, _ = ChatThread.objects.update_or_create(user=user, chat_id=chat_id, defaults={
        'title': str(body.get('title') or 'Chat')[:80], 'at': at, 'messages': messages})
    for old in user.chats.all()[MAX_CHATS:]:  # keep the newest 50
        old.delete()
    return {'ok': True, 'id': thread.chat_id}


@endpoint()
def delete_chats(request, body):
    """{id}: delete one chat. {all: true}: delete them all."""
    user = require_user(request)
    if body.get('all') is True:
        user.chats.all().delete()
    else:
        user.chats.filter(chat_id=str(body.get('id') or '')).delete()
    return {'ok': True}


# ---------------------------------------------------------------- family vote
def voter_key(request, raw):
    """Who is voting. A signed-in family member is always the same voter, on any device. Anyone else is known by a
    random id their phone keeps ("g:" in front, so nobody can pretend to be a signed-in person)."""
    user = app_user(request)
    if user:
        return f'u:{user.pk}'
    raw = str(raw or '').strip()[:60]
    return 'g:' + raw if raw else ''


def poll_json(poll, voter=''):
    """One meal's vote: the dishes, how many votes each has, who voted, and what this voter chose."""
    votes = list(poll.votes.order_by('pk').values_list('option_id', 'name', 'voter'))
    options = [{**o, 'votes': sum(1 for v in votes if v[0] == o['id']), 'voters': [v[1] for v in votes if v[0] == o['id'] and v[1]]}
               for o in poll.options]
    top = max([o['votes'] for o in options] + [0])
    return {'token': poll.token, 'title': poll.title, 'date': poll.date, 'slot': poll.slot, 'options': options,
            'closed': poll.closes_at < timezone.now(), 'total': len(votes),
            'leaders': [o['id'] for o in options if top and o['votes'] == top],
            'mine': next((v[0] for v in votes if voter and v[2] == voter), None)}


def find_poll(token):
    poll = Poll.objects.filter(token=token).first()
    if not poll:
        raise ApiError(404, 'This vote was not found.')
    return poll


def clean_options(raw):
    out = []
    for o in _list(raw)[:5]:
        if isinstance(o, dict) and o.get('id') and o.get('name') and str(o['id'])[:40] not in [x['id'] for x in out]:
            out.append({'id': str(o['id'])[:40], 'name': str(o['name'])[:80]})
    return out


def valid_date(value):
    try:
        return datetime.strptime(str(value), '%Y-%m-%d')
    except ValueError:
        return None


def vote_closes(date):
    """Voting stays open until the end of the day the meal is for (at least 12 hours from now)."""
    day = valid_date(date)
    if not day:
        return timezone.now() + timedelta(days=3)
    soonest, latest = timezone.now() + timedelta(hours=12), timezone.now() + timedelta(days=9)
    return min(max(timezone.make_aware(day + timedelta(days=1)), soonest), latest)


def share_base(request):
    """The address to put in a shared link. `localhost` only opens on this computer, so use PUBLIC_URL, or the first
    Wi-Fi address in DJANGO_ALLOWED_HOSTS."""
    if settings.PUBLIC_URL:
        return settings.PUBLIC_URL
    host, _, port = request.get_host().partition(':')
    if host in ('localhost', '127.0.0.1'):
        lan = next((h for h in settings.ALLOWED_HOSTS if re.fullmatch(r'\d{1,3}(\.\d{1,3}){3}', h) and not h.startswith('127.')), None)
        if lan:
            return f'http://{lan}' + (f':{port}' if port else '')
    return request.build_absolute_uri('/').rstrip('/')


def ballot_json(group, voter=''):
    """Every meal of a shared plan. A link to a single older vote works too."""
    polls = list(Poll.objects.filter(group=group).order_by('position')) or [find_poll(group)]
    return {'group': group, 'meals': [poll_json(p, voter) for p in polls]}


def open_ballot(request, user, meals):
    if limited(f'poll:{user.pk}', 30, 3600):
        raise ApiError(429, 'Too many votes started. Please try again later.')
    group = secrets.token_hex(8)
    with transaction.atomic():
        for n, m in enumerate(meals):
            Poll.objects.create(token=secrets.token_hex(16), group=group, position=n, household=user.profile.household,
                                title=m['title'], date=m['date'], slot=m['slot'], options=m['options'], closes_at=vote_closes(m['date']))
    return {**ballot_json(group), 'shareBase': share_base(request)}


@endpoint()
def create_poll(request, body):
    """A vote about one meal."""
    user = require_user(request)
    options = clean_options(body.get('options'))
    if len(options) < 2:
        raise ApiError(400, 'A vote needs at least two dishes.')
    made = open_ballot(request, user, [{'title': str(body.get('title') or 'What should we eat?')[:100], 'options': options,
                                        'date': str(body.get('date') or '')[:10], 'slot': str(body.get('slot') or 'dinner')[:20]}])
    return {'token': made['meals'][0]['token'], 'group': made['group'], 'shareBase': made['shareBase']}


@endpoint()
def create_ballot(request, body):
    """Share a plan for voting: {meals: [{date, slot, options: [{id, name}]}]}, for a day or a week."""
    user = require_user(request)
    meals = []
    for m in _list(body.get('meals'))[:21]:
        if not isinstance(m, dict) or m.get('slot') not in planner.SLOTS or not valid_date(m.get('date')):
            raise ApiError(400, 'Unknown meal.')
        options = clean_options(m.get('options'))
        if len(options) >= 2:
            meals.append({'title': planner.SLOT_LABEL[m['slot']], 'date': m['date'], 'slot': m['slot'], 'options': options})
    if not meals:
        raise ApiError(400, 'A vote needs at least two dishes for a meal.')
    return open_ballot(request, user, meals)


@endpoint(methods=('GET',))
def get_ballot(request, body, group):
    return {**ballot_json(group, voter_key(request, request.GET.get('voter'))), 'shareBase': share_base(request)}


@endpoint(methods=('GET',))
def get_poll(request, body, token):
    return poll_json(find_poll(token), voter_key(request, request.GET.get('voter')))


@endpoint()
def cast_vote(request, body, token):
    if limited(f'vote:{token}:{client_ip(request)}', 120, 3600):
        raise ApiError(429, 'Too many votes. Please try again later.')
    poll = find_poll(token)
    if poll.closes_at < timezone.now():
        raise ApiError(410, 'This vote has closed.')
    voter = voter_key(request, body.get('voter'))
    if not voter:
        raise ApiError(400, 'Missing voter.')
    if not any(o['id'] == body.get('optionId') for o in poll.options):
        raise ApiError(400, 'Please choose one of the dishes.')
    user = app_user(request)
    name = clean_name(body.get('name')) or (user.first_name if user else '')
    Vote.objects.update_or_create(poll=poll, voter=voter, defaults={'option_id': body['optionId'], 'name': name})
    return poll_json(poll, voter)


def vote_link(request, group, choice=''):
    """The short link in a WhatsApp message. It gives WhatsApp a preview, then opens the voting page in the app.
    Nothing is counted here (WhatsApp itself opens links to preview them): the page casts the vote."""
    return render(request, 'kitchen/vote_link.html', {
        'target': f'/#/vote/{group}' + (f'/{choice}' if choice else ''), 'image': share_base(request) + '/icon-512.png',
        'title': 'Vote: what should we eat?' if Poll.objects.filter(group=group).exists() else 'This vote was not found'})


# ---------------------------------------------------------------- the brain
def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def context(body):
    """Turns what the phone sent into the arguments the planner functions take."""
    live = catalog.live()
    try:
        tz = max(-840, min(840, int(body.get('tz', planner.INDIA))))
    except (TypeError, ValueError):
        tz = planner.INDIA
    history = [h for h in _list(body.get('history')) if isinstance(h, dict) and (h.get('date') or h.get('at'))]
    ratings = {}
    # A saved (hearted) dish counts like a 4-star rating until the family rates it, so it comes up a little more often.
    for s in _list(body.get('savedDishes')):
        if isinstance(s, dict) and isinstance(s.get('id'), str):
            ratings[s['id']] = 4
    for h in history:
        if h.get('rating') and h.get('recipeId'):
            ratings[h['recipeId']] = h['rating']
    ai_recipes = {k: v for k, v in _dict(body.get('aiRecipes')).items() if isinstance(v, dict) and v.get('ingredients')}
    pantry = [p if isinstance(p, dict) else {'id': str(p)} for p in _list(body.get('pantry'))]
    return {
        'pantry': [p for p in pantry if p.get('id')],
        'members': [m for m in _list(body.get('members')) if isinstance(m, dict)],
        'pins': [p for p in _list(body.get('pins')) if isinstance(p, dict) and 'recipeId' in p and 'weekday' in p],
        'log': planner.normalize_log(history, tz), 'ratings': ratings, 'tz': tz,
        'extra_recipes': live['recipes'], 'hidden': live['hidden'], 'extra': {**ai_recipes, **live['extra']},
    }


def ranked(rows, limit=None):
    """Results for the screens: the recipe as its id (the phone already has the full recipe book)."""
    return [{**r, 'recipe': r['recipe']['id']} for r in rows[:limit]]


@endpoint(limit=STATE)
def parse_view(request, body):
    catalog.live()  # include ingredients that admins added
    return engine.parse_ingredients(str(body.get('text') or '')[:2000])


@endpoint(limit=STATE)
def suggest_view(request, body):
    live = catalog.live()
    pantry = [{'id': p} if isinstance(p, str) else p for p in _list(body.get('pantry'))]
    result = engine.suggest(pantry=pantry, members=_list(body.get('members')), filters=_dict(body.get('filters')),
                            extra_recipes=live['recipes'], hidden=live['hidden'])
    slim = lambda r: {'id': r['recipe']['id'], 'name': r['recipe']['name'], 'time': r['recipe']['time'],  # noqa: E731
                      'missing': r['missing'], 'usesSoon': r['usesSoon'], 'notes': r['notes']}
    return {'ready': [slim(r) for r in result['ready']], 'almost': [slim(r) for r in result['almost']]}


@endpoint()
def chat_view(request, body):
    live = catalog.live()
    return engine.chat_reply(str(body.get('text') or '')[:1000], extra_recipes=live['recipes'], hidden=live['hidden'])


@endpoint()
def rescue_view(request, body):
    catalog.live()
    return engine.find_rescue(str(body.get('text') or ''))


@endpoint(limit=STATE)
def home(request, body):
    """The Cook screen: what to cook now, ranked so recent repeats go down and family goals go up."""
    ctx = context(body)
    today = planner.day_key(None, ctx['tz'])
    params = dict(pantry=ctx['pantry'], members=ctx['members'], filters=_dict(body.get('filters')), ratings=ctx['ratings'],
                  extra_recipes=ctx['extra_recipes'], hidden=ctx['hidden'])
    found = engine.suggest(**params)

    def rank(rows):
        out = []
        for r in rows:
            repeat = planner.repeat_check(r['recipe'], ctx['log'], today, ctx['pins'], ctx['extra'])
            goal = planner.goal_score(r['recipe'], ctx['members'])
            out.append({**r, 'repeat': repeat, 'goalWhy': goal['why'][0] if goal['why'] else None, 'rank': r['score'] - repeat['penalty'] + goal['bonus']})
        return sorted(out, key=lambda r: -r['rank'])

    return {'ready': ranked(rank(found['ready'])), 'almost': ranked(rank(found['almost'])),
            'tips': engine.buy_tips(**params), 'prep': planner.prep_tonight(_dict(body.get('plan')), today, ctx['extra']), 'today': today}


@endpoint(limit=STATE)
def plan_week(request, body):
    ctx = context(body)
    start = str(body.get('start') or planner.day_key(None, ctx['tz']))
    plan = planner.plan_week(start=start, existing=_dict(body.get('existing')), festivals=catalog.festivals(),
                             observed=_list(body.get('observed')), **ctx)
    return {'plan': plan}


def slot_options(body):
    """Dishes that could replace one planned meal, best first. Never anything else planned that week, and never
    a dish already tried for this meal (`exclude`), so swapping keeps finding new ideas instead of bouncing
    between the same two (dosa, idli, dosa...)."""
    ctx = context(body)
    plan, date, slot = _dict(body.get('plan')), str(body.get('date') or ''), body.get('slot')
    if slot not in planner.SLOTS:
        raise ApiError(400, 'Unknown meal.')
    start = str(body.get('start') or date)
    days = [planner.add_days(start, i) for i in range(7)]
    week = {i for d in days for i in planner.day_recipe_ids(plan.get(d))}
    tried = {str(x) for x in _list(body.get('exclude'))}
    day_log = ctx['log'] + [{'recipeId': plan[d][s], 'date': d, 'slot': s} for d in days for s in planner.SLOTS
                            if (plan.get(d) or {}).get(s) and not (d == date and s == slot)]
    rows = planner.recommend(**{**ctx, 'log': day_log}, slot=slot, date=date, fasting_applies=False)
    return [r for r in rows if r['recipe']['id'] not in week and r['recipe']['id'] not in tried]


@endpoint(limit=STATE)
def swap(request, body):
    """Pick a different dish for one meal: the best one not planned this week and not tried already."""
    rows = slot_options(body)
    return {'recipeId': rows[0]['recipe']['id'] if rows else None}


@endpoint(limit=STATE)
def alternatives(request, body):
    """A page of ideas for one planned meal, with why each one fits and what it needs."""
    try:
        limit = max(1, min(12, int(body.get('limit') or 6)))
    except (TypeError, ValueError):
        limit = 6
    rows = slot_options(body)
    return {'options': [{'id': r['recipe']['id'], 'why': r['why'][:2], 'missing': [engine.name_of(o[0]) for o in r['majorMissing']]}
                        for r in rows[:limit]], 'more': len(rows) > limit}


@endpoint(limit=STATE)
def recommend_view(request, body):
    ctx = context(body)
    slot = body.get('slot') if body.get('slot') in [*planner.SLOTS, 'tiffin'] else None
    rows = planner.recommend(**ctx, slot=slot, date=body.get('date') or None, fasting_applies=False)
    return {'ids': [r['recipe']['id'] for r in rows[:max(1, min(20, int(body.get('limit') or 3)))]]}


@endpoint(limit=STATE)
def plan_info(request, body):
    """Everything the Plan screen shows besides the plan itself."""
    ctx = context(body)
    plan = _dict(body.get('plan'))
    today = planner.day_key(None, ctx['tz'])
    day = plan.get(today) or {}
    plate_tips = sum(len(planner.plates_for(r, ctx['members'])) for s in planner.SLOTS if (r := planner.lookup(day.get(s), ctx['extra'])))
    return {
        'today': today,
        'prep': planner.prep_tonight(plan, today, ctx['extra']),
        'groceries': planner.plan_groceries(plan, today, pantry=ctx['pantry'], extra=ctx['extra']),
        'menu': planner.menu_message(day, lang=str(body.get('lang') or 'en'), members=ctx['members'], extra=ctx['extra']) if day else None,
        'plateTips': plate_tips,
    }


@endpoint(limit=STATE)
def recipe_info(request, body):
    """Everything the recipe page needs about this family: can they eat it, portion tips, last made."""
    ctx = context(body)
    recipe = planner.lookup(str(body.get('recipeId') or ''), ctx['extra'])
    if not recipe:
        raise ApiError(404, 'Recipe not found.')
    house = engine.household_check(recipe, ctx['members'])
    today = planner.day_key(None, ctx['tz'])
    return {
        'house': house,
        'plates': planner.plates_for(recipe, ctx['members']) if house['ok'] else [],
        'lastDays': planner.repeat_check(recipe, ctx['log'], today, (), ctx['extra'])['lastDays'],
        'leftovers': planner.leftover_chains(recipe),
        'shareText': engine.recipe_text(recipe),
    }


@endpoint(limit=STATE)
def dashboard_view(request, body):
    ctx = context(body)
    return planner.dashboard([*ctx['log']], extra=ctx['extra'], tz=ctx['tz'])


@endpoint(limit=STATE)
def calories_view(request, body):
    """The family dashboard: calories per day, nutrients, every meal with its calories, plans and a lighter swap."""
    ctx = context(body)
    try:
        days = max(1, min(31, int(body.get('days') or 7)))
    except (TypeError, ValueError):
        days = 7
    return planner.calorie_dashboard(ctx['log'], days=days, extra=ctx['extra'], tz=ctx['tz'], plan=_dict(body.get('plan')),
                                     members=ctx['members'], extra_recipes=ctx['extra_recipes'], hidden=ctx['hidden'])


@endpoint(limit=STATE)
def ask(request, body):
    ctx = context(body)
    current = planner.lookup(str(body.get('recipeId') or ''), ctx['extra']) if body.get('recipeId') else None
    return planner.assistant_reply(str(body.get('text') or '')[:500], plan=_dict(body.get('plan')), current=current, **ctx)


# ---------------------------------------------------------------- AI Chef
def _ai_allowed(request):
    user = app_user(request)
    who = f'user:{user.pk}' if user else 'ip:' + client_ip(request)
    if limited('ai:' + who, settings.AI_RATE_LIMIT, 60):
        raise ApiError(429, 'Too many AI requests. Please wait a minute.')
    row, _ = AiUsage.objects.get_or_create(day=timezone.localdate(), who=who)
    AiUsage.objects.filter(pk=row.pk).update(calls=row.calls + 1)


@endpoint()
def ai_invent(request, body):
    wish = str(body.get('wish') or '')[:300]
    live = catalog.live()
    # Asked for a dish that's already in the recipe book? Give exactly that one (no AI needed).
    book = planner.mentioned_recipe(wish.lower(), live['recipes'], live['hidden'])
    if book:
        return {'recipe': book, 'fromBook': True}
    _ai_allowed(request)
    household = [m for m in _list(body.get('household')) if isinstance(m, dict)]
    diners = [{**m, 'fasting': False} for m in household]
    args = dict(pantry=_list(body.get('pantry')), household=household, wish=wish, meal=body.get('meal'))
    avoid = None
    for _attempt in range(2):  # if an invented idea breaks a family rule, ask once more, saying why
        raw = ai.invent_recipe(**args, avoid=avoid)
        try:
            recipe = engine.normalize_ai_recipe(raw)
        except ValueError as err:
            raise ApiError(502, f'{err}. Please try again.') from err
        house = engine.household_check(recipe, diners)
        if house['ok']:
            return {'recipe': recipe}
        if recipe.get('requested') or engine.names_dish(wish, recipe['name']):
            # They asked for this dish by name: give exactly that, with a clear warning, never a different dish.
            return {'recipe': {**recipe, 'requested': True, 'warning': house['reason']}, 'warning': house['reason']}
        avoid = house['reason']
    raise ApiError(502, f"The AI's idea didn't suit your family ({avoid}). Please try again, or add a wish like \"vegetarian\".")


@endpoint()
def ai_estimate(request, body):
    """Calories for a meal that isn't in the recipe book, for the food diary."""
    name = str(body.get('name') or '').strip()
    if not name:
        raise ApiError(400, 'Please give the name of the food.')
    _ai_allowed(request)
    return ai.estimate_meal(name)


@endpoint(limit=STATE)
def ai_chat(request, body):
    """The kitchen assistant on every screen. Uses the AI when it's on, and the built-in brain otherwise
    (or when the AI is busy), so there is always an answer."""
    question = str(body.get('text') or '').strip()[:1000]
    if not question:
        raise ApiError(400, 'Please type a question.')
    ctx = context(body)
    current = planner.lookup(str(body.get('recipeId') or ''), ctx['extra']) if body.get('recipeId') else None
    named = planner.mentioned_recipe(question.lower(), ctx['extra_recipes'], ctx['hidden'])  # "how do I make dal tadka?"
    # "Plan my day" / "plan my week": make a real plan (the Plan tab's rules), which the phone can add with one tap.
    made = planner.chat_plan(question, plan=_dict(body.get('plan')), festivals=catalog.festivals(),
                             observed=_list(body.get('observed')), **ctx)
    if made:
        named = None
    today = planner.day_key(None, ctx['tz'])

    def built_in(note=None):
        if made:
            head = 'Here is your week, with no repeats' if made['kind'] == 'week' else "Here's a plan"
            reply = f"{head}:\n{planner.plan_summary(made, ctx['extra'], today)}\nTap “Add to my plan” to use it."
            return {'reply': reply, 'dishes': [], 'recipe': None, 'shopping': [], 'plan': made, 'source': 'builtin', 'note': note}
        r = planner.assistant_reply(question, plan=_dict(body.get('plan')), current=current, **ctx)
        return {'reply': r['reply'], 'dishes': r.get('dishes', []), 'recipe': None, 'shopping': [], 'source': 'builtin', 'note': note}

    if not ai.ai_key():
        return built_in()
    try:
        _ai_allowed(request)
    except ApiError as err:
        return built_in(err.message)
    history = [('assistant' if m.get('from') == 'bot' else 'user', str(m.get('text') or '')[:1500])
               for m in _list(body.get('messages'))[-8:] if isinstance(m, dict) and m.get('text')]
    try:
        data = ai.chat(question, assistant.context_text(ctx, body, current, named=named, made=made, festivals=catalog.festivals()), history)
    except ApiError as err:
        log.warning('AI chat fell back to the built-in answers: %s', err.message)
        return built_in(err.message)
    return assistant.clean_reply(data, ctx, current, question=question, named=named, made=made)


@endpoint(limit=PHOTO)
def ai_scan(request, body):
    _ai_allowed(request)
    names = ai.scan_photo(body.get('image'), body.get('mediaType') or 'image/jpeg')
    catalog.live()
    parsed = engine.parse_ingredients(', '.join(names))
    return {'names': names, 'found': parsed['found'], 'unknown': parsed['unknown']}
