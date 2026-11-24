"""Real-browser test of the signed-in app: real Chrome, the real Django server and database, several family members.
Run: pytest -m e2e"""
import re
from datetime import timedelta
from urllib.parse import unquote

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from playwright.sync_api import expect

from .e2e_helpers import DESKTOP, PHONE, browser, device, diary, errors, more, no_sideways_scroll, open_chef, site, snap, tab  # noqa: F401

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
    settings.PUBLIC_URL = site.rstrip('/')  # shared links open on this test server
    User.objects.create_superuser(ADMIN['email'], ADMIN['email'], ADMIN['password'])
    yield settings
    settings.OTP_DEV_MODE = False
    settings.PUBLIC_URL = ''


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
    picker = page.get_by_role('dialog', name=re.compile('Change Dinner'))
    picker.locator('.swap-option').first.wait_for()
    first_ideas = picker.locator('.swap-option').all_inner_texts()
    assert len(first_ideas) >= 3, first_ideas
    picker.get_by_role('button', name='🔁 Show other ideas').click()
    expect(picker.locator('.swap-option').first).not_to_have_text(first_ideas[0])  # new ideas, never the same two again
    second = [t.split('\n')[0] for t in picker.locator('.swap-option').all_inner_texts()]
    assert not set(second) & {t.split('\n')[0] for t in first_ideas}, (first_ideas, second)
    snap(page, '22b-swap-picker')
    picker.locator('.swap-option').first.click()
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
    diary(page)
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
    snap(page, '24-diary')
    no_sideways_scroll(page, 'Food diary')

    # Food from outside has no calories until you add them.
    page.get_by_role('button', name='📊 Overview').click()
    row = page.locator('.meal-table tr', has_text='Pizza from outside')
    row.get_by_role('button', name='Add kcal').click()
    row.get_by_label('Calories for Pizza from outside').fill('650')
    row.get_by_role('button', name='OK').click()
    row.get_by_text('650').wait_for()
    page.locator('.meal-table tr', has_text='Dal Tadka').first.wait_for()
    snap(page, '24-dashboard')
    no_sideways_scroll(page, 'Dashboard')

    page.get_by_role('button', name='📖 Food diary').click()
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
    diary(page)
    page.locator('.diary-item', has_text='Jeera Rice').nth(1).wait_for()


def test_ai_window_knows_the_plan(page):
    tab(page, 'Plan')
    open_chef(page)
    page.get_by_role('button', name="What's planned for tomorrow?").click()
    page.locator('.bubble.bot', has_text="Tomorrow's plan").wait_for()
    page.get_by_label('Your question').fill('I have paneer and spinach')
    page.get_by_role('button', name='Send').click()
    card = page.locator('.bubble.bot .chat-dish', has_text='Palak Paneer')
    card.wait_for()
    card.get_by_role('button', name='📅 Tomorrow').click()
    page.get_by_text(re.compile("Planned Palak Paneer for tomorrow's")).wait_for()
    snap(page, '25-chef-window')
    no_sideways_scroll(page, 'Chef window')
    tab(page, 'Ballava Chef')
    page.goto(page.url.split('#')[0] + '#/ask')  # the old Ask Ballava address opens Chef
    page.get_by_role('dialog', name='Ballava Chef').wait_for()
    tab(page, 'Ballava Chef')


def test_data_follows_you_to_a_second_phone(page, device, site):
    phone2 = device()
    page.wait_for_timeout(1500)  # let the last changes upload
    sign_in(phone2, site)
    phone2.get_by_role('heading', name=re.compile(', Asha')).wait_for()  # the dashboard greets her by name
    open_chef(phone2)  # her chats came along to the new phone
    phone2.get_by_role('button', name=re.compile('Your chats')).click()
    phone2.locator('.chat-list-item', has_text="What's planned for tomorrow?").wait_for()
    phone2.get_by_text('Saved in your account').wait_for()
    tab(phone2, 'Ballava Chef')
    tab(phone2, 'Plan')
    phone2.locator('.plan-day').first.wait_for()
    diary(phone2)
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
            p.locator('.pantry-list .p-name', has_text=item).wait_for(timeout=30000)  # phones check again every 20 seconds
    ravi.context.close()


