"""Real-browser test of Help & support: someone sends a problem from their phone, an admin answers it in the
admin portal, and the answer shows in the app.   Run: pytest -m e2e"""
import re

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from kitchen.api import new_family_user
from kitchen.models import SupportRequest
from .e2e_helpers import DESKTOP, browser, device, errors, more, no_sideways_scroll, site, snap, tab  # noqa: F401

pytestmark = pytest.mark.e2e

ADMIN = {'email': 'admin@ballava.test', 'password': 'admin-secret-pass-123'}
MEERA = {'name': 'Meera', 'email': 'meera@ballava.test', 'password': 'kadai-masala-42'}


@pytest.fixture(scope='module')
def people(site):
    User.objects.create_superuser(ADMIN['email'], ADMIN['email'], ADMIN['password'])
    new_family_user(MEERA['name'], email=MEERA['email'], password=MEERA['password'])


@pytest.fixture(scope='module')
def phone(device, site, people):
    p = device()
    p.goto(site)
    p.get_by_label('Email').fill(MEERA['email'])
    p.get_by_label('Password').fill(MEERA['password'])
    p.get_by_role('button', name='Sign in', exact=True).last.click()
    p.get_by_role('navigation', name='Main').wait_for()
    return p


def test_send_a_problem_to_the_team(phone):
    more(phone, 'Help & support')
    phone.get_by_text('No requests yet').wait_for()
    phone.get_by_role('button', name='➕ New request').click()
    phone.get_by_role('button', name=re.compile('A recipe or ingredient is wrong')).click()
    phone.get_by_label('In a few words').fill('Paneer tikka says it is vegan')
    phone.get_by_label('What happened?').fill('The recipe page shows a vegan tag,\nbut it has paneer and curd.')
    snap(phone, '40-support-new')
    no_sideways_scroll(phone, 'new support request')
    phone.get_by_role('button', name='Send to the team').click()
    phone.get_by_role('heading', name=re.compile(r'Request #\d+')).wait_for()
    expect(phone.locator('.bubble.me')).to_contain_text('but it has paneer and curd.')
    phone.get_by_role('status').get_by_text('Sent. The team will answer here.').wait_for()
    phone.locator('.note.info', has_text='The team will answer here').wait_for()
    ticket = SupportRequest.objects.get()
    assert ticket.category == 'recipe' and ticket.status == 'open' and ticket.device, 'the browser is kept to help find the problem'


def test_an_admin_answers_it_in_the_portal(device, site):
    admin = device(DESKTOP)
    admin.goto(site + 'admin/')
    admin.get_by_label('Email').or_(admin.get_by_label('Username')).first.fill(ADMIN['email'])
    admin.get_by_label('Password').fill(ADMIN['password'])
    admin.get_by_role('button', name='Log in').click()
    expect(admin.locator('.ballava-nav .b-count')).to_have_text('1')
    admin.get_by_role('link', name=re.compile('Paneer tikka says it is vegan')).first.click()
    expect(admin.locator('.b-thread')).to_contain_text('but it has paneer and curd.')
    admin.get_by_label('Your reply').fill('Thank you, Meera! The vegan tag is now removed.')
    snap(admin, '41-support-admin')
    admin.get_by_role('button', name='Save', exact=True).click()
    admin.get_by_text(re.compile('Reply sent')).wait_for()
    expect(admin.locator('.ballava-nav .b-count')).to_have_count(0)
    assert SupportRequest.objects.get().status == 'in_progress'


def test_the_answer_shows_in_the_app(phone, errors):
    tab(phone, 'Dashboard')
    phone.evaluate("window.dispatchEvent(new Event('focus'))")  # coming back to the app checks for replies
    nav = phone.get_by_role('navigation', name='Main')
    nav.get_by_role('button', name='More, 1 new reply from the Ballava team').click()
    phone.get_by_role('button', name='Help & support, 1 new reply from the team').click()
    phone.get_by_text('New reply').wait_for()
    phone.locator('.support-list .menu-item').first.click()
    expect(phone.locator('.bubble.team')).to_contain_text('The vegan tag is now removed.')
    expect(phone.locator('.bubble.team')).to_contain_text('Ballava team')
    snap(phone, '42-support-reply')
    no_sideways_scroll(phone, 'support conversation')
    expect(nav.get_by_role('button', name='More', exact=True)).to_be_visible()  # the red dot goes once it's read

    phone.get_by_role('button', name='✓ My problem is solved').click()
    phone.get_by_text('This is resolved').wait_for()
    expect(phone.locator('.card .pill')).to_have_text('Resolved')
    assert SupportRequest.objects.get().status == 'resolved'
    assert not errors, errors
