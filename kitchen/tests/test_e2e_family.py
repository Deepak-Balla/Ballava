"""Real-browser test of the signed-in app: real Chrome, the real Django server and database, several family members.
Run: pytest -m e2e"""
import re
from urllib.parse import unquote

import pytest
from django.contrib.auth.models import User
from playwright.sync_api import expect

from .e2e_helpers import DESKTOP, browser, device, errors, more, no_sideways_scroll, site, snap, tab  # noqa: F401

pytestmark = pytest.mark.e2e

ADMIN = {'email': 'admin@ballava.test', 'password': 'admin-secret-pass-123'}
ASHA = {'name': 'Asha', 'email': 'asha@ballava.test', 'password': 'kadai-masala-42'}


@pytest.fixture(scope='module')
def page(device, site, settings_module):
    p = device()
    p.goto(site)
    return p


@pytest.fixture(scope='module')
def settings_module(site):
    from django.conf import settings
    settings.OTP_DEV_MODE = True
    User.objects.create_superuser(ADMIN['email'], ADMIN['email'], ADMIN['password'])
    yield settings
    settings.OTP_DEV_MODE = False


def sign_in(p, site, who=ASHA):
    p.goto(site)
    p.get_by_label('Email').fill(who['email'])
    p.get_by_label('Password').fill(who['password'])
    p.get_by_role('button', name='Sign in', exact=True).last.click()
    p.get_by_role('navigation', name='Main').wait_for()


def admin_sign_in(p, site, who=ADMIN):
    p.goto(site + 'admin/')
    p.get_by_label('Email').or_(p.get_by_label('Username')).first.fill(who['email'])
    p.get_by_label('Password').fill(who['password'])
    p.get_by_role('button', name='Log in').click()


def test_wrong_password_shows_a_clear_message(page):
    page.get_by_text('Cooks with you today').wait_for()
    snap(page, '20-login')
    page.get_by_label('Email').fill('nobody@ballava.test')
    page.get_by_label('Password').fill('wrong-password')
    page.get_by_role('button', name='Sign in', exact=True).last.click()
    page.get_by_role('alert').get_by_text(re.compile('not right')).wait_for()


def test_guest_data_moves_into_a_new_account(page):
    page.get_by_role('button', name='Continue without an account').click()
    page.get_by_role('button', name='Try with a sample kitchen').click()
    page.get_by_text('Cook now').wait_for()
    more(page, 'Account')
    page.get_by_role('button', name='Sign in').click()
    page.get_by_role('button', name='Create account').click()
    page.get_by_label('Your name').fill(ASHA['name'])
    page.get_by_label('Email').fill(ASHA['email'])
    page.get_by_label('Password').fill(ASHA['password'])
    page.get_by_role('button', name='Create account').last.click()
    page.get_by_role('alert').get_by_text(re.compile('agree')).wait_for()
    page.get_by_role('checkbox').check()
    page.get_by_role('button', name='Create account').last.click()
    page.get_by_role('navigation', name='Main').wait_for()
    tab(page, 'Kitchen')
    page.locator('.pantry-list .p-name', has_text='Leftover rice').wait_for()


def test_family_profile_with_age_goals_tiffin_and_dislikes(page):
    more(page, 'Family')
    page.get_by_placeholder('e.g. Amma').fill('Dadaji')
    page.get_by_label('Diabetic').check()
    page.get_by_label('Age group').select_option('senior')
    page.get_by_role('button', name='Low salt (BP)').click()
    page.get_by_role('button', name='Add member').click()
    page.get_by_text(re.compile('Added Dadaji')).wait_for()
    page.get_by_placeholder('e.g. Amma').fill('Riya')
    page.get_by_label('Age group').select_option('child')
    page.get_by_label('Spice level').select_option('1')
    page.get_by_label(re.compile('Takes a tiffin')).check()
    page.get_by_label("Doesn't like").fill('karela')
    page.get_by_role('button', name='Add member').click()
    page.get_by_text(re.compile('Added Riya')).wait_for()
    page.get_by_text('Dislikes Bitter gourd').wait_for()
    snap(page, '21-family')
    no_sideways_scroll(page, 'Family')