def vrat_names(p):
    return set(p.evaluate("() => JSON.parse(localStorage.getItem('ballava.catalog')).recipes.filter(r => r.tags.includes('vrat')).map(r => r.name)"))


def meals_of(p, day):
    """The day's three main dishes (not tiffins or the fasting people's own meals)."""
    return day.evaluate("""d => [...d.querySelectorAll('.plan-row')].filter(r => ['Breakfast', 'Lunch', 'Dinner'].includes(r.querySelector('.plan-slot').textContent))
      .map(r => [...r.querySelector('.plan-dish').childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim())""")


def test_festival_added_by_an_admin_shows_without_a_reload(page, device, site):
    tab(page, 'Dashboard')
    assert page.get_by_text('Nagula Chavithi').count() == 0
    boss = device(DESKTOP)
    admin_sign_in(boss, site)
    soon = timezone.localdate() + timedelta(days=2)
    boss.goto(site + 'admin/kitchen/festival/add/')
    boss.get_by_label('Name').fill('Nagula Chavithi')
    boss.get_by_label('Date').fill(soon.isoformat())
    boss.get_by_label('Fast').check()
    boss.get_by_role('button', name='Save', exact=True).click()
    boss.get_by_text(re.compile('Users will see Nagula Chavithi')).wait_for()
    snap(boss, '26-admin-festival')
    page.evaluate("window.dispatchEvent(new Event('focus'))")  # coming back to the app (it also checks every 30 seconds)
    page.get_by_text('Nagula Chavithi').first.wait_for()
    page.get_by_text(re.compile('in 2 days')).wait_for()
    snap(page, '26-dashboard-festival')
    # It's marked as a fast, so it's kept unless the family says otherwise, with dishes that suit a fast.
    expect(page.get_by_label('We keep this fast')).to_be_checked()
    tab(page, 'Plan')
    plan_day = page.locator('.plan-day', has_text='Nagula Chavithi')
    plan_day.wait_for()
    usual = meals_of(page, plan_day)
    first_day = meals_of(page, page.locator('.plan-day').first)
    tab(page, 'Dashboard')
    card = page.locator('.festival-card')
    card.get_by_text('Children, and people who are pregnant or diabetic').wait_for()  # Riya is a child and Dadaji is diabetic...
    card.get_by_role('button', name='Dadaji').click()  # ...but Dadaji does keep it
    card.get_by_text('Fasting dishes that suit you').wait_for()
    ideas = card.locator('.festival-item > .chips .chip')
    expect(ideas).to_have_count(4)
    assert set(ideas.all_inner_texts()) <= vrat_names(page)
    snap(page, '26-dashboard-festival')
    tab(page, 'Plan')
    day = page.locator('.plan-day', has_text='Nagula Chavithi')
    # That day's plan followed at once, and only that day's. The others keep their meals.
    day.get_by_text('Vrat · Lunch').wait_for()
    fasting = [r.strip() for r in day.locator('.plan-row', has_text='Vrat ·').locator('.plan-dish').all_inner_texts()]
    assert len(fasting) == 3 and all(any(f.startswith(v) for v in vrat_names(page)) for f in fasting), fasting
    assert meals_of(page, day) == usual, 'the others eat as planned'
    assert meals_of(page, page.locator('.plan-day').first) == first_day, 'no other day changes'
    day.scroll_into_view_if_needed()
    snap(page, '26-plan-some-fasting')
    # A fasting dish can be changed, for other fasting dishes.
    day.get_by_label('Swap Vrat · Lunch').click()
    picker = page.get_by_role('dialog', name=re.compile('Change Fasting Lunch'))
    picker.locator('.swap-option').first.wait_for()
    assert all(any(v in o for v in vrat_names(page)) for o in picker.locator('.swap-option').all_inner_texts())
    picker.locator('.swap-option').nth(1).click()
    expect(day.get_by_label('Unlock Vrat · Lunch')).to_be_visible()
    # Everyone fasts: all three meals are fasting dishes. Nobody: the usual meals come back.
    day.get_by_role('button', name=re.compile('^Fasting:')).click()
    day.get_by_role('button', name='Everyone', exact=True).click()
    day.get_by_text('Vrat · Lunch').wait_for(state='detached')
    assert set(meals_of(page, day)) <= vrat_names(page), meals_of(page, day)
    snap(page, '26-plan-everyone-fasting')
    day.get_by_role('button', name='Nobody', exact=True).click()
    expect(day.locator('.plan-dish').first).to_contain_text(usual[0])
    assert meals_of(page, day) == usual
    tab(page, 'Dashboard')
    expect(page.get_by_label('We keep this fast')).not_to_be_checked()
    # Removing it in the admin portal removes it here too.
    boss.get_by_role('link', name='Nagula Chavithi').first.click()
    boss.locator('a.deletelink').click()
    boss.get_by_role('button', name=re.compile('sure')).click()
    boss.get_by_text(re.compile('deleted successfully')).wait_for()
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    page.get_by_text('Nagula Chavithi').first.wait_for(state='detached')
    boss.context.close()


