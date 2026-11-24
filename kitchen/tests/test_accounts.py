"""Tests for sign-in, family data, family codes, voting and "my data"."""
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from kitchen.models import FamilyData, Household, Poll, Vote
from .conftest import Api

pytestmark = pytest.mark.django_db
PW = 'kadai-masala-42'


def test_sign_up_stay_signed_in_sign_out(make_user):
    c = make_user()
    status, me = c.get_json('me')
    assert me['user']['email'] == c.email and me['household']['inviteCode']
    c.post_json('auth/logout')
    assert c.get_json('me')[1] == {'user': None}


def test_session_cookie_is_hidden_from_page_scripts(api):
    api.post_json('auth/signup', {'name': 'C', 'email': 'cookie@ballava.test', 'password': PW, 'consent': True})
    cookie = api.cookies['sessionid']
    assert cookie['httponly'] and cookie['samesite'] == 'Lax'


def test_sign_up_checks_inputs_and_needs_consent(api):
    good = {'name': 'A', 'email': 'check@ballava.test', 'password': PW, 'consent': True}
    assert api.post_json('auth/signup', {**good, 'email': 'nope'})[0] == 400
    assert api.post_json('auth/signup', {**good, 'password': 'short'})[0] == 400
    assert 'too common' in api.post_json('auth/signup', {**good, 'password': 'password123'})[1]['error']
    assert api.post_json('auth/signup', {**good, 'consent': False})[0] == 400
    assert api.post_json('auth/signup', good)[0] == 200
    assert Api().post_json('auth/signup', good)[0] == 409


def test_passwords_are_stored_hashed(make_user):
    c = make_user()
    stored = User.objects.get(email=c.email).password
    assert stored.startswith('pbkdf2_sha256$') and PW not in stored


def test_wrong_password_fails_and_repeated_tries_lock(make_user):
    c = make_user()
    t = Api()
    statuses = [t.post_json('auth/login', {'email': c.email, 'password': 'wrong-password'})[0] for _ in range(8)]
    assert statuses[0] == 401 and 429 in statuses


def test_phone_sign_in_with_a_one_time_code(api, settings):
    settings.OTP_DEV_MODE = True
    assert api.post_json('auth/otp/request', {'phone': '123'})[0] == 400
    code = api.post_json('auth/otp/request', {'phone': '98765 43210'})[1]['devCode']
    wrong = str((int(code) % 899999) + 100001)
    assert api.post_json('auth/otp/verify', {'phone': '9876543210', 'code': wrong, 'name': 'Asha', 'consent': True})[0] == 400
    status, ok = api.post_json('auth/otp/verify', {'phone': '9876543210', 'code': code, 'name': 'Asha', 'consent': True})
    assert status == 200 and ok['user']['phone'] == '+919876543210' and ok['isNew']
    assert api.post_json('auth/otp/verify', {'phone': '9876543210', 'code': code})[0] == 400, 'a code only works once'


def test_too_many_wrong_codes_kills_the_code(api, settings):
    settings.OTP_DEV_MODE = True
    code = api.post_json('auth/otp/request', {'phone': '9000000001'})[1]['devCode']
    wrong = str((int(code) % 899999) + 100001)
    for _ in range(5):
        api.post_json('auth/otp/verify', {'phone': '9000000001', 'code': wrong})
    assert api.post_json('auth/otp/verify', {'phone': '9000000001', 'code': code, 'name': 'X', 'consent': True})[0] == 429


def test_code_is_never_shown_outside_dev_mode(api, settings):
    settings.OTP_DEV_MODE = False
    assert api.get_json('auth/config')[1] == {'phone': False, 'devOtp': False, 'supabase': None}
    status, body = api.post_json('auth/otp/request', {'phone': '9000000002'})
    assert status == 503 and 'devCode' not in body