def test_plan_my_week_21_different_meals_and_a_tiffin(page):
    tab(page, 'Plan')
    page.get_by_role('button', name='Plan my week').click()
    page.locator('.plan-day').nth(6).wait_for()
    main = page.locator('.plan-day .plan-row').evaluate_all(
        "rows => rows.filter(r => /Breakfast|Lunch|Dinner/.test(r.querySelector('.plan-slot').textContent)).map(r => r.querySelector('.plan-dish').textContent)")
    assert len(main) == 21 and len(set(main)) == 21, main
    assert page.get_by_text('Tiffin · Riya').count() >= 1
    snap(page, '22-plan')
    no_sideways_scroll(page, 'Plan')


def test_swap_lock_and_refresh_keeps_it(page):
    day = page.locator('.plan-day').first
    before = day.locator('.plan-dish').nth(2).inner_text()
    day.get_by_role('button', name='Swap Dinner').click()
    expect(day.locator('.plan-dish').nth(2)).not_to_have_text(before)
    swapped = day.locator('.plan-dish').nth(2).inner_text()
    expect(day.get_by_role('button', name='Unlock Dinner')).to_have_count(1)
    page.get_by_role('button', name='Refresh unlocked meals').click()
    page.get_by_text(re.compile('Your week is planned')).wait_for()
    expect(day.locator('.plan-dish').nth(2)).to_have_text(swapped)


def test_groceries_for_the_plan(page):
    page.get_by_role('button', name=re.compile('items to shopping list')).click()
    page.get_by_text(re.compile('to your shopping list')).wait_for()
    tab(page, 'List')
    page.locator('.shop-list li').first.wait_for()


def test_menu_for_the_cook_in_hindi(page):
    tab(page, 'Plan')
    link = page.get_by_role('link', name='Share on WhatsApp')
    link.wait_for()
    assert 'आज का मेन्यू' in unquote(link.get_attribute('href'))


def test_one_meal_many_plates(page, site):
    page.goto(site + '#/recipe/kanda_poha')
    page.get_by_text('One meal, many plates').wait_for()
    page.locator('.plates').get_by_text('Dadaji:').wait_for()
    page.locator('.plates').get_by_text(re.compile('smaller portion')).wait_for()
    snap(page, '23-plates')


def test_pin_a_family_tradition(page):
    page.get_by_label('Day of the week').select_option('0')
    page.get_by_role('button', name='⭐ Pin').click()
    page.get_by_text(re.compile('your Sun favourite')).wait_for()
    tab(page, 'Plan')
    page.get_by_text('Family traditions').wait_for()


def test_log_meals_and_see_the_dashboard(page):
    tab(page, 'Track')
    dish = page.get_by_label('Dish name', exact=True)
    page.get_by_role('button', name='Dinner', exact=True).click()
    dish.fill('Dal Tadka')
    page.get_by_role('button', name='Log', exact=True).click()
    page.get_by_text('Logged Dal Tadka').wait_for()
    page.get_by_role('button', name='Lunch', exact=True).click()
    dish.fill('Pizza from outside')
    page.get_by_role('button', name='Log', exact=True).click()
    page.locator('.diary-item', has_text='Pizza from outside').wait_for()
    page.get_by_role('button', name='Yesterday').click()
    dish.fill('Jeera Rice')
    page.get_by_role('button', name='Log', exact=True).click()
    page.locator('.diary-item', has_text='Jeera Rice').wait_for()
    expect(page.locator('.bar-row', has_text='Protein').locator('.bar-count')).to_have_text('1')
    page.locator('.insights').wait_for()
    snap(page, '24-dashboard')
    no_sideways_scroll(page, 'Track')
    page.get_by_role('button', name='Remove Pizza from outside').click()
    expect(page.locator('.diary-item', has_text='Pizza')).to_have_count(0)


