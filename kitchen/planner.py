"""Ballava planner: decides what to cook, day after day.

Plain Python functions with no Django code. Log entries look like
{'recipeId': ..., 'name': ..., 'date': 'YYYY-MM-DD', 'slot': 'dinner', 'rating': 4}.

About dates: the server may run in a different time zone from the family (Docker usually runs
on UTC). So every function that needs "today" takes `tz`, the phone's time-zone offset in
minutes, exactly as the browser reports it (India is -330). It defaults to India.
"""
from datetime import date as Date, datetime, timedelta, timezone

from .data.ingredients import ASSUMED, BY_ID
from .engine import (FLAVOURINGS, RECIPE_BY_ID, household_check, match_recipe, now_ms, parse_ingredients, recipes_from,
                     suggest, use_soon)

SLOTS = ['breakfast', 'lunch', 'dinner']
SLOT_LABEL = {'breakfast': 'Breakfast', 'lunch': 'Lunch', 'dinner': 'Dinner', 'snack': 'Snack'}
WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
INDIA = -330

# Health goals a family member can have. These only nudge the ranking; they are not medical advice.
GOALS = [['bp', 'Low salt (BP)'], ['weight', 'Weight care'], ['pcos', 'PCOS'], ['pregnancy', 'Pregnant']]
AGE_GROUPS = [['toddler', 'Toddler (1-3)'], ['child', 'Child (4-12)'], ['teen', 'Teen'], ['adult', 'Adult'], ['senior', 'Senior']]


# ------------------------------------------------------------------- dates
def _local(t, tz):
    return datetime.fromtimestamp(t / 1000, timezone.utc) - timedelta(minutes=tz)


def day_key(t=None, tz=INDIA):
    """A timestamp in milliseconds -> the family's date, like '2026-11-09'."""
    return _local(t if t is not None else now_ms(), tz).strftime('%Y-%m-%d')


def add_days(key, n):
    return (Date.fromisoformat(key) + timedelta(days=n)).isoformat()


def days_between(a, b):
    return (Date.fromisoformat(b) - Date.fromisoformat(a)).days


def weekday_of(key):
    """0 = Sunday ... 6 = Saturday (the same numbering the app uses)."""
    return (Date.fromisoformat(key).weekday() + 1) % 7


def slot_now(t=None, tz=INDIA):
    h = _local(t if t is not None else now_ms(), tz).hour
    return 'breakfast' if h < 11 else 'lunch' if h < 16 else 'dinner'


def normalize_log(history=(), tz=INDIA):
    """Older history entries only have a timestamp, so fill in the day and the meal."""
    return [{**h, 'date': h.get('date') or day_key(h['at'], tz), 'slot': h.get('slot') or slot_now(h['at'], tz)} for h in history]


# ---------------------------------------------------- what is in a dish
AROMATICS = {'onion', 'tomato', 'garlic', 'ginger', *FLAVOURINGS}
NOT_PROTEIN = {'peanuts', 'cashew'}
GREENS = {'spinach', 'methi'}
WHOLE_GRAINS = {'atta', 'oats', 'ragi', 'jowar', 'bajra', 'kuttu', 'samak', 'leftover_roti'}
NOT_VEG = AROMATICS | {'potato', 'sweet_potato', 'sweet_corn'}
BASES = {
    'rice': ['rice', 'leftover_rice', 'dosa_batter', 'poha'],
    'wheat': ['atta', 'maida', 'bread', 'sooji', 'noodles', 'pasta', 'vermicelli', 'leftover_roti'],
    'millet': ['ragi', 'jowar', 'bajra'],
}


def lookup(id_, extra=None):
    return (extra or {}).get(id_) or RECIPE_BY_ID.get(id_)


def _required(recipe):
    return [i for i in recipe['ingredients'] if not i['optional']]


def _category(id_):
    return BY_ID.get(id_, {}).get('category')


def _name(id_):
    return BY_ID.get(id_, {}).get('name', id_)


def mains_of(recipe):
    """The ingredients a dish is "about" (no masalas, onion, tomato and so on)."""
    out = []
    for it in _required(recipe):
        id_, cat = it['options'][0], _category(it['options'][0])
        if not cat or id_ in AROMATICS or cat in ('Spices', 'Basics & Sauces') or id_ in out:
            continue
        out.append(id_)
    return out