def test_codes_go_through_twilio_when_set_up(api, monkeypatch, settings):
    settings.OTP_DEV_MODE = True
    for k, v in {'TWILIO_SID': 'sid', 'TWILIO_TOKEN': 'tok', 'TWILIO_FROM': '+15550000000'}.items():
        monkeypatch.setenv(k, v)
    sent = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        sent.append(req)
        return FakeResponse()

    monkeypatch.setattr('kitchen.security.urllib.request.urlopen', fake_urlopen)
    status, body = api.post_json('auth/otp/request', {'phone': '9000000003'})
    assert status == 200 and 'devCode' not in body
    assert len(sent) == 1 and 'twilio.com' in sent[0].full_url and b'Your+Ballava+code+is' in sent[0].data


# ---------------------------------------------------------------- family data
def test_family_data_needs_a_sign_in(api):
    assert api.get_json('state')[0] == 401
    assert api.post_json('state', {'key': 'pantry', 'value': []})[0] == 401
    assert api.get_json('account/export')[0] == 401


def test_saved_data_comes_back_on_another_phone(make_user):
    c = make_user()
    pantry = [{'id': 'tomato', 'addedAt': 1}]
    assert c.post_json('state', {'key': 'pantry', 'value': pantry, 'baseVersion': 0}) == (200, {'version': 1})
    other = Api()
    other.post_json('auth/login', {'email': c.email, 'password': PW})
    assert other.get_json('state')[1]['items']['pantry'] == {'value': pantry, 'version': 1}


def test_unknown_data_types_are_refused(make_user):
    assert make_user().post_json('state', {'key': 'role', 'value': 'admin'})[0] == 400


def test_two_people_editing_at_once(make_user):
    c = make_user()
    c.post_json('state', {'key': 'shopping', 'value': [{'id': 'a'}], 'baseVersion': 0})
    status, stale = c.post_json('state', {'key': 'shopping', 'value': [{'id': 'b'}], 'baseVersion': 0})
    assert status == 409 and stale['value'] == [{'id': 'a'}] and stale['version'] == 1


def test_families_cannot_see_each_other(make_user):
    a, b = make_user(), make_user()
    a.post_json('state', {'key': 'members', 'value': [{'name': 'Secret', 'diabetic': True}], 'baseVersion': 0})
    assert b.get_json('state')[1]['items'] == {}


def test_family_code_shares_one_kitchen(make_user):
    a, b = make_user(), make_user()
    a.post_json('state', {'key': 'pantry', 'value': [{'id': 'rice'}], 'baseVersion': 0})
    code = a.get_json('me')[1]['household']['inviteCode']
    assert b.post_json('household/join', {'code': 'WRONG123'})[0] == 404
    assert b.post_json('household/join', {'code': code.lower()})[0] == 200
    assert b.get_json('state')[1]['items']['pantry']['value'] == [{'id': 'rice'}]
    assert len(a.get_json('me')[1]['household']['people']) == 2
    assert Household.objects.count() == 1, "b's empty family was tidied away"


def test_download_and_delete_my_data(make_user):
    c = make_user()
    c.post_json('state', {'key': 'pantry', 'value': [{'id': 'dal'}], 'baseVersion': 0})
    assert c.get_json('account/export')[1]['data']['pantry']['value'] == [{'id': 'dal'}]
    assert c.post_json('account/delete', {'confirm': 'no'})[0] == 400
    assert c.post_json('account/delete', {'confirm': 'DELETE'})[0] == 200
    assert not User.objects.filter(email=c.email).exists()
    assert FamilyData.objects.count() == 0, 'family data is deleted too'
    assert Api().post_json('auth/login', {'email': c.email, 'password': PW})[0] == 401


def test_leaving_a_shared_family_keeps_data_for_the_others(make_user):
    a, b = make_user(), make_user()
    a.post_json('state', {'key': 'pantry', 'value': [{'id': 'rice'}], 'baseVersion': 0})
    b.post_json('household/join', {'code': a.get_json('me')[1]['household']['inviteCode']})
    a.post_json('account/delete', {'confirm': 'DELETE'})
    assert b.get_json('state')[1]['items']['pantry']['value'] == [{'id': 'rice'}]


