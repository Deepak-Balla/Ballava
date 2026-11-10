"""Tests for sign-in, family data, family codes, voting and "my data"."""
import pytest
from django.contrib.auth.models import User

from kitchen.models import FamilyData, Household
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
    assert api.get_json('auth/config')[1] == {'phone': False, 'devOtp': False}
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
