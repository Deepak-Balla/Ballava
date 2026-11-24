"""Tests for running Ballava online: sign-in with Supabase, the database setting, hosting settings, and moving data."""
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, RequestFactory
from django.utils import timezone

from config import database
from kitchen import retention, supabase
from kitchen.models import FamilyData, Festival, Household, Profile
from kitchen.security import client_ip
from .conftest import Api
from .fake_supabase import PUBLISHABLE, SECRET, FakeSupabase

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def auth(settings):
    fake = FakeSupabase()
    settings.SUPABASE_URL = settings.SUPABASE_AUTH_URL = fake.url
    settings.SUPABASE_PUBLISHABLE_KEY, settings.SUPABASE_SECRET_KEY = PUBLISHABLE, SECRET
    supabase._settings.update(at=0.0, data=None)
    yield fake
    supabase._settings.update(at=0.0, data=None)
    fake.stop()


def enter(token, client=None, **body):
    c = client or Api()
    return (*c.post_json('auth/supabase', {'accessToken': token, **body}), c)


# ---------------------------------------------------------------- signing in
def test_a_new_person_agrees_first_and_then_has_an_account(auth):
    token = auth.token(auth.add('Riya@Example.com'.lower(), name='Riya'))
    status, body, c = enter(token)
    assert (status, body) == (200, {'needsConsent': True, 'name': 'Riya', 'email': 'riya@example.com'})
    assert User.objects.count() == 0 and c.get_json('me')[1] == {'user': None}, 'nothing is made before they agree'
    status, body, c = enter(token, consent=True, name='Riya K')
    assert status == 200 and body['isNew'] and body['user']['name'] == 'Riya K' and body['user']['email'] == 'riya@example.com'
    me = c.get_json('me')[1]
    assert me['user']['name'] == 'Riya K' and me['household']['inviteCode'], 'our own session, and a family'
    assert Profile.objects.get().consent_at and not User.objects.get().has_usable_password()
    # Next time they go straight in, on any device.
    status, body, c2 = enter(auth.token(auth.users['riya@example.com']))
    assert status == 200 and not body['isNew'] and c2.get_json('me')[1]['user']['id'] == me['user']['id']
    c2.post_json('auth/logout')
    assert c2.get_json('me')[1] == {'user': None}


@pytest.mark.parametrize('token', ['', None, 'x' * 30, 'has space ' * 5, 'y' * 6000, {'a': 1}])
def test_made_up_tokens_never_work(auth, token):
    assert enter(token, consent=True)[0] == 401 and User.objects.count() == 0


def test_unconfirmed_and_anonymous_people_cannot_enter(auth):
    unconfirmed = auth.add('new@example.com', confirmed=False)
    status, body, _ = enter(auth.token(unconfirmed), consent=True)
    assert status == 403 and 'confirm your email' in body['error']
    ghost = auth.add('ghost@example.com')
    ghost['is_anonymous'] = True
    assert enter(auth.token(ghost), consent=True)[0] == 403
    nobody = auth.add('phone@example.com')
    nobody['email'] = ''
    auth.users[''] = nobody
    assert enter(auth.token(nobody), consent=True)[0] == 403
    assert User.objects.count() == 0


def old_account(email='amma@example.com'):
    """Someone who made their account before Supabase was switched on."""
    user = User.objects.create_user(email, email, 'old-password-123', first_name='Amma')
    home = Household.objects.create(name="Amma's family")
    Profile.objects.create(user=user, household=home, consent_at=timezone.now())
    FamilyData.objects.create(household=home, key='pantry', value=[{'id': 'rice'}])
    return user


def test_people_who_had_an_account_keep_everything(auth):
    user = old_account()
    old_session = Api()
    old_session.force_login(user)
    status, body, c = enter(auth.token(auth.add('amma@example.com')))
    assert status == 200 and body['user']['id'] == str(user.pk) and not body['isNew']
    assert c.get_json('state')[1]['items']['pantry']['value'] == [{'id': 'rice'}]
    assert not User.objects.get().has_usable_password(), 'the old password opens nothing any more'
    assert old_session.get_json('me')[1] == {'user': None}, 'and whoever was signed in with it is signed out'