def whatsapp_text(link):
    return unquote(link.get_attribute('href').split('text=')[1])


def test_fasting_today_changes_the_cook_screen_and_todays_menu(page):
    tab(page, 'Cook')
    page.locator('.today-card').wait_for()
    before = page.locator('.today-card .plan-dish').all_inner_texts()
    page.get_by_role('button', name='Fasting: Today').click()
    page.get_by_role('group', name='Who is fasting: Today').first.get_by_role('button', name='Everyone', exact=True).click()
    page.get_by_text('Today: fasting dishes for everyone').wait_for()
    page.get_by_role('heading', name=re.compile('Fasting dishes')).wait_for()
    names = vrat_names(page)
    dishes = page.locator('.fast-today .dish-title')
    dishes.first.wait_for()
    assert all(d.strip() in names for d in dishes.all_inner_texts())
    expect(page.get_by_role('heading', name=re.compile('Cook now'))).to_have_count(0)
    assert set(x.strip() for x in page.locator('.today-card .plan-dish').all_inner_texts()) <= names
    page.locator('.fast-today').scroll_into_view_if_needed()
    snap(page, '25-cook-fasting')
    no_sideways_scroll(page, 'cook on a fasting day')
    # The Family page has the same switch, per person, just for today.
    more(page, 'Family')
    switches = page.get_by_label('Fasting today')
    expect(switches.first).to_be_checked()
    for n in range(switches.count()):
        switches.nth(n).uncheck()
        expect(switches.nth(n)).not_to_be_checked()
    tab(page, 'Cook')
    page.get_by_role('heading', name=re.compile('Cook now')).wait_for()
    expect(page.locator('.fast-today')).to_have_count(0)
    assert page.locator('.today-card .plan-dish').all_inner_texts() == before, 'the usual menu is back'


