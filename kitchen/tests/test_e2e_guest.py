"""Real-browser test of the app without an account: open Chrome on a phone-sized screen and use it like a person.
Run: pytest -m e2e   (screenshots go to test-screenshots/)"""
import re

import pytest
from playwright.sync_api import expect

from .e2e_helpers import WIDE, browser, device, errors, no_sideways_scroll, open_chef, site, snap, tab, more  # noqa: F401  (pytest fixtures)

pytestmark = pytest.mark.e2e


@pytest.fixture(scope='module')
def page(device, site):
    p = device()
    p.goto(site)
    return p


def test_first_visit_shows_the_welcome_screen(page):
    page.get_by_role('button', name='Continue without an account').click()
    page.get_by_text('Cooks with you today. For you tomorrow.').wait_for()
    snap(page, '01-welcome')


def test_add_ingredients_by_typing_in_hindi_and_english(page):
    page.get_by_role('button', name='Add what I have').click()
    page.get_by_label('Add ingredients').fill('2 tamatar, pyaz, anda, hari mirch, dahi, leftover chawal, mysteryfruit')
    page.get_by_role('button', name='Add', exact=True).click()
    page.get_by_text(re.compile("Didn't recognise: mysteryfruit")).wait_for()
    for name in ['Tomato', 'Onion', 'Eggs', 'Green chilli', 'Curd', 'Leftover rice']:
        page.locator('.pantry-list .p-name', has_text=name).first.wait_for()
    page.get_by_role('button', name='+ Masala box').click()
    page.get_by_text(re.compile('Added 8 items from Masala box')).wait_for()
    snap(page, '02-kitchen')


def test_leftover_rice_can_be_adjusted(page):
    row = page.locator('.pantry-list li', has_text='Leftover rice')
    row.get_by_text('1 day left').wait_for()
    row.get_by_role('button', name=re.compile('One day less')).click()
    row.get_by_text('Use today').wait_for()


def test_home_suggests_dishes_and_flags_leftovers(page):
    tab(page, 'Cook')
    page.locator('.soon-banner').first.wait_for()
    expect(page.locator('.dish-title', has_text='Curd Rice').first).to_be_visible()
    expect(page.locator('.dish-title', has_text='Masala Omelette').first).to_be_visible()
    snap(page, '03-home')


def test_veg_filter_hides_egg_dishes(page):
    page.get_by_role('button', name='Veg only').click()
    expect(page.locator('.dish-title', has_text=re.compile('Omelette|Egg'))).to_have_count(0)
    expect(page.locator('.dish-title').first).to_be_visible()
    page.get_by_role('button', name='Veg only').click()
    expect(page.locator('.dish-title', has_text='Masala Omelette').first).to_be_visible()


def test_recipe_page_shows_have_and_missing(page):
    page.locator('.dish-card', has_text='Curd Rice').first.click()
    page.get_by_role('heading', name=re.compile('Curd Rice')).wait_for()
    page.get_by_text(re.compile('Food safety')).wait_for()
    assert page.locator('.ing-list li.have').count() >= 2
    snap(page, '04-recipe')


def test_missing_items_go_to_the_shopping_list(page, site):
    page.goto(site + '#/recipe/palak_paneer')
    page.get_by_role('button', name=re.compile('missing to shopping list')).click()
    page.get_by_text(re.compile('to your shopping list')).wait_for()
    tab(page, 'List')
    page.get_by_role('heading', name='Shopping list').wait_for()
    page.locator('.shop-list li', has_text='Spinach').wait_for()
    wa = page.get_by_role('link', name='Share list on WhatsApp').get_attribute('href')
    assert wa.startswith('https://wa.me/?text=Ballava%20shopping%20list')
    page.locator('.shop-list li', has_text='Spinach').get_by_role('checkbox').check()
    page.get_by_role('button', name=re.compile('I bought the ticked items')).click()
    page.get_by_text(re.compile('Moved 1 item')).wait_for()
    snap(page, '05-shopping')