def test_nobody_can_take_over_an_account_with_an_unchecked_email(auth):
    old_account()
    auth.autoconfirm = True  # "Confirm email" is off in Supabase: anyone could claim any address
    status, body, c = enter(auth.token(auth.add('amma@example.com')), consent=True)
    assert status == 409 and 'already exists' in body['error'] and c.get_json('me')[1] == {'user': None}
    unverified = auth.add('amma@example.com', provider='google', email_verified=False)
    assert enter(auth.token(unverified))[0] == 409
    assert enter(auth.token(auth.add('amma@example.com', provider='google')))[0] == 200, "Google's word is enough"


def test_if_supabase_cannot_say_whether_emails_are_checked_assume_not(auth, monkeypatch):
    old_account()
    monkeypatch.setattr(supabase, 'project_settings', lambda: {})
    assert enter(auth.token(auth.add('amma@example.com')))[0] == 409


def test_admins_and_disabled_people_cannot_enter_this_way(auth):
    User.objects.create_superuser('boss@example.com', 'boss@example.com', 'admin-secret-pass-123')
    assert enter(auth.token(auth.add('boss@example.com')), consent=True)[0] == 403
    user = old_account()
    User.objects.filter(pk=user.pk).update(is_active=False)
    assert enter(auth.token(auth.add('amma@example.com')), consent=True)[0] == 403


def test_a_changed_email_is_followed_but_never_onto_someone_else(auth):
    a = auth.add('a@example.com')
    enter(auth.token(a), consent=True)
    auth.users['a2@example.com'] = {**a, 'email': 'a2@example.com'}
    status, body, _ = enter(auth.token(auth.users['a2@example.com']))
    assert body['user']['email'] == 'a2@example.com' and User.objects.count() == 1
    old_account('taken@example.com')
    auth.users['taken@example.com'] = {**a, 'email': 'taken@example.com'}
    status, body, _ = enter(auth.token(auth.users['taken@example.com']))
    assert status == 200 and body['user']['email'] == 'a2@example.com', 'still their own account'


def test_our_own_passwords_are_off_when_supabase_is_on(auth):
    old_account()
    assert Api().post_json('auth/login', {'email': 'amma@example.com', 'password': 'old-password-123'})[0] == 403
    assert Api().post_json('auth/signup', {'name': 'X', 'email': 'x@example.com', 'password': 'kadai-masala-42', 'consent': True})[0] == 403
    assert Client().get('/admin/login/').status_code == 200, 'admins still sign in at /admin'


def test_the_sign_in_screen_gets_only_public_settings(auth):
    got = Api().get_json('auth/config')[1]['supabase']
    assert got == {'url': auth.url, 'key': PUBLISHABLE, 'google': True, 'signup': True}
    assert SECRET not in json.dumps(got)
    auth.google = False
    assert Api().get_json('auth/config')[1]['supabase']['google'] is True, 'remembered for a few minutes'
    supabase._settings.update(at=0.0, data=None)
    assert Api().get_json('auth/config')[1]['supabase']['google'] is False


def test_supabase_being_down_is_said_kindly(auth, settings):
    token = auth.token(auth.add('a@example.com'))
    auth.down = True
    assert Api().get_json('auth/config')[1]['supabase']['google'] is False
    assert enter(token, consent=True)[0] == 401
    settings.SUPABASE_AUTH_URL = 'http://127.0.0.1:9'
    status, body, _ = enter(token, consent=True)
    assert status == 503 and 'could not be reached' in body['error']


def test_deleting_an_account_deletes_the_sign_in_too(auth, settings):
    _, _, c = enter(auth.token(auth.add('a@example.com')), consent=True)
    assert c.post_json('account/delete', {'confirm': 'DELETE'})[0] == 200
    assert 'a@example.com' not in auth.users and User.objects.count() == 0
    # Without the secret key it can't, and that never gets in the way of deleting here.
    settings.SUPABASE_SECRET_KEY = ''
    _, _, c = enter(auth.token(auth.add('b@example.com')), consent=True)
    assert c.post_json('account/delete', {'confirm': 'DELETE'})[0] == 200 and User.objects.count() == 0
    assert 'b@example.com' in auth.users
    settings.SUPABASE_SECRET_KEY = SECRET
    _, _, c = enter(auth.token(auth.add('c@example.com')), consent=True)
    auth.down = True
    assert c.post_json('account/delete', {'confirm': 'DELETE'})[0] == 200 and User.objects.count() == 0