# ---------------------------------------------------------------- family vote
def test_family_vote(make_user):
    c = make_user()
    options = [{'id': 'rajma_masala', 'name': 'Rajma'}, {'id': 'chole', 'name': 'Chole'}]
    assert Api().post_json('polls', {'options': options})[0] == 401
    assert c.post_json('polls', {'options': options[:1]})[0] == 400
    token = c.post_json('polls', {'title': 'Dinner?', 'date': '2026-11-08', 'slot': 'dinner', 'options': options})[1]['token']
    guest = Api()
    assert guest.post_json(f'polls/{token}/vote', {'voter': 'v1', 'optionId': 'pizza'})[0] == 400
    guest.post_json(f'polls/{token}/vote', {'voter': 'v1', 'optionId': 'chole', 'name': 'Riya'})
    guest.post_json(f'polls/{token}/vote', {'voter': 'v2', 'optionId': 'chole'})
    _, changed = guest.post_json(f'polls/{token}/vote', {'voter': 'v1', 'optionId': 'rajma_masala'})
    assert [o['votes'] for o in changed['options']] == [1, 1] and changed['total'] == 2
    assert 'household' not in str(changed)
    assert guest.get_json('polls/nope')[0] == 404


def day(n=1):
    return (timezone.localdate() + timedelta(days=n)).isoformat()


DINNER = [{'id': 'rajma_masala', 'name': 'Rajma'}, {'id': 'chole', 'name': 'Chole'}, {'id': 'poha', 'name': 'Poha'}]


def open_ballot(c, *slots):
    status, made = c.post_json('ballots', {'meals': [{'date': day(), 'slot': s, 'options': DINNER} for s in slots or ['dinner']]})
    assert status == 200, made
    return made


def test_sharing_a_plan_opens_a_vote_for_every_meal(make_user):
    c = make_user()
    assert Api().post_json('ballots', {'meals': [{'date': day(), 'slot': 'dinner', 'options': DINNER}]})[0] == 401
    for bad in ([], [{'date': 'soon', 'slot': 'dinner', 'options': DINNER}], [{'date': day(), 'slot': 'brunch', 'options': DINNER}],
                [{'date': day(), 'slot': 'dinner', 'options': DINNER[:1]}], 'all'):
        assert c.post_json('ballots', {'meals': bad})[0] == 400, bad
    made = open_ballot(c, 'lunch', 'dinner')
    assert [m['slot'] for m in made['meals']] == ['lunch', 'dinner']
    assert not any(m['closed'] or m['total'] for m in made['meals'])
    # Family members open it without an account, and never learn whose family it is.
    guest = Api().get_json('ballots/' + made['group'])
    assert guest[0] == 200 and [m['title'] for m in guest[1]['meals']] == ['Lunch', 'Dinner']
    assert c.email not in str(guest[1]) and 'household' not in str(guest[1])
    assert Api().get_json('ballots/nope')[0] == 404


def test_one_short_link_holds_everything_that_was_sent(make_user):
    c = make_user()
    meals = [{'date': day(n), 'slot': s, 'options': DINNER, 'fast': 'Nomulu' if n == 2 else ''} for n in (1, 2) for s in ('lunch', 'dinner')]
    made = c.post_json('ballots', {'meals': meals, 'note': '  Guests on Sunday! ' + 'x' * 300})[1]
    assert len(made['group']) == 10 and made['group'].isalnum()
    seen = Api().get_json('ballots/' + made['group'])[1]
    assert seen['note'].startswith('Guests on Sunday!') and len(seen['note']) == 200
    assert [(m['date'], m['title']) for m in seen['meals']] == [(day(1), 'Lunch'), (day(1), 'Dinner'), (day(2), 'Lunch (Nomulu)'), (day(2), 'Dinner (Nomulu)')]
    rajma = seen['meals'][0]['options'][0]
    assert rajma['diet'] == 'veg' and rajma['kcal'] > 0 and rajma['time'] > 0
    page = Api().get('/v/' + made['group']).content.decode()
    assert 'Guests on Sunday!' in page and '4 meals to choose' in page
    script = c.post_json('ballots', {'meals': meals[:1], 'note': '<script>alert(1)</script>'})[1]['group']
    assert '<script>alert' not in Api().get('/v/' + script).content.decode()