def base_of(recipe):
    for base, ids in BASES.items():
        if any(not it['optional'] and any(i in ids for i in it['options']) for it in recipe['ingredients']):
            return base
    return None


def groups_of(recipe):
    """Food groups for the dashboard. A dish counts when it really contains the group."""
    ids = [i for it in recipe['ingredients'] if not it['optional'] for i in it['options']]
    has = lambda test: any(test(i) for i in ids)  # noqa: E731
    groups = []
    if has(lambda i: i in GREENS):
        groups.append('greens')
    if has(lambda i: _category(i) == 'Vegetables' and i not in NOT_VEG and i not in GREENS):
        groups.append('vegetables')
    if has(lambda i: (_category(i) == 'Dals & Beans' and i not in NOT_PROTEIN) or _category(i) == 'Meat & Fish'
           or i in ('egg', 'paneer', 'leftover_dal', 'besan')):
        groups.append('protein')
    if has(lambda i: i in WHOLE_GRAINS):
        groups.append('wholegrain')
    if has(lambda i: _category(i) == 'Fruits'):
        groups.append('fruit')
    return groups


# ---------------------------------------------------- no-repeat scoring
def _nice_list(ids):
    return ' and '.join(_name(i).lower() for i in ids)


def repeat_check(recipe, log, date, pins=(), extra=None):
    """How much to push a dish down because of what was eaten around `date`."""
    penalty, reasons = 0, []
    pinned = any(p['recipeId'] == recipe['id'] for p in pins)
    mains, base = mains_of(recipe), base_of(recipe)
    main_hit = base_hit = 0
    last_days = None
    for e in log:
        gap = abs(days_between(e['date'], date))
        if gap > 13:
            continue
        if e.get('recipeId') == recipe['id']:
            if last_days is None or gap < last_days:
                last_days = gap
            continue
        other = lookup(e.get('recipeId'), extra)
        if not other or gap > 2:
            continue
        shared = [m for m in mains_of(other) if m in mains]
        if shared:
            main_hit += 16 if gap <= 1 else 8
            if gap <= 1 and not reasons:
                reasons.append(f"Had {_nice_list(shared)} {'today' if gap == 0 else 'recently'}")
        if gap == 0 and base and base_of(other) == base:
            base_hit += 10
    if last_days is not None and not pinned:
        penalty += 90 if last_days <= 2 else 55 if last_days <= 6 else 20
        reasons.insert(0, 'Already on the menu today' if last_days == 0 else f"Made {last_days} day{'s' if last_days > 1 else ''} ago")
    penalty += min(main_hit, 32) + min(base_hit, 20)
    return {'penalty': penalty, 'reasons': reasons, 'lastDays': last_days}


# ---------------------------------------------------- family diet
SALTY = ['soy_sauce', 'noodles', 'tomato_ketchup', 'chaat_masala', 'cheese']


def goal_score(recipe, members=()):
    bonus, why = 0, []
    tags = recipe['tags']
    uses = lambda id_: any(not it['optional'] and id_ in it['options'] for it in recipe['ingredients'])  # noqa: E731
    groups = groups_of(recipe)

    def note(text):
        if text not in why:
            why.append(text)

    for m in members:
        goals = m.get('goals') or []
        who = m.get('name') or 'someone'
        if m.get('diabetic') and 'diabetic-friendly' in tags:
            bonus += 10
            note(f"Good for {who}'s sugar")
        if 'bp' in goals and any(uses(i) for i in SALTY):
            bonus -= 14
        if 'weight' in goals:
            if 'high-protein' in tags:
                bonus += 6
                note(f'Filling and light for {who}')
            if 'sweet' in tags:
                bonus -= 15
        if 'pcos' in goals and ('diabetic-friendly' in tags or 'high-protein' in tags):
            bonus += 6
            note(f'Balanced for {who}')
        if 'pregnancy' in goals and ('high-protein' in tags or 'greens' in groups):
            bonus += 6
            note(f'Protein and iron for {who}')
        if m.get('age') in ('toddler', 'child') and 'kid-friendly' in tags:
            bonus += 8
            note(f'{who} will like this')
        if any(uses(i) for i in m.get('likes') or []):
            bonus += 6
            note(f'{who} loves this')
        if any(uses(i) for i in m.get('dislikes') or []):
            bonus -= 22
    return {'bonus': bonus, 'why': why}