def test_cook_mode_steps_timer_whistles_bachao_finish(page, site):
    page.goto(site + '#/recipe/dal_tadka')
    page.get_by_role('button', name='Start cooking').click()
    page.get_by_text('Step 1 of 6').wait_for()
    for _ in range(4):
        page.get_by_role('button', name='I heard a whistle (+1)').click()
    page.get_by_text(re.compile('enough whistles')).wait_for()
    snap(page, '06-cook-whistle')
    page.get_by_role('button', name='Next ›').click()
    page.get_by_role('button', name='Next ›').click()
    page.get_by_text('Step 3 of 6').wait_for()
    page.get_by_role('button', name=re.compile('Start 1-minute timer')).click()
    page.locator('.timer').get_by_text(re.compile(r'0:5\d|1:00')).wait_for()
    page.get_by_role('button', name=re.compile('Bachao!')).click()
    page.get_by_placeholder(re.compile('Search')).fill('salty')
    page.get_by_role('button', name='Too much salt').click()
    page.get_by_text(re.compile('Myth check')).wait_for()
    snap(page, '08-bachao')
    page.get_by_role('button', name='Close').click()
    for _ in range(3):
        page.get_by_role('button', name='Next ›').click()
    page.get_by_role('button', name='Done cooking ✓').click()
    page.get_by_role('radio', name='5 stars').click()
    page.get_by_role('button', name='Save and finish').click()
    page.locator('.stats').get_by_text('meals cooked').wait_for()
    assert page.locator('.stats b').first.inner_text() == '1'


def test_jain_vegetarian_member_changes_suggestions(page):
    more(page, 'Family')
    page.get_by_placeholder('e.g. Amma').fill('Amma')
    page.locator('select').first.select_option('veg')
    page.get_by_label('Jain').check()
    page.get_by_role('button', name='Add member').click()
    page.get_by_text(re.compile('Added Amma')).wait_for()
    tab(page, 'Cook')
    page.get_by_text(re.compile('suit everyone in your family')).wait_for()
    expect(page.locator('.dish-title', has_text=re.compile('Egg|Omelette|Chicken'))).to_have_count(0)
    expect(page.locator('.dish-title').first).to_be_visible()


def test_ai_chef_explains_it_is_switched_off(page):
    page.get_by_role('button', name='✨ Recipe Studio').click()
    page.get_by_text('Recipe Studio needs AI').wait_for()
    page.get_by_text(re.compile('AI_PROVIDER')).wait_for()


def test_ai_is_in_the_navigation_on_every_tab(page):
    for name in ['Cook', 'Plan', 'Kitchen', 'List', 'Dashboard', 'More']:
        tab(page, name)
        open_chef(page)
        page.get_by_text('AI is off · quick answers').wait_for()
        tab(page, 'Ballava Chef')  # the same button closes it again
        expect(page.get_by_role('dialog', name='Ballava Chef')).to_have_count(0)
    tab(page, 'Cook')
    open_chef(page)
    page.get_by_label('Your question').fill('How many calories in dal tadka?')
    page.get_by_role('button', name='Send').click()
    page.locator('.bubble.bot', has_text='kcal per serving').wait_for()
    page.get_by_label('Your question').fill('How do I make chole?')
    page.get_by_role('button', name='Send').click()
    card = page.locator('.chat-dish', has_text='Punjabi Chole')
    card.get_by_text(re.compile('Missing \\d+:')).wait_for()
    snap(page, '09-ai-window')
    card.get_by_role('button', name='🛒 Add missing').click()
    card.get_by_role('button', name='✓ On your list').wait_for()


def test_every_chat_is_kept(page):
    page.get_by_role('button', name=re.compile('Your chats')).click()
    page.locator('.chat-list-item', has_text='How many calories in dal tadka?').wait_for()
    page.get_by_role('button', name='New chat').click()
    page.get_by_text("I'm Ballava Chef").wait_for()
    page.locator('.recent-chat', has_text='How many calories').wait_for()  # recent chats, right there in a new chat
    page.get_by_role('button', name=re.compile('Your chats')).click()
    page.locator('.chat-list-open', has_text='How many calories').click()
    page.locator('.bubble.me', has_text='How do I make chole?').wait_for()
    page.locator('.chat-dish', has_text='Dal Tadka').get_by_role('button', name='Open recipe').click()
    page.get_by_role('heading', name=re.compile('Dal Tadka')).wait_for()
    expect(page.get_by_role('dialog', name='Ballava Chef')).to_have_count(0), 'opening a dish closes the chat'


def test_recipe_shows_calories_and_can_be_saved(page):
    page.locator('.nutrition .nutri-kcal').wait_for()
    expect(page.locator('.ing-list .line-kcal').first).to_be_visible()
    page.get_by_role('button', name='Save Dal Tadka').click()
    page.get_by_text(re.compile('Saved Dal Tadka')).wait_for()
    snap(page, '10-recipe-nutrition')
    page.goto(page.url.split('#')[0] + '#/recipe/kanda_poha')
    page.get_by_role('button', name='Save Kanda Poha').click()
    tab(page, 'Cook')
    page.locator('.saved-tile', has_text='Kanda Poha').wait_for()
    expect(page.locator('.saved-tile', has_text='Dal Tadka')).to_have_count(0), 'cooked today, so not suggested again yet'
    more(page, 'Saved dishes')
    page.locator('.dish-title', has_text='Dal Tadka').wait_for()
    page.get_by_text('Made today').wait_for()
    snap(page, '11-saved')
    page.get_by_role('button', name='Remove Dal Tadka from saved dishes').click()
    page.get_by_role('button', name='Remove Kanda Poha from saved dishes').click()
    page.get_by_text('Nothing saved yet').wait_for()