def test_family_votes_with_one_whatsapp_link(page, device):
    tab(page, 'Plan')
    page.get_by_role('button', name='Share on WhatsApp and vote', exact=False).first.click()
    sheet = page.get_by_role('dialog', name='Share the plan on WhatsApp')
    for name, want in (('Breakfast', 'false'), ('Lunch', 'false'), ('Dinner', 'true')):  # (meals already over today start unticked)
        if sheet.get_by_role('button', name=name).get_attribute('aria-pressed') != want:
            sheet.get_by_role('button', name=name).click()
    sheet.get_by_role('button', name='Tomorrow').click()  # today's and tomorrow's dinner, in one link
    sheet.get_by_label('Add a note').fill('Guests on Sunday!')
    snap(page, '27-share-choose')
    sheet.get_by_role('button', name='Make one link for 2 meals').click()
    send = sheet.get_by_role('link', name='Send on WhatsApp')
    send.wait_for()
    snap(page, '27-share-vote')
    text = whatsapp_text(send)
    links = re.findall(r'https?://\S+', text)
    assert len(links) == 1 and re.fullmatch(r'https?://\S+/v/\w{10}', links[0]), text
    assert 'Dinner, Today: ' in text and 'Dinner, Tomorrow: ' in text and 'Guests on Sunday!' in text
    assert len(text.splitlines()) <= 6, 'short enough to read at a glance'
    send.evaluate("a => a.addEventListener('click', e => e.preventDefault())")
    send.click()
    sheet.wait_for(state='detached')

    # The link opens everything that was sent. No account, no family data.
    kid = device()
    kid.goto(links[0])
    kid.get_by_text('Guests on Sunday!').wait_for()
    meals = kid.locator('.meal-vote')
    expect(meals).to_have_count(2)
    expect(kid.get_by_role('heading', name='Tomorrow')).to_be_visible()
    expect(meals.nth(0).locator('.vote-option')).to_have_count(3)
    expect(meals.nth(0)).to_contain_text('kcal')
    assert kid.get_by_role('navigation', name='Main').count() == 0, 'no family data on the public page'
    kid.get_by_label('Your name').fill('Kabir')
    kid.get_by_role('button', name='Save').click()
    meals.nth(0).locator('.vote-option').nth(1).click()
    kid.get_by_text('1 of 2 chosen').wait_for()
    meals.nth(1).locator('.vote-option').nth(0).click()
    kid.get_by_text('2 of 2 chosen').wait_for()
    snap(kid, '27-vote')
    no_sideways_scroll(kid, 'vote page')
    # It shows up in the app by itself, with who voted.
    page.get_by_text(re.compile(r'\d new family vote')).wait_for(timeout=15000)
    page.locator('.vote-option', has_text='Kabir').first.wait_for()
    snap(page, '27-plan-votes')

    # Changing your mind moves the vote, and a reload keeps it.
    dinner = meals.nth(0).locator('.vote-option')
    dinner.nth(2).click()
    expect(dinner.nth(2)).to_have_class(re.compile(' on'))
    kid.reload()
    expect(dinner.nth(2)).to_have_class(re.compile(' on'))
    expect(dinner.nth(1)).not_to_have_class(re.compile(' on'))
    chosen = dinner.nth(2).locator('.vote-name > span').inner_text().replace('🏆', '').strip()
    kid.context.close()

    # The Dashboard shows the result; one tap puts the winners in the plan and locks them.
    tab(page, 'Dashboard')
    card = page.locator('.vote-card')
    expect(card.locator('.vote-option', has_text='🏆').first).to_contain_text(chosen)
    card.scroll_into_view_if_needed()
    snap(page, '27-dashboard-votes')
    no_sideways_scroll(page, 'dashboard with votes')
    card.get_by_role('button', name='Use the winners').click()
    page.get_by_text(re.compile('it is!')).wait_for()
    card.wait_for(state='detached')
    tab(page, 'Plan')
    today = page.locator('.plan-day').first
    assert meals_of(page, today)[2] == chosen
    expect(today.get_by_label('Unlock Dinner')).to_be_visible()