def test_the_6_month_clean_up_deletes_the_sign_in_too(auth):
    enter(auth.token(auth.add('a@example.com')), consent=True)
    long_ago = timezone.now() - timedelta(days=300)
    User.objects.update(date_joined=long_ago)
    Profile.objects.update(last_seen=long_ago)
    assert retention.cleanup()['accounts'] == 1 and 'a@example.com' not in auth.users


def test_supabase_sign_in_is_off_unless_set_up(api):
    assert api.get_json('auth/config')[1]['supabase'] is None
    assert api.post_json('auth/supabase', {'accessToken': 'x' * 40})[0] == 404


def test_too_many_tries_are_slowed_down(auth):
    c = Api()
    assert 429 in [enter('x' * 40, c)[0] for _ in range(45)]


@pytest.mark.parametrize('key', ['sb_secret_abc', 'eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.sig'])
def test_a_secret_key_in_the_public_place_stops_the_server(settings, key):
    settings.SUPABASE_PUBLISHABLE_KEY = key
    with pytest.raises(ImproperlyConfigured):
        supabase.check_keys()
    for fine in ('', 'sb_publishable_abc', 'eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.sig', 'a.b.c'):
        settings.SUPABASE_PUBLISHABLE_KEY = fine
        supabase.check_keys()


# ---------------------------------------------------------------- the database setting
def test_database_url_is_understood():
    db = database.from_url('postgresql://postgres.abc:p%40ss%2Fword@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres')
    assert (db['USER'], db['PASSWORD'], db['HOST'], db['PORT'], db['NAME']) == ('postgres.abc', 'p@ss/word', 'aws-0-ap-southeast-1.pooler.supabase.com', '5432', 'postgres')
    assert db['OPTIONS']['sslmode'] == 'require' and db['CONN_MAX_AGE'] == 60, 'always encrypted over the internet'
    pooled = database.from_url('postgres://u:p@x.pooler.supabase.com:6543/postgres')
    assert pooled['CONN_MAX_AGE'] == 0 and pooled['DISABLE_SERVER_SIDE_CURSORS']
    assert database.from_url('postgres://u:p@localhost/x')['OPTIONS']['sslmode'] == 'prefer'
    assert database.from_url('postgres://u:p@db.example.com/x?sslmode=verify-full')['OPTIONS']['sslmode'] == 'verify-full'
    for bad in ('mysql://u:p@h/x', 'nonsense'):
        with pytest.raises(ValueError):
            database.from_url(bad)


# ---------------------------------------------------------------- hosting
def online(**env):
    """Ballava's settings as they would be online."""
    code = ("import json, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'\nfrom django.conf import settings as s\n"
            "print(json.dumps({k: getattr(s, k, None) for k in ('DEBUG','ALLOWED_HOSTS','CSRF_TRUSTED_ORIGINS','PUBLIC_URL','CLIENT_IP_HEADER','SESSION_COOKIE_SECURE','SECURE_SSL_REDIRECT','SUPABASE_AUTH_URL','SECURE_CSP')}, default=str))")
    clean = {k: v for k, v in os.environ.items() if not k.startswith(('DJANGO', 'SUPABASE', 'RENDER', 'PUBLIC_URL', 'DATABASE', 'SITE_'))}
    blank = {k: '' for k in ('DJANGO_ALLOWED_HOSTS', 'DJANGO_CSRF_TRUSTED_ORIGINS', 'SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY', 'SUPABASE_SECRET_KEY', 'DATABASE_URL', 'SITE_DOMAIN', 'PUBLIC_URL')}
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env={**clean, **blank, **env}, capture_output=True, text=True, check=False)
    return json.loads(r.stdout) if r.returncode == 0 else r.stderr