def test_logged_dishes_are_flagged_as_repeats(page, site):
    page.goto(site + '#/recipe/dal_tadka')
    page.get_by_text('You already made this today.').wait_for()


def test_finishing_a_cook_logs_it_and_keeps_leftovers(page, site):
    page.goto(site + '#/recipe/jeera_rice')
    page.get_by_role('button', name='Start cooking').click()
    for _ in range(12):
        if page.get_by_role('button', name='Done cooking ✓').count():
            page.get_by_role('button', name='Done cooking ✓').click()
            break
        page.get_by_role('button', name='Next ›').click()
    page.get_by_text('Anything left over?').wait_for()
    page.get_by_label(re.compile('Leftover rice becomes')).check()
    page.get_by_role('radio', name='4 stars').click()
    page.get_by_role('button', name='Save and finish').click()
    page.locator('.stats').get_by_text('meals cooked').wait_for()
    tab(page, 'Track')
    page.locator('.diary-item', has_text='Jeera Rice').nth(1).wait_for()


def test_ask_ballava_knows_the_plan(page):
    more(page, 'Ask Ballava')
    page.get_by_role('button', name="What's planned for tomorrow?").click()
    page.locator('.bubble.bot', has_text="Tomorrow's plan").wait_for()
    page.get_by_label('Your question').fill('I have paneer and spinach')
    page.get_by_role('button', name='Send').click()
    page.locator('.bubble.bot', has_text='Palak Paneer').wait_for()
    snap(page, '25-ask')
    no_sideways_scroll(page, 'Ask')


def test_data_follows_you_to_a_second_phone(page, device, site):
    phone2 = device()
    page.wait_for_timeout(1500)  # let the last changes upload
    sign_in(phone2, site)
    tab(phone2, 'Plan')
    phone2.locator('.plan-day').first.wait_for()
    tab(phone2, 'Track')
    phone2.locator('.diary-item', has_text='Dal Tadka').wait_for()
    more(phone2, 'Family')
    phone2.get_by_text('Dadaji').first.wait_for()
    phone2.context.close()


def test_family_member_joins_and_changes_reach_both_phones(page, device, site):
    more(page, 'Account')
    code = page.get_by_label('Family code', exact=True).first.inner_text()
    snap(page, '26-account')
    ravi = device()
    ravi.goto(site)
    ravi.get_by_role('button', name='Create account').click()
    ravi.get_by_label('Your name').fill('Ravi')
    ravi.get_by_label('Email').fill('ravi@ballava.test')
    ravi.get_by_label('Password').fill('kadai-masala-42')
    ravi.get_by_role('checkbox').check()
    ravi.get_by_role('button', name='Create account').last.click()
    ravi.get_by_role('navigation', name='Main').wait_for()
    more(ravi, 'Account')
    ravi.get_by_role('textbox', name='Family code').fill(code)
    ravi.get_by_role('button', name='Join', exact=True).click()
    ravi.get_by_text('You joined the family kitchen').wait_for()
    ravi.get_by_text('Asha, Ravi').wait_for()

    # Ravi adds something; Asha sees it when she comes back to the app.
    tab(ravi, 'Kitchen')
    ravi.get_by_label('Add ingredients').fill('paneer')
    ravi.get_by_role('button', name='Add', exact=True).click()
    ravi.locator('.pantry-list .p-name', has_text='Paneer').wait_for()
    ravi.wait_for_timeout(1500)
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    tab(page, 'Kitchen')
    page.locator('.pantry-list .p-name', has_text='Paneer').wait_for(timeout=10000)

    # Both change the kitchen at the same time with no connection: nobody's item is lost.
    # (Offline, typed words can't be read, because Python does that on the server. Picking from the list still works.)
    page.context.set_offline(True)
    ravi.context.set_offline(True)
    page.get_by_role('button', name='Vegetables').click()
    page.locator('.chip.ing', has_text='Carrot').first.click()
    ravi.get_by_role('button', name='Vegetables').click()
    ravi.locator('.chip.ing', has_text='Cabbage').first.click()
    page.context.set_offline(False)
    ravi.context.set_offline(False)
    for p in (page, ravi):
        p.evaluate("window.dispatchEvent(new Event('online'))")
    for p in (page, ravi):
        for item in ('Carrot', 'Cabbage'):
            p.evaluate("window.dispatchEvent(new Event('focus'))")
            p.locator('.pantry-list .p-name', has_text=item).wait_for(timeout=15000)
    ravi.context.close()


