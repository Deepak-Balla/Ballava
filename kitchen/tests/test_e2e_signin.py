"""Real-browser test of signing in with Supabase (a stand-in for it: see fake_supabase.py).   Run: pytest -m e2e"""
import re

import pytest
from playwright.sync_api import expect

from kitchen import supabase
from .e2e_helpers import browser, device, errors, more, no_sideways_scroll, site, snap  # noqa: F401
from .fake_supabase import CODE, PUBLISHABLE, SECRET, FakeSupabase

pytestmark = pytest.mark.e2e
PASSWORD = 'kadai-masala-42'


@pytest.fixture(scope='module')
def auth(site):
    from django.conf import settings
    fake = FakeSupabase()
    settings.SUPABASE_URL = settings.SUPABASE_AUTH_URL = fake.url
    settings.SUPABASE_PUBLISHABLE_KEY, settings.SUPABASE_SECRET_KEY = PUBLISHABLE, SECRET
    settings.SECURE_CSP['connect-src'].append(fake.url)
    supabase._settings.update(at=0.0, data=None)
    yield fake
    settings.SUPABASE_URL = settings.SUPABASE_AUTH_URL = settings.SUPABASE_PUBLISHABLE_KEY = settings.SUPABASE_SECRET_KEY = ''
    settings.SECURE_CSP['connect-src'].remove(fake.url)
    supabase._settings.update(at=0.0, data=None)
    fake.stop()


def home(p):
    p.get_by_role('navigation', name='Main').wait_for()


def sign_in(p, site, email, password=PASSWORD):
    p.goto(site)
    p.get_by_label('Email').fill(email)
    p.get_by_label('Password', exact=True).fill(password)
    p.get_by_role('button', name='Sign in', exact=True).last.click()


def test_create_an_account_with_a_code_from_the_email(device, site, auth):
    p = device()
    p.goto(site)
    p.get_by_role('button', name='Continue with Google').wait_for()
    snap(p, '20-login-supabase')
    no_sideways_scroll(p, 'sign in')
    p.get_by_role('button', name='Create account').first.click()
    p.get_by_label('Your name').fill('Asha')
    p.get_by_label('Email').fill('Asha@Example.com')
    p.get_by_label('Password', exact=True).fill(PASSWORD)
    p.get_by_role('button', name='Create account').last.click()
    p.get_by_role('alert').get_by_text(re.compile('Please agree')).wait_for()
    p.get_by_role('checkbox').check()
    p.get_by_role('button', name='Create account').last.click()
    p.get_by_text('We sent an email to asha@example.com').wait_for()
    snap(p, '20-login-code')
    p.get_by_label('Code from the email').fill('000000')
    p.get_by_role('button', name='Confirm and continue').click()
    p.get_by_role('alert').get_by_text(re.compile('not right, or it has expired')).wait_for()
    p.get_by_role('button', name='Send the email again').click()
    p.get_by_text('A new email is on its way').wait_for()
    p.get_by_label('Code from the email').fill(CODE)
    p.get_by_role('button', name='Confirm and continue').click()
    home(p)
    more(p, 'Account')
    p.get_by_text('asha@example.com').wait_for()
    stored = p.evaluate("Object.entries(localStorage).map(e => e.join('=')).join(' ') + document.cookie")
    assert 'token-' not in stored, "Supabase's token isn't kept in the browser"
    # Still signed in after a reload; and out means out.
    p.reload()
    home(p)
    more(p, 'Account')
    p.get_by_role('button', name='Sign out').click()
    p.get_by_role('button', name='Continue with Google').wait_for()
    p.context.close()


def test_sign_in_and_wrong_passwords(device, site, auth):
    p = device()
    sign_in(p, site, 'asha@example.com', 'wrong-password')
    p.get_by_role('alert').get_by_text('That email or password is not right.').wait_for()
    p.get_by_label('Password', exact=True).fill(PASSWORD)
    p.get_by_role('button', name='Sign in', exact=True).last.click()
    home(p)
    p.context.close()


def test_signing_in_before_confirming_sends_a_new_code(device, site, auth):
    auth.add('half@example.com', confirmed=False, name='Half')
    p = device()
    sign_in(p, site, 'half@example.com')
    p.get_by_text("Your email isn't confirmed yet").wait_for()
    p.get_by_label('Code from the email').fill(CODE)
    p.get_by_role('button', name='Confirm and continue').click()
    home(p)
    p.context.close()


def test_forgotten_password(device, site, auth):
    p = device()
    p.goto(site)
    p.get_by_role('button', name='Forgot your password?').click()
    p.get_by_label('Email').fill('asha@example.com')
    p.get_by_role('button', name='Email me a code').click()
    p.get_by_text('If asha@example.com has an account, an email is on its way').wait_for()
    p.get_by_label('Code from the email').fill(CODE)
    p.get_by_label('New password').fill('new-masala-43')
    p.get_by_role('button', name='Set new password').click()
    home(p)
    p.context.close()
    p = device()
    sign_in(p, site, 'asha@example.com', 'new-masala-43')
    home(p)
    p.context.close()


def test_continue_with_google(device, site, auth):
    p = device()
    p.goto(site)
    p.get_by_role('button', name='Continue with Google').click()
    # Back from Google for the first time: agree, and you're in.
    p.get_by_role('heading', name='Welcome to Ballava!').wait_for()
    assert 'code=' not in p.url, 'the one-time code is taken out of the address bar'
    assert p.get_by_label('Your name').input_value() == 'Asha Google'
    expect(p.get_by_role('button', name='Agree and continue')).to_be_disabled()
    snap(p, '20-login-consent')
    p.get_by_role('checkbox').check()
    p.get_by_role('button', name='Agree and continue').click()
    home(p)
    p.context.close()
    # Next time there is nothing to fill in.
    p = device()
    p.goto(site)
    p.get_by_role('button', name='Continue with Google').click()
    home(p)
    p.context.close()


def test_links_from_emails_and_stolen_codes(device, site, auth):
    # The link in a reset email brings a token in the address.
    p = device()
    p.goto(f"{site}#access_token={auth.token(auth.users['asha@example.com'])}&type=recovery&expires_in=3600")
    p.get_by_role('heading', name='Choose a new password').wait_for()
    assert 'access_token' not in p.url
    p.get_by_label('New password').fill('newer-masala-44')
    p.get_by_role('button', name='Set new password').click()
    home(p)
    p.context.close()
    # A code that this browser didn't ask for is useless (someone sent you their link).
    auth.pkce['stolen'] = ('asha@example.com', 'challenge-of-another-browser')
    p = device()
    p.goto(site + '?code=stolen')
    p.get_by_role('alert').get_by_text('Please sign in again from this browser.').wait_for()
    p.goto(site + '?error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid')
    p.get_by_role('alert').get_by_text(re.compile('expired or was already used')).wait_for()
    p.context.close()


def test_the_link_in_a_standard_sign_up_email(device, site, auth):
    new = auth.add('link@example.com', name='Link')
    p = device()
    p.goto(f"{site}#access_token={auth.token(new)}&type=signup&expires_in=3600")
    p.get_by_role('heading', name='Welcome to Ballava!').wait_for()
    assert 'access_token' not in p.url
    p.get_by_role('checkbox').check()
    p.get_by_role('button', name='Agree and continue').click()
    p.get_by_role('navigation', name='Main').wait_for()
    p.context.close()


def test_no_javascript_errors(errors):
    assert errors == []