def test_votes_from_whatsapp_show_names_leaders_and_ties(make_user):
    c = make_user()
    made = open_ballot(c)
    token = made['meals'][0]['token']
    vote = lambda who, dish, name='': Api().post_json(f'polls/{token}/vote', {'voter': who, 'optionId': dish, 'name': name})[1]
    assert vote('phone1', 'chole', 'Riya')['mine'] == 'chole'
    vote('phone2', 'rajma_masala', 'Dadaji')
    tie = vote('phone3', 'rajma_masala')
    assert tie['leaders'] == ['rajma_masala'] and tie['total'] == 3
    vote('phone3', 'chole')  # changing your mind moves the vote, it doesn't add one
    seen = c.get_json('ballots/' + made['group'])[1]['meals'][0]
    assert {o['id']: o['votes'] for o in seen['options']} == {'rajma_masala': 1, 'chole': 2, 'poha': 0}
    assert next(o for o in seen['options'] if o['id'] == 'chole')['voters'] == ['Riya'] and seen['leaders'] == ['chole']
    vote('phone4', 'rajma_masala')
    assert set(c.get_json('ballots/' + made['group'])[1]['meals'][0]['leaders']) == {'rajma_masala', 'chole'}
    assert Api().get_json(f'ballots/{made["group"]}?voter=phone1')[1]['meals'][0]['mine'] == 'chole'


def test_a_signed_in_voter_counts_once_and_cannot_be_imitated(make_user):
    c = make_user()
    token = open_ballot(c)['meals'][0]['token']
    c.post_json(f'polls/{token}/vote', {'voter': 'phone', 'optionId': 'chole'})
    again = c.post_json(f'polls/{token}/vote', {'voter': 'laptop', 'optionId': 'poha'})[1]
    assert again['total'] == 1 and again['mine'] == 'poha'
    guest = Api().post_json(f'polls/{token}/vote', {'voter': f'u:{c.id}', 'optionId': 'chole'})[1]
    assert guest['total'] == 2, 'a guest using someone else\'s id is just another guest'


def test_a_vote_closes_after_the_day_of_the_meal(make_user):
    c = make_user()
    made = open_ballot(c)
    closes = timezone.localtime(Poll.objects.get(group=made['group']).closes_at)
    assert closes.date().isoformat() == day(2) and closes.hour == 0
    Poll.objects.update(closes_at=timezone.now() - timedelta(minutes=1))
    token = made['meals'][0]['token']
    assert Api().post_json(f'polls/{token}/vote', {'voter': 'late', 'optionId': 'chole'})[0] == 410
    assert Api().get_json('ballots/' + made['group'])[1]['meals'][0]['closed']


def test_whatsapp_link_previews_without_voting(make_user):
    c = make_user()
    made = open_ballot(c)
    r = Api().get(f'/v/{made["group"]}/0-1')
    page = r.content.decode()
    assert r.status_code == 200 and f'/#/vote/{made["group"]}/0-1' in page and 'og:title' in page
    assert Api().get(f'/v/{made["group"]}').status_code == 200
    assert b'not found' in Api().get('/v/nope').content
    assert Api().get('/v/nope/0-1%22%3E%3Cscript%3E').content.find(b'<script>') == -1
    assert Vote.objects.count() == 0, 'WhatsApp opening the link to preview it is not a vote'