def test_family_vote_needs_no_account(page, device):
    tab(page, 'Plan')
    page.get_by_role('button', name=re.compile('Ask the family')).first.click()
    share = page.get_by_role('link', name='Share vote').first
    share.wait_for()
    link = re.search(r'https?://\S+/vote/\S+', unquote(share.get_attribute('href'))).group(0)
    kid = device()
    kid.goto(link)
    kid.locator('.vote-option').first.wait_for()
    snap(kid, '27-vote')
    kid.locator('.vote-option').nth(1).click()
    kid.get_by_text('Your vote is in').wait_for()
    assert kid.get_by_role('navigation', name='Main').count() == 0, 'no family data on the public page'
    kid.context.close()
    page.reload()
    tab(page, 'Plan')
    page.get_by_role('button', name='Use the winner').first.click()
    page.get_by_text(re.compile('it is!')).wait_for()


def test_language_switch(page):
    tab(page, 'More')
    page.get_by_role('button', name='हिन्दी').click()
    page.get_by_role('navigation', name='Main').get_by_role('button', name='रसोई').wait_for()
    snap(page, '28-hindi')
    page.get_by_role('button', name='English').click()
    page.get_by_role('navigation', name='Main').get_by_role('button', name='Kitchen', exact=True).wait_for()


def test_offline_phone_still_saves_and_uploads_later(device, site):
    p = device()
    sign_in(p, site)
    p.context.route('**/api/**', lambda route: route.abort())
    p.reload()
    tab(p, 'Kitchen')
    p.get_by_role('button', name='Vegetables').click()
    p.locator('.chip.ing', has_text='Radish').first.click()
    p.locator('.pantry-list .p-name', has_text='Radish').wait_for()
    p.context.unroute('**/api/**')
    p.evaluate("window.dispatchEvent(new Event('online'))")
    p.wait_for_timeout(2000)
    p.context.close()
    other = device()
    sign_in(other, site)
    tab(other, 'Kitchen')
    other.locator('.pantry-list .p-name', has_text='Radish').wait_for()
    other.context.close()


def test_phone_sign_in(device, site):
    p = device()
    p.goto(site)
    p.get_by_role('button', name='Phone', exact=True).click()
    p.get_by_label('Mobile number').fill('9876543210')
    p.get_by_role('button', name='Send code').click()
    code = p.locator('.note.info b').inner_text().strip()
    p.get_by_label('Your name').fill('Meena')
    p.get_by_label('6-digit code').fill(code)
    p.get_by_role('checkbox').check()
    p.get_by_role('button', name='Verify and continue').click()
    p.get_by_role('navigation', name='Main').wait_for()
    p.context.close()


def test_family_user_cannot_get_into_admin(device, site):
    p = device(DESKTOP)
    admin_sign_in(p, site, {'email': ASHA['email'], 'password': ASHA['password']})
    p.get_by_text(re.compile('correct')).first.wait_for()
    p.context.close()