def plates_for(recipe, members=()):
    """"One meal, many plates": small changes so one pot works for everyone."""
    plates = []

    def add(who, text):
        row = next((p for p in plates if p['who'] == who), None)
        if row is None:
            plates.append({'who': who, 'tips': [text]})
        elif text not in row['tips']:
            row['tips'].append(text)

    def uses(ids, optional=None):
        return any((optional is None or it['optional'] == optional) and any(i in ids for i in it['options']) for it in recipe['ingredients'])

    base = base_of(recipe)
    for m in members:
        who = m.get('name') or 'Someone'
        goals = m.get('goals') or []
        if m.get('spice') and m['spice'] < recipe['spice'] and recipe['hasChilli']:
            add(who, 'Take out their portion before adding chilli.')
        if m.get('age') == 'toddler':
            add(who, 'Take out their portion before salt and chilli go in, and mash it well.')
            if uses(['peanuts', 'cashew']):
                add(who, 'Leave out whole nuts, as they can cause choking.')
        if m.get('age') == 'senior' and recipe['time'] > 0 and uses(['rice', 'leftover_rice', 'toor_dal', 'moong_dal', 'chana_dal']):
            add(who, 'Cook their portion a little softer if chewing is hard.')
        if 'bp' in goals:
            add(who, 'Salt their portion lightly and add lemon for flavour instead.')
        if m.get('diabetic') and base in ('rice', 'wheat'):
            add(who, 'Serve a smaller portion of rice or roti, with more dal and sabzi.')
        if 'weight' in goals and uses(['ghee', 'butter', 'cream']):
            add(who, 'Use less ghee, butter or cream on their plate.')
        if 'pregnancy' in goals and recipe['diet'] != 'veg':
            add(who, 'Make sure meat, fish and eggs are fully cooked.')
        for id_ in m.get('dislikes') or []:
            if uses([id_], True):
                add(who, f'Leave out {_name(id_).lower()} from their portion.')
        opt_allergen = next((a for a in m.get('allergies') or [] if any(
            it['optional'] and any(a in BY_ID.get(i, {}).get('allergens', []) for i in it['options']) for it in recipe['ingredients'])), None)
        if opt_allergen:
            add(who, f'Skip the optional {opt_allergen} items, they are allergic.')
    return plates


# ---------------------------------------------------- recommendations
def _hash(s):
    """A small, stable number per (date, dish), so plans vary from day to day but never at random."""
    h = 7
    for c in s:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return abs(h - 0x100000000 if h >= 0x80000000 else h)


# Existing dishes that pack well. Leftover-rice dishes are kept out on purpose: a lunchbox sits warm for hours.
TIFFIN_IDS = {'kanda_poha', 'rava_upma', 'besan_chilla', 'aloo_paratha', 'veg_pulao', 'veg_fried_rice', 'hakka_noodles', 'masala_pasta',
              'veg_sandwich', 'idli', 'jeera_aloo'}


def fits_slot(recipe, slot):
    if slot == 'tiffin':
        return 'tiffin' in recipe['tags'] or recipe['id'] in TIFFIN_IDS
    return slot in recipe['meal'] and 'side' not in recipe['meal']