def test_dashboard_greets_you_by_name(page):
    tab(page, 'Dashboard')
    page.get_by_role('heading', name=re.compile('^Good (morning|afternoon|evening)|^Hello')).wait_for()
    page.get_by_role('button', name='What should I call you?').click()
    page.get_by_label('Your name').fill('Deepak')
    page.get_by_role('button', name='Save', exact=True).click()
    page.get_by_role('heading', name=re.compile(', Deepak')).wait_for()
    page.locator('.quick-card').get_by_role('button', name=re.compile('What can I cook')).wait_for()
    open_chef(page)
    page.get_by_role('button', name='New chat').click()
    page.get_by_text("Hi Deepak! I'm Ballava Chef").wait_for()
    tab(page, 'Ballava Chef')


def test_the_app_opens_on_the_dashboard(page):
    page.goto(page.url.split('#')[0])
    page.get_by_role('heading', name=re.compile(', Deepak')).wait_for()
    expect(page.get_by_role('navigation', name='Main').get_by_role('button', name='Dashboard', exact=True)).to_have_class(re.compile('active'))


def test_dashboard_shows_calories_and_meals(page):
    tab(page, 'Dashboard')
    page.locator('.goal-ring').wait_for()
    page.locator('.meal-table tr', has_text='Dal Tadka').first.wait_for()
    page.get_by_role('button', name=re.compile('Daily goal')).click()
    page.get_by_label('Daily calorie goal per person').fill('1500')
    page.get_by_role('button', name='Save', exact=True).click()
    page.get_by_text('of 1,500 kcal').wait_for()
    page.get_by_role('button', name='30 days').click()
    expect(page.locator('.kcal-col')).to_have_count(30)
    snap(page, '12-dashboard')


def test_calories_and_the_light_filter(page):
    tab(page, 'Cook')
    page.get_by_role('button', name='Light (≤400 kcal)').click()
    expect(page.locator('.dish-card .kcal').first).to_be_visible()
    for text in page.locator('.dish-card .kcal').all_inner_texts():
        assert int(text.split()[0]) <= 400, text
    page.get_by_role('button', name='Light (≤400 kcal)').click()


def test_computer_screens_use_the_width(device, site):
    p = device(WIDE)
    p.goto(site)
    p.locator('.login-perks').wait_for()  # sign-in: the story on the left, the forms on the right
    snap(p, '40-desktop-login')
    p.get_by_role('button', name='Continue without an account').click()
    p.get_by_role('button', name='Try with a sample kitchen').click()
    p.get_by_text('Cook now').wait_for()
    nav = p.get_by_role('navigation', name='Main').bounding_box()
    assert nav['x'] == 0 and nav['height'] > 800 and nav['width'] < 300, f'a sidebar on the left: {nav}'
    p.locator('.dish-card').nth(3).wait_for()
    columns = p.evaluate("getComputedStyle(document.querySelector('.dish-list')).gridTemplateColumns.split(' ').length")
    assert columns >= 2, columns
    snap(p, '41-desktop-cook')
    tab(p, 'Dashboard')
    p.locator('.hub-grid .quick-card').wait_for()
    snap(p, '42-desktop-dashboard')
    no_sideways_scroll(p, 'desktop dashboard')
    p.goto(site + '#/recipe/dal_tadka')
    left, right = p.locator('.recipe-left').bounding_box(), p.locator('.recipe-right').bounding_box()
    assert right['x'] > left['x'] + left['width'] - 1, 'ingredients and steps sit beside the details'
    tab(p, 'Ballava Chef')
    p.get_by_role('dialog', name='Ballava Chef').wait_for()
    panel = p.locator('.sheet-inner.assistant').bounding_box()
    assert panel['x'] + panel['width'] >= 1439 and panel['height'] >= 890, f'Chef is docked on the right: {panel}'
    main = p.locator('main').bounding_box()
    assert main['x'] + main['width'] <= panel['x'] + 1, 'the page makes room for Chef instead of hiding under it'
    snap(p, '43-desktop-recipe-chef')
    no_sideways_scroll(p, 'desktop recipe with Chef')
    p.context.close()


def test_data_survives_a_reload(page):
    page.reload()
    tab(page, 'Kitchen')
    page.locator('.pantry-list .p-name', has_text='Tomato').wait_for()


def test_no_javascript_errors(errors):
    assert errors == []