def test_admin_publishes_a_recipe_and_users_see_it(page, device, site):
    p = device(DESKTOP)
    admin_sign_in(p, site)
    p.get_by_text('Meals logged').wait_for()
    assert 'Dadaji' not in p.content(), 'admin overview shows no family details'
    snap(p, '30-admin-overview')

    p.goto(site + 'admin/kitchen/recipe/add/')
    p.get_by_label('Id:', exact=True).fill('gongura_pappu')
    p.get_by_label('Name:', exact=True).fill('Admin Test Pappu')
    p.get_by_label('Cuisine:', exact=True).fill('Andhra')
    p.get_by_label('Ingredients:', exact=True).fill('toor_dal:1 cup\nmysteryleaf:1 bunch')
    p.get_by_label('Steps:', exact=True).fill('Pressure cook the dal well. |3w\nAdd the tadka and serve hot.')
    p.get_by_role('button', name='Save', exact=True).click()
    p.get_by_text(re.compile('Unknown ingredient "mysteryleaf"')).wait_for()
    p.locator('#result_list').get_by_role('link', name='Admin Test Pappu').click()
    p.get_by_label('Ingredients:', exact=True).fill('toor_dal:1 cup\nspinach:1 bunch\nturmeric:1/2 tsp')
    p.get_by_role('button', name='Save', exact=True).click()

    def run_action(label):
        p.locator('tr', has_text='Admin Test Pappu').get_by_role('checkbox').check()
        p.locator('select[name=action]').select_option(label=label)
        p.get_by_role('button', name=re.compile('^(Go|Run)$')).click()

    run_action('Send to review')
    p.get_by_text(re.compile('sent to review')).wait_for()
    run_action('Publish (users see it straight away)')
    p.get_by_text(re.compile('Users see it now')).wait_for()
    snap(p, '31-admin-recipe')

    page.goto(site + '#/recipe/gongura_pappu')
    page.reload()
    page.get_by_role('heading', name=re.compile('Admin Test Pappu')).wait_for()

    p.goto(site + 'admin/kitchen/announcement/add/')
    p.get_by_label('Text:', exact=True).fill('Navratri recipes are here!')
    p.get_by_role('button', name='Save', exact=True).click()
    page.goto(site + '#/home')
    page.reload()
    page.get_by_text('Navratri recipes are here!').wait_for()

    p.goto(site + 'admin/recipe-book/?q=pappu')
    p.locator('#recipe-book').get_by_role('link', name='Admin Test Pappu').click()
    p.get_by_text(re.compile('Nutrition per serving')).wait_for()
    snap(p, '33-admin-recipe-detail')
    p.goto(site + 'admin/recipe-book/')
    p.locator('#recipe-book').get_by_role('link', name='Kanda Poha').wait_for()
    snap(p, '34-admin-recipe-book')
    no_sideways_scroll(p, 'admin recipe book')

    p.goto(site + 'admin/auth/user/')
    p.get_by_role('link', name='Asha').wait_for()
    snap(p, '32-admin-users')
    p.goto(site + 'admin/admin/logentry/')
    p.get_by_text('Admin Test Pappu').first.wait_for()
    p.context.close()


def test_every_screen_fits_a_phone(page, site):
    for route in ['home', 'plan', 'track', 'pantry', 'list', 'more', 'family', 'bachao', 'ask', 'account', 'ai', 'recipe/dal_tadka', 'saved']:
        page.goto(f'{site}#/{route}')
        page.wait_for_timeout(150)
        no_sideways_scroll(page, route)


def test_signing_out_removes_family_data_from_the_phone(page):
    more(page, 'Account')
    page.get_by_role('button', name='Sign out').click()
    page.get_by_text('Continue without an account').wait_for()
    left = page.evaluate("['members', 'pantry', 'history', 'plan'].map(k => localStorage.getItem('ballava.' + k))")
    assert all(v in (None, '[]', '{}') for v in left), left
    page.get_by_role('button', name='Continue without an account').click()
    page.get_by_role('button', name='Try with a sample kitchen').wait_for()


def test_no_javascript_errors(errors):
    assert errors == []