def recommend(pantry=(), members=(), ratings=None, log=(), pins=(), filters=None, slot=None, date=None, now=None,
              extra_recipes=(), hidden=(), extra=None, only_vrat=False, fasting_applies=True, tz=INDIA):
    """Best dishes for one meal on one day. Unlike suggest(), this also considers dishes you'd need to shop for."""
    ratings, filters = ratings or {}, filters or {}
    now = now or now_ms()
    date = date or day_key(now, tz)
    pantry_ids = [p['id'] for p in pantry]
    soon_ids = [p['id'] for p in use_soon(pantry, now)]
    diners = list(members) if fasting_applies else [{**m, 'fasting': False} for m in members]
    weekday = weekday_of(date)
    out = []
    for recipe in recipes_from(extra_recipes, hidden):
        if slot and not fits_slot(recipe, slot):
            continue
        if only_vrat and 'vrat' not in recipe['tags']:
            continue
        if filters.get('veg') and recipe['diet'] != 'veg':
            continue
        if filters.get('quick') and recipe['time'] > 20:
            continue
        if filters.get('healthy') and 'diabetic-friendly' not in recipe['tags']:
            continue
        house = household_check(recipe, diners)
        if not house['ok']:
            continue
        m = match_recipe(recipe, pantry_ids, soon_ids)
        coverage = m['majorHave'] / max(1, m['majorTotal'])
        rep = repeat_check(recipe, log, date, pins, extra)
        goal = goal_score(recipe, diners)
        pin = next((p for p in pins if p['recipeId'] == recipe['id'] and p['weekday'] == weekday
                    and (not slot or not p.get('slot') or p['slot'] == slot)), None)
        rating = ratings.get(recipe['id'])
        score = (coverage * 60 - len(m['majorMissing']) * 8 + len(m['usesSoon']) * 15 + m['optionalHave']
                 + ((rating - 3) * 6 if rating else 0) + goal['bonus'] - rep['penalty'] + _hash(date + recipe['id']) % 9 + (200 if pin else 0))
        why = []
        if pin:
            why.append(f'Your {WEEKDAYS[weekday]} favourite')
        if m['usesSoon']:
            why.append(f"Uses up {_nice_list(m['usesSoon'])}")
        why.extend(goal['why'])
        if rating and rating >= 4:
            why.append('Your family rated this highly')
        if not m['majorMissing']:
            why.append('You have everything')
        out.append({'recipe': recipe, **m, 'coverage': coverage, 'score': score, 'why': why[:3], 'repeat': rep, 'notes': house['notes']})
    out.sort(key=lambda r: (-r['score'], r['recipe']['time']))
    return out


def fasters_on(date, members=(), festivals=(), observed=()):
    """Who is fasting on a day: weekly habits plus any festival the family observes."""
    names = [m['name'] for m in members if weekday_of(date) in (m.get('fastWeekdays') or [])]
    fest = next((f for f in festivals if f['date'] == date and f.get('fast') and f['id'] in observed), None)
    return {'names': names, 'festival': fest}


def plan_week(start=None, days=7, existing=None, log=(), festivals=(), observed=(), members=(), tz=INDIA, **rest):
    """Plan the week: {'YYYY-MM-DD': {breakfast, lunch, dinner, tiffins: {name: id}, fast: {name: id}, locked: [...]}}.
    Anything the family locked is kept and never overwritten."""
    existing = existing or {}
    start = start or day_key(rest.get('now'), tz)
    plan = {}
    sim = list(log)

    def remember(recipe_id, date, slot):
        sim.append({'recipeId': recipe_id, 'date': date, 'slot': slot})

    for date, day in existing.items():
        for s in SLOTS:
            if day.get(s):
                remember(day[s], date, s)
    for i in range(days):
        date = add_days(start, i)
        old = existing.get(date) or {}
        locked = old.get('locked') or []
        day = {'locked': locked, 'tiffins': {}, 'fast': {}}
        for slot in SLOTS:
            if slot in locked and old.get(slot):
                day[slot] = old[slot]
                continue
            day_log = [e for e in sim if not (e['date'] == date and e['slot'] == slot)]
            ranked = recommend(**rest, members=members, slot=slot, date=date, log=day_log, fasting_applies=False, tz=tz)
            day[slot] = ranked[0]['recipe']['id'] if ranked else None
            if ranked:
                remember(ranked[0]['recipe']['id'], date, slot)
        # School days: a separate, non-repeating lunchbox for each child who takes one.
        if 1 <= weekday_of(date) <= 5:
            for kid in (m for m in members if m.get('tiffin')):
                tiffin_log = [{**e, 'slot': 'tiffin'} for e in sim if e['slot'] == 'tiffin:' + kid['name']]
                ranked = recommend(**rest, members=[{**kid, 'fasting': False}], slot='tiffin', date=date, log=tiffin_log,
                                   fasting_applies=False, tz=tz)
                if ranked:
                    day['tiffins'][kid['name']] = ranked[0]['recipe']['id']
                    remember(ranked[0]['recipe']['id'], date, 'tiffin:' + kid['name'])
        # Fasting: a separate vrat meal, so the rest of the family still eats normally.
        who_fasts = fasters_on(date, members, festivals, observed)
        for who in (['Family'] if who_fasts['festival'] else who_fasts['names']):
            pool = list(members) if who == 'Family' else [m for m in members if m['name'] == who]
            ranked = recommend(**rest, members=pool, slot='lunch', date=date, log=sim, only_vrat=True, fasting_applies=False, tz=tz)
            if ranked:
                day['fast'][who] = ranked[0]['recipe']['id']
                remember(ranked[0]['recipe']['id'], date, 'fast')
        if who_fasts['festival']:
            day['festival'] = who_fasts['festival']['name']
        plan[date] = day
    return plan


