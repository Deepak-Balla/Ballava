"""Real-browser test of the app without an account: open Chrome on a phone-sized screen and use it like a person.
Run: pytest -m e2e   (screenshots go to test-screenshots/)"""
import re

import pytest
from playwright.sync_api import expect

from .e2e_helpers import browser, device, errors, site, snap, tab, more  # noqa: F401  (pytest fixtures)

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
    page.get_by_role('button', name='✨ AI Chef').click()
    page.get_by_text('AI Chef is switched off').wait_for()
    page.get_by_text(re.compile('AI_PROVIDER')).wait_for()


def test_data_survives_a_reload(page):
    page.reload()
    tab(page, 'Kitchen')
    page.locator('.pantry-list .p-name', has_text='Tomato').wait_for()


def test_no_javascript_errors(errors):
    assert errors == []