def test_shared_links_never_point_at_localhost_when_there_is_a_better_address(make_user, settings):
    c = make_user()
    settings.ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.1.50', 'testserver']
    body = {'meals': [{'date': day(), 'slot': 'dinner', 'options': DINNER}]}
    assert c.post_json('ballots', body, HTTP_HOST='localhost:8000')[1]['shareBase'] == 'http://192.168.1.50:8000'
    assert c.post_json('ballots', body, HTTP_HOST='192.168.1.50:8000')[1]['shareBase'] == 'http://192.168.1.50:8000'
    settings.PUBLIC_URL = 'https://ballava.example'
    group = c.post_json('ballots', body, HTTP_HOST='localhost:8000')[1]
    assert group['shareBase'] == 'https://ballava.example'
    assert c.get_json('ballots/' + group['group'])[1]['shareBase'] == 'https://ballava.example'


# ---------------------------------------------------------------- Ballava Chef: saved chats
def chat(id_='chat0001', at=1000, **over):
    return {'id': id_, 'title': 'Chicken biryani?', 'at': at, 'messages': [
        {'from': 'bot', 'text': 'Hi! I am Ballava Chef.'},
        {'from': 'me', 'text': 'Give me chicken biryani', 'at': at},
        {'from': 'bot', 'text': 'Here it is.', 'recipeId': 'ai_x1', 'dishes': ['chole'], 'followups': ['Veg version?'], 'warning': 'Amma is veg',
         'secret': 'dropped', 'at': at}], **over}


def test_chats_are_saved_in_your_account(make_user):
    c = make_user()
    assert c.post_json('chats', chat())[0] == 200
    assert c.post_json('chats', chat('chat0002', at=2000, title='Tiffin ideas'))[0] == 200
    status, body = c.get_json('chats')
    assert status == 200 and [x['id'] for x in body['chats']] == ['chat0002', 'chat0001'], 'newest first'
    saved = body['chats'][1]['messages'][2]
    assert saved['recipeId'] == 'ai_x1' and saved['followups'] == ['Veg version?'] and 'secret' not in saved, 'only known fields are kept'
    c.post_json('chats', chat(at=3000, title='Chicken biryani, again'))  # the same chat, updated
    assert c.get_json('chats')[1]['chats'][0]['title'] == 'Chicken biryani, again'


def test_chats_survive_signing_out_and_stay_private(make_user):
    c = make_user()
    c.post_json('chats', chat())
    c.post_json('auth/logout', {})
    assert Api().get_json('chats')[0] == 401, 'guests keep chats on their phone only'
    again = Api()
    again.post_json('auth/login', {'email': c.email, 'password': 'kadai-masala-42'})
    assert [x['id'] for x in again.get_json('chats')[1]['chats']] == ['chat0001'], 'back after signing in again'
    other = make_user()
    assert other.get_json('chats')[1]['chats'] == [], "nobody else sees them, not even family"


def test_chat_limits_and_deleting(make_user):
    c = make_user()
    assert c.post_json('chats', chat('bad id!'))[0] == 400
    long = chat(messages=[{'from': 'me', 'text': 'x' * 4500}] * 150)
    assert c.post_json('chats', long)[0] == 200
    kept = c.get_json('chats')[1]['chats'][0]['messages']
    assert len(kept) == 100 and len(kept[0]['text']) == 4000
    for n in range(52):
        c.post_json('chats', chat(f'many{n:04d}', at=10_000 + n))
    assert len(c.get_json('chats')[1]['chats']) == 50, 'the newest 50 are kept'
    c.post_json('chats/delete', {'id': 'many0051'})
    assert 'many0051' not in [x['id'] for x in c.get_json('chats')[1]['chats']]
    c.post_json('chats/delete', {'all': True})
    assert c.get_json('chats')[1]['chats'] == []


def test_chats_are_in_your_download_and_go_with_your_account(make_user):
    from kitchen.models import ChatThread
    c = make_user()
    c.post_json('chats', chat())
    assert c.get_json('account/export')[1]['chats'][0]['title'] == 'Chicken biryani?'
    c.post_json('account/delete', {'confirm': 'DELETE'})
    assert ChatThread.objects.count() == 0