def day_recipe_ids(day=None):
    day = day or {}
    return [i for i in [*(day.get(s) for s in SLOTS), *(day.get('tiffins') or {}).values(), *(day.get('fast') or {}).values()] if i]


# ---------------------------------------------------- prep and leftovers
def prep_for(recipe):
    """What must be done the night before, so tomorrow's meals actually happen."""
    if recipe.get('prep'):
        return recipe['prep']
    uses = lambda id_: any(not it['optional'] and id_ in it['options'] for it in recipe['ingredients'])  # noqa: E731
    if uses('dosa_batter'):
        return 'Check you have batter. Fresh batter needs 8-12 hours to ferment.'
    if any(uses(i) for i in ('chicken', 'mutton', 'fish', 'prawns')):
        return 'If it is frozen, move it to the fridge tonight.'
    if uses('chickpeas'):
        return 'If using dry chana, soak it tonight.'
    return None


def prep_tonight(plan, date, extra=None):
    tomorrow = (plan or {}).get(add_days(date, 1))
    if not tomorrow:
        return []
    out, seen = [], set()
    for id_ in day_recipe_ids(tomorrow):
        r = lookup(id_, extra)
        text = r and prep_for(r)
        if text and id_ not in seen:
            seen.add(id_)
            out.append({'recipeId': id_, 'name': r['name'], 'text': text})
    return out


# After cooking: what could be left over, and what it can turn into tomorrow.
CHAINS = [
    ('leftover_rice', lambda r: base_of(r) == 'rice' and any('rice' in i['options'] for i in r['ingredients']), ['lemon_rice', 'curd_rice', 'tomato_rice']),
    ('leftover_dal', lambda r: any(not i['optional'] and any(o in ('toor_dal', 'moong_dal', 'masoor_dal') for o in i['options'])
                                   for i in r['ingredients']), ['dal_paratha']),
    ('leftover_roti', lambda r: any(not i['optional'] and 'atta' in i['options'] for i in r['ingredients']), ['chapati_upma']),
    ('leftover_sabzi', lambda r: ('lunch' in r['meal'] or 'dinner' in r['meal']) and 'vegetables' in groups_of(r), ['veg_cutlet']),
]


def leftover_chains(recipe):
    return [{'item': item, 'name': BY_ID[item]['name'], 'ideas': [RECIPE_BY_ID[i]['name'] for i in ideas if i in RECIPE_BY_ID]}
            for item, test, ideas in CHAINS if test(recipe)]


# ---------------------------------------------------- groceries
def plan_groceries(plan, start, days=7, pantry=(), extra=None):
    """Everything the plan needs that is not in the kitchen, with the dishes that need it."""
    have = {p['id'] for p in pantry} | set(ASSUMED)
    need = {}
    for i in range(days):
        for id_ in day_recipe_ids((plan or {}).get(add_days(start, i))):
            r = lookup(id_, extra)
            if not r:
                continue
            for it in _required(r):
                if any(o in have for o in it['options']):
                    continue
                dishes = need.setdefault(it['options'][0], [])
                if r['name'] not in dishes:
                    dishes.append(r['name'])
    rows = [{'id': k, 'name': _name(k), 'category': _category(k) or 'Other', 'dishes': v} for k, v in need.items()]
    return sorted(rows, key=lambda g: (g['category'].casefold(), g['name'].casefold()))


# ---------------------------------------------------- dashboard
GROUP_TEXT = {'greens': 'leafy greens', 'vegetables': 'vegetables', 'protein': 'protein', 'wholegrain': 'whole grains', 'fruit': 'fruit'}