def test_share_the_whole_week_for_a_vote(page, device):
    tab(page, 'Plan')
    # One of the days is a fast for everyone: its choices are fasting dishes.
    fast_day = page.locator('.plan-day').nth(3)
    fast_day.get_by_role('button', name=re.compile('^Fasting:')).click()
    fast_day.get_by_role('button', name='Everyone', exact=True).click()
    expect(fast_day.get_by_role('button', name=re.compile('^Fasting:'))).to_contain_text('Everyone fasts')
    page.get_by_text(re.compile('fasting dishes for everyone')).wait_for()
    expect(fast_day.locator('.fast-note')).to_have_count(0)
    page.get_by_role('button', name='Share the week on WhatsApp and vote', exact=False).click()
    sheet = page.get_by_role('dialog', name='Share the plan on WhatsApp')
    sheet.get_by_role('button', name='Lunch').click()
    made = sheet.get_by_role('button', name=re.compile('Make one link for 1[34] meals'))  # (today's lunch may be over)
    made.click()
    send = sheet.get_by_role('link', name='Send on WhatsApp')
    send.wait_for(timeout=30000)
    text = whatsapp_text(send)
    links = re.findall(r'https?://\S+', text)
    assert len(links) == 1 and len(text.splitlines()) <= 4 and 'Today to ' in text and '(lunch, dinner)' in text, text
    sheet.get_by_role('button', name='Close').click()
    kid = device()
    kid.goto(links[0])
    meals = kid.locator('.meal-vote')
    meals.nth(12).wait_for()
    names = vrat_names(page)
    fasts = kid.locator('.card', has_text='Dinner (fasting day)').locator('.vote-name > span').all_inner_texts()
    assert len(fasts) == 6 and set(fasts) <= names, fasts
    for n in range(3):
        meals.nth(n).locator('.vote-option').nth(1).click()
        kid.get_by_text(re.compile(rf'{n + 1} of 1[34] chosen')).wait_for()
    snap(kid, '27-vote-week')
    kid.context.close()
    expect(page.locator('.plan-day').first.locator('.vote-option', has_text='🏆').first).to_be_visible(timeout=15000)
    tab(page, 'Dashboard')
    page.locator('.vote-fold', has_text='1 vote').nth(2).wait_for()
    page.locator('.vote-card').scroll_into_view_if_needed()
    snap(page, '27-dashboard-week')
    no_sideways_scroll(page, 'dashboard with a week of votes')
    tab(page, 'Plan')
    # Every day has a vote now, and choosing one again says it would start over.
    page.get_by_role('button', name='Share the week on WhatsApp and vote', exact=False).click()
    expect(sheet.get_by_role('button', name='Choose at least one meal')).to_be_disabled()
    sheet.get_by_role('button', name='Tomorrow').click()
    sheet.get_by_text('Tomorrow already has a vote').wait_for()
    sheet.get_by_role('button', name='Close').click()
    for _ in range(7):
        page.locator('.vote-box').first.get_by_role('button', name='Remove').click()
    assert page.locator('.vote-box').count() == 0
    if not fast_day.get_by_role('button', name='Nobody', exact=True).is_visible():
        fast_day.get_by_role('button', name=re.compile('^Fasting:')).click()
    fast_day.get_by_role('button', name='Nobody', exact=True).click()
    expect(fast_day.get_by_role('button', name=re.compile('^Fasting:'))).to_contain_text('Fasting?')


def test_old_vote_links_still_work(page, device, site):
    token = page.evaluate("""async () => (await (await fetch('/api/polls', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '' },
      body: JSON.stringify({ title: 'Dinner?', options: [{ id: 'chole', name: 'Chole' }, { id: 'rajma_masala', name: 'Rajma' }] }) })).json()).token""")
    kid = device()
    kid.goto(f'{site}#/vote/{token}')
    kid.locator('.vote-option', has_text='Rajma').click()
    kid.get_by_text('Your vote for').wait_for()
    kid.context.close()
    # Messages sent before had a link for every dish: opening one votes for it, and a reload doesn't vote again.
    kid = device()
    kid.goto(f'{site}v/{token}/0-0')
    kid.get_by_text('Your vote for').wait_for()
    kid.locator('.vote-option', has_text='Rajma').click()
    expect(kid.locator('.vote-option', has_text='Rajma')).to_have_class(re.compile(' on'))
    kid.reload()
    expect(kid.locator('.vote-option', has_text='Rajma')).to_have_class(re.compile(' on'))
    kid.context.close()


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


def test_everything_is_still_there_after_signing_in_again(device, site):
    p = device()
    sign_in(p, site)
    p.goto(site + '#/recipe/kanda_poha')
    p.get_by_role('button', name='Save Kanda Poha').click()
    p.get_by_text(re.compile('Saved Kanda Poha')).wait_for()
    tab(p, 'Dashboard')
    p.get_by_role('button', name=re.compile('Daily goal')).click()
    p.get_by_label('Daily calorie goal per person').fill('1650')
    p.get_by_role('button', name='Save', exact=True).click()
    p.get_by_text('of 1,650 kcal').wait_for()
    p.wait_for_timeout(1500)  # let the changes upload
    more(p, 'Account')
    p.get_by_role('button', name='Sign out').click()
    p.get_by_text('Continue without an account').wait_for()
    assert p.evaluate("localStorage.getItem('ballava.savedDishes')") in (None, '[]'), 'signing out clears this phone'

    sign_in(p, site)
    p.get_by_text('of 1,650 kcal').wait_for()
    more(p, 'Saved dishes')
    p.locator('.dish-title', has_text='Kanda Poha').wait_for()
    p.context.close()