def test_settings_on_a_hosting_service(tmp_path):
    host = {'RENDER': 'true', 'RENDER_EXTERNAL_HOSTNAME': 'x.onrender.com', 'RENDER_EXTERNAL_URL': 'https://x.onrender.com', 'DATA_DIR': str(tmp_path)}
    s = online(**host, DJANGO_SECRET_KEY='k' * 60)
    assert s['DEBUG'] is False and 'x.onrender.com' in s['ALLOWED_HOSTS'] and '*' not in s['ALLOWED_HOSTS']
    assert s['SESSION_COOKIE_SECURE'] and s['SECURE_SSL_REDIRECT'] and s['PUBLIC_URL'] == 'https://x.onrender.com'
    s = online(**host, DJANGO_SECRET_KEY='k' * 60, SITE_DOMAIN='https://www.Ballava.com/', SUPABASE_URL='https://abc.supabase.co/', SUPABASE_PUBLISHABLE_KEY='sb_publishable_x')
    assert {'ballava.com', 'www.ballava.com', 'x.onrender.com'} <= set(s['ALLOWED_HOSTS'])
    assert 'https://ballava.com' in s['CSRF_TRUSTED_ORIGINS'] and s['PUBLIC_URL'] == 'https://ballava.com'
    assert s['SUPABASE_AUTH_URL'] == 'https://abc.supabase.co/auth/v1' and 'https://abc.supabase.co' in s['SECURE_CSP']['connect-src']
    assert 'DJANGO_SECRET_KEY' in online(**host, DJANGO_SECRET_KEY=''), 'refuses to start with a key that changes on every restart'
    home = online(DATA_DIR=str(tmp_path))
    assert home['DEBUG'] is True and not home['SESSION_COOKIE_SECURE'], 'nothing changes on your own computer'


def test_health_check_answers_whatever_the_address(settings):
    settings.ALLOWED_HOSTS = ['ballava.com']
    assert Client().get('/healthz', HTTP_HOST='10.0.0.7').content == b'ok'
    assert Client().get('/api/health', HTTP_HOST='evil.com').status_code == 400


def test_each_visitor_is_counted_separately_behind_a_proxy(settings):
    ask = lambda **h: client_ip(RequestFactory().get('/', REMOTE_ADDR='10.0.0.1', **h))  # noqa: E731
    assert ask(HTTP_CF_CONNECTING_IP='203.0.113.9') == '10.0.0.1', 'never trusted unless the server says so'
    settings.CLIENT_IP_HEADER = 'CF-Connecting-IP'
    assert ask(HTTP_CF_CONNECTING_IP='203.0.113.9') == '203.0.113.9'
    assert ask(HTTP_CF_CONNECTING_IP='2001:db8::1') == '2001:db8::1'
    for odd in ('', 'x', '1.2.3.4, 5.6.7.8', "'; drop table"):
        assert ask(HTTP_CF_CONNECTING_IP=odd) == '10.0.0.1'


# ---------------------------------------------------------------- moving to another database
def test_everything_moves_to_another_database(make_user, tmp_path):
    c = make_user()
    c.post_json('state', {'key': 'pantry', 'value': [{'id': 'rice'}], 'baseVersion': 0})
    User.objects.create_superuser('boss@example.com', 'boss@example.com', 'admin-secret-pass-123')
    Festival.objects.create(name='Nomulu', date='2026-11-23', fast=True)
    before = (User.objects.count(), Household.objects.get().invite_code, FamilyData.objects.get().value)
    file = str(tmp_path / 'backup.json')
    call_command('export_data', file, verbosity=0)
    with pytest.raises(CommandError, match='already has data'):
        call_command('import_data', file)
    for m in (User, Household, Festival, FamilyData):
        m.objects.all().delete()
    call_command('import_data', file)
    assert (User.objects.count(), Household.objects.get().invite_code, FamilyData.objects.get().value) == before
    assert Festival.objects.get().name == 'Nomulu' and Profile.objects.get().household
    again = Api()
    assert again.post_json('auth/login', {'email': c.email, 'password': 'kadai-masala-42'})[0] == 200, 'people can still sign in'
    assert make_user.__call__ and User.objects.create_user('new@x.test').pk > 0, 'and new rows get new numbers'