def dashboard(history=(), now=None, days=7, extra=None, tz=INDIA):
    log = normalize_log(history, tz)
    today = day_key(now, tz)
    in_range = lambda e: 0 <= days_between(e['date'], today) < days  # noqa: E731
    recent = [e for e in log if in_range(e)]

    groups = {g: 0 for g in GROUP_TEXT}
    last_group = {}
    for e in log:
        r = lookup(e.get('recipeId'), extra) if e.get('recipeId') else None
        if not r:
            continue
        for g in groups_of(r):
            if in_range(e):
                groups[g] += 1
            gap = days_between(e['date'], today)
            if gap >= 0 and (g not in last_group or gap < last_group[g]):
                last_group[g] = gap

    counts = {}
    for e in log:
        key = e.get('recipeId') or e['name']
        row = counts.setdefault(key, {'id': e.get('recipeId'), 'name': e['name'], 'count': 0, 'last': e['date'], 'rating': None})
        row['count'] += 1
        if e['date'] > row['last']:
            row['last'] = e['date']
        if e.get('rating'):
            row['rating'] = e['rating']
    rows = list(counts.values())
    recent_names = list(dict.fromkeys(e.get('recipeId') or e['name'] for e in recent))
    variety = round(len(recent_names) / len(recent) * 100) if recent else None
    repeats = [{**counts[k], 'week': sum(1 for e in recent if (e.get('recipeId') or e['name']) == k)} for k in recent_names]
    repeats = sorted((r for r in repeats if r['week'] >= 3), key=lambda r: -r['week'])
    missed = [r for r in rows if r['id'] and ((r['rating'] or 0) >= 4 or r['count'] >= 3) and days_between(r['last'], today) >= 21]
    missed.sort(key=lambda r: r['last'])
    missed.sort(key=lambda r: -(r['rating'] or 0))

    # Friendly, useful nudges. Only say something when there is enough history to be fair.
    insights = []
    if len(log) >= 3:
        for g in ('greens', 'vegetables', 'protein'):
            gap = last_group.get(g)
            if gap is None:
                insights.append({'kind': 'tip', 'text': f'No {GROUP_TEXT[g]} logged yet. Want to add some this week?', 'group': g})
            elif gap >= 4:
                insights.append({'kind': 'tip', 'text': f'No {GROUP_TEXT[g]} in {gap} days. Want to add some tomorrow?', 'group': g})
        for r in repeats[:1]:
            insights.append({'kind': 'tip', 'text': f"{r['name']} was made {r['week']} times this week. Time for a change?"})
        for r in missed[:2]:
            insights.append({'kind': 'idea', 'text': f"You haven't made {r['name']} in {days_between(r['last'], today)} days. It was a family favourite.",
                             'recipeId': r['id']})
        if variety is not None and variety >= 80 and len(recent) >= 5:
            insights.append({'kind': 'good', 'text': f'Lovely variety! {len(recent_names)} different dishes this week.'})
        if groups['greens'] + groups['vegetables'] >= 4:
            insights.append({'kind': 'good', 'text': 'Plenty of vegetables on the table this week.'})

    by_day = {}
    for e in log:
        by_day.setdefault(e['date'], []).append(e)
    return {
        'total': len(log), 'weekCount': len(recent), 'variety': variety, 'groups': groups, 'lastGroup': last_group,
        'insights': insights, 'byDay': by_day, 'top': sorted(rows, key=lambda r: -r['count'])[:5],
        'saved': sum(len(h.get('saved') or []) for h in log), 'repeats': repeats, 'missed': missed,
    }


# ---------------------------------------------------- sharing with a house cook
MENU_WORDS = {
    'en': {'hello': "Today's menu", 'breakfast': 'Breakfast', 'lunch': 'Lunch', 'dinner': 'Dinner', 'note': 'Special portions'},
    'hi': {'hello': 'आज का मेन्यू', 'breakfast': 'नाश्ता', 'lunch': 'दोपहर का खाना', 'dinner': 'रात का खाना', 'note': 'खास ध्यान दें'},
    'te': {'hello': 'ఈ రోజు మెనూ', 'breakfast': 'అల్పాహారం', 'lunch': 'మధ్యాహ్న భోజనం', 'dinner': 'రాత్రి భోజనం', 'note': 'ప్రత్యేక గమనిక'},
    'ta': {'hello': 'இன்றைய மெனு', 'breakfast': 'காலை உணவு', 'lunch': 'மதிய உணவு', 'dinner': 'இரவு உணவு', 'note': 'சிறப்பு குறிப்பு'},
}