def test_admin_signs_in_from_the_admin_tab(device, site):
    p = device()
    p.goto(site)
    p.get_by_role('button', name='Admin', exact=True).click()
    snap(p, '21-login-admin-tab')
    p.get_by_label('Admin username').fill(ADMIN['email'])
    p.get_by_label('Admin password').fill(ADMIN['password'])
    p.get_by_role('button', name='Sign in to admin').click()
    p.get_by_text('Meals logged').wait_for()
    assert '/admin/' in p.url
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

    # Paste a recipe as it came on WhatsApp: the form fills itself in.
    p.goto(site + 'admin/kitchen/recipe/add/')
    p.get_by_role('tab', name='Paste a recipe').click()
    p.get_by_label('Recipe text').fill("""Admin Test Pappu Recipe
Serves 4, Time: 30 mins
Ingredients
Toor dal - 1 cup
Mysteryleaf - 2 bunches
1 tbsp ghee or oil
Salt to taste
Method
1. Pressure cook the dal for 3 whistles.
2. Cook the leaves for 8-10 minutes and mix.""")
    p.get_by_role('button', name='Fill in the form').click()
    p.get_by_text('Filled in from your text').wait_for()
    assert p.locator('#id_name').input_value() == 'Admin Test Pappu'
    assert p.locator('#id_serves').input_value() == '4'
    expect(p.locator('#re-ing-list .re-chip')).to_have_count(4)  # dal, mysteryleaf, ghee or oil
    assert p.get_by_label('Timer number for step 1').input_value() == '3'
    assert p.get_by_label('Timer number for step 2').input_value() == '10'
    # The checks say what's wrong in plain words, and Publish won't go until it's right.
    p.get_by_text('1 thing to fix before publishing').wait_for()
    p.get_by_role('button', name='Publish').click()
    p.locator('#re-msg').get_by_text(re.compile('"mysteryleaf" is not in the ingredient list yet')).wait_for()
    snap(p, '31-admin-recipe-fix')
    # Add the missing ingredient without leaving the recipe.
    p.get_by_role('button', name='Add to the ingredient list').click()
    dialog = p.get_by_role('dialog', name='New ingredient')
    dialog.get_by_label('Other names people type').fill('rahasyam')
    dialog.get_by_text('Calories per 100 g').click()
    dialog.get_by_label('kcal').fill('30')
    snap(p, '31-admin-new-ingredient')
    dialog.get_by_role('button', name='Add ingredient').click()
    p.get_by_role('heading', name='Ready to publish').wait_for()
    expect(p.locator('#re-msg')).to_be_empty()
    # Type one more ingredient by its Telugu name, and choose a meal, a tag and the spice.
    p.get_by_role('button', name='Add an ingredient').click()
    p.get_by_role('combobox', name='Ingredient', exact=True).fill('ullipaya')
    p.get_by_role('option', name='Onion').click()
    p.get_by_label('Amount of ingredient 4').fill('1 medium, chopped')
    p.get_by_label('Amount of ingredient 4').press('Enter')  # Enter starts the next ingredient; it never saves by accident
    p.get_by_role('combobox', name='Ingredient', exact=True).fill('2 tsp jeera')
    p.get_by_role('combobox', name='Ingredient', exact=True).press('Enter')
    expect(p.locator('#re-ing-list .re-chip', has_text='Cumin')).to_be_visible()
    assert p.get_by_label('Amount of ingredient 5').input_value() == '2 tsp'
    p.get_by_label('Move ingredient 5 up').click()
    assert p.get_by_label('Amount of ingredient 4').input_value() == '2 tsp'
    p.get_by_role('group', name='Meals').get_by_role('button', name='Breakfast').click()
    p.get_by_role('group', name='Spice').get_by_role('button', name='Mild').click()
    p.locator('#re-check').get_by_role('button', name=re.compile('Gluten-free')).click()
    p.get_by_role('group', name='Good for').get_by_role('button', name='Kid-friendly').click()
    p.get_by_label('Step 2', exact=True).press('Enter')
    p.get_by_label('Step 3', exact=True).fill('Simmer for 5 minutes and serve hot.')
    p.get_by_label('Step 3', exact=True).blur()
    assert p.get_by_label('Timer number for step 3').input_value() == '5'
    p.locator('#re-check').get_by_text('kcal a serving').wait_for()
    p.evaluate('window.scrollTo(0, 0)')
    snap(p, '31-admin-recipe')
    no_sideways_scroll(p, 'recipe editor')
    p.get_by_role('button', name='Publish').click()
    p.get_by_text('Users see it now').wait_for()
    snap(p, '31-admin-recipe-published')

    from kitchen.models import Recipe
    saved = Recipe.objects.get(recipe_id='admin_test_pappu')
    assert saved.ingredients.splitlines() == ['toor_dal:1 cup', 'mysteryleaf:2 bunches', 'ghee|oil:1 tbsp', 'cumin:2 tsp', 'onion:1 medium, chopped']
    assert saved.steps.splitlines() == ['Pressure cook the dal for 3 whistles. |3w', 'Cook the leaves for 8-10 minutes and mix. |10m', 'Simmer for 5 minutes and serve hot. |5m']
    assert saved.meal == 'breakfast, lunch, dinner' and saved.spice == 1 and saved.tags == 'kid-friendly, gluten-free'

    # Edit it later, on a phone.
    small = p.context.browser.new_context(**PHONE, storage_state=p.context.storage_state()).new_page()
    small.goto(f'{site}admin/kitchen/recipe/{saved.pk}/change/')
    small.get_by_role('heading', name='Ready to publish').wait_for()
    expect(small.locator('#re-ing-list .re-row')).to_have_count(5)
    no_sideways_scroll(small, 'recipe editor on a phone')
    edges = small.locator('.re-row').evaluate_all('rows => rows.flatMap(r => [...r.children].map(c => c.getBoundingClientRect().right))')
    assert max(edges) <= 390, 'every box of every row fits the phone'
    small.locator('#re-ingredients').scroll_into_view_if_needed()
    snap(small, '31-admin-recipe-phone')
    small.locator('#id_name').fill('Admin Test Pappu Deluxe')
    small.get_by_role('button', name='Save draft').click()
    small.get_by_text('was changed successfully').wait_for()
    small.context.close()

    # Copy an existing recipe, or change it for everyone.
    p.goto(site + 'admin/kitchen/recipe/add/')
    p.get_by_role('tab', name='Copy a recipe').click()
    p.get_by_label('Recipe to start from').fill('Kanda Poha')
    p.get_by_role('button', name='Make a new recipe like it').click()
    p.get_by_text('Copied. Give it its own name').wait_for()
    assert p.locator('#id_name').input_value() == 'Kanda Poha (copy)'
    p.once('dialog', lambda d: d.accept())  # leaving without saving asks first
    p.goto(site + 'admin/kitchen/recipe/add/?copy_from=kanda_poha')
    p.get_by_role('heading', name='Edit Kanda Poha').wait_for()
    assert p.locator('#id_name').input_value() == 'Kanda Poha'

    page.goto(site + '#/recipe/admin_test_pappu')
    page.reload()
    page.get_by_role('heading', name=re.compile('Admin Test Pappu$')).wait_for()  # the published version, not the new draft

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
    for route in ['home', 'plan', 'dashboard', 'track', 'pantry', 'list', 'more', 'family', 'bachao', 'ask', 'account', 'ai', 'recipe/dal_tadka', 'saved']:
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