def menu_message(day, lang='en', members=(), extra=None):
    w = MENU_WORDS.get(lang, MENU_WORDS['en'])
    day = day or {}
    lines, notes = [w['hello'] + ':'], []
    for s in SLOTS:
        r = day.get(s) and lookup(day[s], extra)
        if not r:
            continue
        lines.append(f"{w[s]}: {r['name']}")
        notes.extend(f"{p['who']} ({r['name']}): {' '.join(p['tips'])}" for p in plates_for(r, members))
    for who, id_ in (day.get('tiffins') or {}).items():
        if r := lookup(id_, extra):
            lines.append(f"Tiffin, {who}: {r['name']}")
    for who, id_ in (day.get('fast') or {}).items():
        if r := lookup(id_, extra):
            lines.append(f"Vrat, {who}: {r['name']}")
    if notes:
        lines.extend(['', w['note'] + ':', *notes[:6]])
    return '\n'.join(lines)


# ---------------------------------------------------- Ask Ballava
def assistant_reply(text, plan=None, now=None, tz=INDIA, **ctx):
    """The assistant behind the in-app chat. It knows the family, the plan and the kitchen.
    ctx: pantry, members, ratings, log, pins, extra_recipes, hidden, extra."""
    q = str(text or '').lower()
    plan = plan or {}
    now = now or now_ms()
    today = day_key(now, tz)
    extra = ctx.get('extra')
    name_of = lambda id_: (lookup(id_, extra) or {}).get('name')  # noqa: E731

    def dish_lines(rows):
        return '\n'.join(f"{n}. {r['recipe']['name']} ({r['recipe']['time']} min){', ' + r['why'][0].lower() if r['why'] else ''}"
                         for n, r in enumerate(rows[:3], 1))

    asks = lambda *words: any(w in q for w in words)  # noqa: E731

    if asks('tomorrow', 'kal'):
        day = plan.get(add_days(today, 1)) or {}
        names = [f'{SLOT_LABEL[s]}: {name_of(day[s])}' for s in SLOTS if day.get(s)]
        if names:
            return {'reply': "Tomorrow's plan:\n" + '\n'.join(names)}
        return {'reply': 'Nothing is planned for tomorrow yet. Open the Plan tab and tap "Plan my week".'}
    if asks('prep', 'soak', 'tonight i', 'ready for'):
        prep = prep_tonight(plan, today, extra)
        return {'reply': '\n'.join(f"{p['name']}: {p['text']}" for p in prep) if prep else 'Nothing to prepare tonight.'}
    if asks('tiffin', 'lunchbox', 'lunch box', 'dabba'):
        rows = recommend(**ctx, slot='tiffin', date=today, now=now, fasting_applies=False, tz=tz)
        return {'reply': 'Good tiffin ideas:\n' + dish_lines(rows), 'dishes': [r['recipe']['id'] for r in rows[:3]]}
    slot = ('breakfast' if asks('breakfast', 'nashta') else 'lunch' if asks('lunch') else 'dinner' if asks('dinner', 'tonight', 'raat')
            else slot_now(now, tz) if asks('cook', 'make', 'banau', 'banaun', 'what should') else None)
    found = parse_ingredients(q)['found']
    if slot and not found:
        planned = (plan.get(today) or {}).get(slot)
        rows = recommend(**ctx, slot=slot, date=today, now=now, tz=tz)
        head = f'Your plan says {name_of(planned)}. Other good options:' if planned else f'For {SLOT_LABEL[slot].lower()}, I\'d suggest:'
        return {'reply': f'{head}\n{dish_lines(rows)}', 'dishes': [r['recipe']['id'] for r in rows[:3]]}
    if found:
        result = suggest(pantry=[{'id': i} for i in found], members=ctx.get('members') or [],
                         extra_recipes=ctx.get('extra_recipes') or [], hidden=ctx.get('hidden') or [])
        pick = (result['ready'] + result['almost'])[:3]
        if pick:
            return {'reply': f"With {', '.join(_name(i) for i in found)} you could make:\n"
                             + '\n'.join(f"{n}. {r['recipe']['name']} ({r['recipe']['time']} min)" for n, r in enumerate(pick, 1)),
                    'dishes': [r['recipe']['id'] for r in pick]}
    return {'reply': 'Ask me things like "What should I cook tonight?", "Tiffin ideas", "What\'s planned for tomorrow?", or "I have paneer and spinach".'}
