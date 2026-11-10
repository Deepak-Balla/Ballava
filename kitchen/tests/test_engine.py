"""Tests for the cooking brain (kitchen/engine.py). Run: pytest"""
import re

import pytest

from kitchen.data.ingredients import BY_ID, INGREDIENTS, KITS
from kitchen.data.rescue import RESCUES
from kitchen.engine import (ALL_RECIPES, RECIPE_BY_ID, buy_tips, chat_reply, days_left, default_expiry, find_rescue, household_check,
                            normalize_ai_recipe, parse_ingredients, parse_step, recipe_text, suggest, use_soon, validate_recipe)
from kitchen.data.recipes import RECIPES

DAY = 86_400_000
NOW = 1_800_000_000_000


def pantry_of(ids):
    return [{'id': i} for i in ids]


def every_dish(result):
    return [r['recipe'] for r in result['ready'] + result['almost']]


# ---------- Data quality: catches typos in the recipe book ----------
def test_every_recipe_ingredient_exists():
    for r in ALL_RECIPES:
        for it in r['ingredients']:
            for i in it['options']:
                assert i in BY_ID, f'{r["id"]} uses unknown ingredient "{i}"'


def test_recipes_are_complete_and_unique():
    ids = set()
    for r in ALL_RECIPES:
        assert r['id'] not in ids, f'duplicate id {r["id"]}'
        ids.add(r['id'])
        assert r['name'] and r['time'] > 0 and r['serves'] > 0, r['id']
        assert r['spice'] in (1, 2, 3), r['id']
        assert len(r['steps']) >= 2 and all(len(s['text']) > 5 for s in r['steps']), r['id']
        assert any(not i['optional'] for i in r['ingredients']), r['id']
        assert r['meal'], r['id']
    assert len(ALL_RECIPES) >= 100


def test_every_recipe_passes_the_publishing_rules():
    for r in RECIPES:
        assert validate_recipe(r) == [], r['id']


def test_ingredient_ids_and_aliases_are_sane():
    ids = set()
    for i in INGREDIENTS:
        assert i['id'] not in ids, i['id']
        ids.add(i['id'])
        assert all(a == a.strip() and a for a in i['aliases'])
    for kit in KITS:
        for i in kit['items']:
            assert i in BY_ID, f'kit {kit["id"]}: {i}'


def test_tags_match_the_actual_ingredients():
    for r in ALL_RECIPES:
        if 'jain' in r['tags']:
            assert r['jainOk'], r['id']
        if 'vrat' in r['tags']:
            assert not r['needsOnionGarlic'], r['id']
        if 'gluten-free' in r['tags']:
            assert 'gluten' not in r['allergens'], r['id']
        if 'diabetic-friendly' in r['tags']:
            assert 'sweet' not in r['tags'], r['id']
        if 'leftover' in r['tags']:
            assert any(BY_ID[i]['category'] == 'Leftovers' or i == 'bread' for it in r['ingredients'] for i in it['options']), r['id']


def test_risky_dishes_carry_a_food_safety_note():
    for r in ALL_RECIPES:
        risky_rice = any(not i['optional'] and i['options'] == ['leftover_rice'] for i in r['ingredients'])
        if (risky_rice and 'leftover' in r['tags']) or r['diet'] == 'nonveg':
            assert r.get('safety'), f'{r["id"]} should have a safety note'


def test_bachao_entries_are_complete():
    for r in RESCUES:
        assert r['title'] and len(r['fixes']) >= 2, r['id']
    assert any(r['id'] == 'safe' for r in RESCUES)


# ---------- Understanding what people type ----------
def test_understands_hindi_telugu_and_english():
    found = parse_ingredients('2 tamatar, pyaz aur thoda dahi, palak, kodi, pesarapappu')['found']
    for i in ['tomato', 'onion', 'curd', 'spinach', 'chicken', 'moong_dal']:
        assert i in found


@pytest.mark.parametrize('text, expected', [
    ('leftover chawal', ['leftover_rice']), ('lal mirch', ['red_chilli_powder']), ('hari mirch', ['green_chilli']),
    ('chana dal', ['chana_dal']), ('cottage cheese', ['paneer']),
])
def test_prefers_longer_names(text, expected):
    assert parse_ingredients(text)['found'] == expected


def test_plurals_numbers_and_unknown_words():
    r = parse_ingredients('3 Tomatoes, 2 potatoes, eggs and dragonfruit')
    assert sorted(r['found']) == ['egg', 'potato', 'tomato']
    assert r['unknown'] == ['dragonfruit']
    assert parse_ingredients('')['found'] == []


def test_step_timers_and_whistles():
    assert parse_step('Simmer. |10m') == {'text': 'Simmer.', 'minutes': 10}
    assert parse_step('Pressure cook. |3w') == {'text': 'Pressure cook.', 'whistles': 3}
    assert parse_step('Serve hot.') == {'text': 'Serve hot.'}


# ---------- Suggestions ----------
def test_suggests_complete_dishes_first():
    ready = suggest(pantry=pantry_of(['egg', 'onion', 'tomato', 'green_chilli', 'turmeric']))['ready']
    assert any(r['recipe']['id'] == 'masala_omelette' for r in ready)
    assert all(not r['missing'] for r in ready)


def test_things_about_to_spoil_push_dishes_up():
    base = pantry_of(['onion', 'tomato', 'green_chilli', 'turmeric', 'cumin', 'red_chilli_powder', 'coriander_powder', 'garam_masala', 'ginger', 'garlic', 'peas'])
    fresh = suggest(pantry=base + [{'id': 'paneer', 'expiresAt': NOW + 10 * DAY}, {'id': 'egg', 'expiresAt': NOW + 10 * DAY}], now=NOW)
    spoiling = suggest(pantry=base + [{'id': 'paneer', 'expiresAt': NOW + DAY}, {'id': 'egg', 'expiresAt': NOW + 10 * DAY}], now=NOW)
    rank = lambda res: [r['recipe']['id'] for r in res['ready']].index('paneer_bhurji')  # noqa: E731
    assert rank(spoiling) < rank(fresh)
    assert 'paneer' in next(r for r in spoiling['ready'] if r['recipe']['id'] == 'paneer_bhurji')['usesSoon']


def test_filters():
    pantry = pantry_of(['egg', 'onion', 'tomato', 'chicken', 'leftover_rice', 'curd', 'sabudana', 'peanuts', 'potato', 'cumin', 'green_chilli'])
    dishes = lambda f: every_dish(suggest(pantry=pantry, filters=f))  # noqa: E731
    assert all(r['diet'] == 'veg' for r in dishes({'veg': True}))
    assert all(r['time'] <= 20 for r in dishes({'quick': True}))
    assert all('leftover' in r['tags'] for r in dishes({'leftover': True}))
    assert all('vrat' in r['tags'] for r in dishes({'vrat': True}))
    assert any(r['id'] == 'sabudana_khichdi' for r in dishes({'vrat': True}))


def test_ratings_change_the_order():
    pantry = pantry_of(['egg', 'onion', 'tomato', 'green_chilli', 'turmeric'])
    before = [r['recipe']['id'] for r in suggest(pantry=pantry)['ready']]
    loved = before[-1]
    after = [r['recipe']['id'] for r in suggest(pantry=pantry, ratings={loved: 5, before[0]: 1})['ready']]
    assert after.index(loved) < before.index(loved)


def test_buy_tips_point_to_the_most_useful_item():
    tips = buy_tips(pantry=pantry_of(['onion', 'tomato', 'green_chilli', 'turmeric', 'red_chilli_powder', 'ginger', 'garlic']))
    assert tips and len(tips[0]['dishes']) >= len(tips[-1]['dishes'])


# ---------- Family rules ----------
def test_vegetarian_member_hides_meat_and_egg():
    members = [{'name': 'Amma', 'diet': 'veg'}]
    result = suggest(pantry=pantry_of(['chicken', 'egg', 'onion', 'tomato', 'ginger', 'garlic', 'paneer']), members=members)
    assert all(r['diet'] == 'veg' for r in every_dish(result))
    assert household_check(RECIPE_BY_ID['chicken_curry'], members)['ok'] is False


def test_allergy_jain_onion_garlic_diabetic_and_fasting_rules():
    check = lambda rid, m: household_check(RECIPE_BY_ID[rid], [m])  # noqa: E731
    assert not check('palak_paneer', {'name': 'A', 'allergies': ['dairy']})['ok']
    assert not check('rava_upma', {'name': 'A', 'allergies': ['gluten']})['ok']
    poha = check('kanda_poha', {'name': 'Riya', 'allergies': ['nuts']})  # peanuts are optional: a tip, not hidden
    assert poha['ok'] and 'nuts' in ' '.join(poha['notes'])
    assert not check('aloo_gobi', {'name': 'A', 'jain': True})['ok']
    assert check('idli', {'name': 'A', 'jain': True})['ok']
    assert not check('chana_masala', {'name': 'A', 'noOnionGarlic': True})['ok']
    assert not check('sooji_halwa', {'name': 'Dad', 'diabetic': True})['ok']
    assert not check('dal_tadka', {'name': 'Maa', 'fasting': True})['ok']
    assert check('sabudana_khichdi', {'name': 'Maa', 'fasting': True})['ok']


def test_low_spice_member_gets_a_mild_portion_tip():
    r = household_check(RECIPE_BY_ID['tomato_pappu'], [{'name': 'Chintu', 'spice': 1}])
    assert r['ok'] and 'mild portion for Chintu' in ' '.join(r['notes'])


# ---------- Freshness ----------
def test_expiry_tracking():
    assert days_left({'expiresAt': NOW + 2 * DAY}, NOW) == 2
    assert days_left({'expiresAt': None}, NOW) is None
    assert default_expiry('tomato', NOW) > NOW
    assert default_expiry('rice', NOW) is None
    soon = use_soon([{'id': 'a', 'expiresAt': NOW + 5 * DAY}, {'id': 'b', 'expiresAt': NOW + DAY}, {'id': 'c', 'expiresAt': None}], NOW)
    assert [s['id'] for s in soon] == ['b']


# ---------- Chat, rescue, sharing, AI safety ----------
def test_chat_reply_works_like_a_whatsapp_bot():
    assert 'Kanda Poha' in chat_reply('I have poha, onion, potato, peanuts and lemon')['reply']
    assert 'Tell me what you have' in chat_reply('hello')['reply']


def test_bachao_finds_the_right_fix():
    assert find_rescue('dal is too salty')[0]['id'] == 'too_salty'
    assert any(r['id'] == 'burnt_bottom' for r in find_rescue('it got burnt'))
    assert len(find_rescue('')) == len(RESCUES)


def test_recipe_text_for_sharing():
    text = recipe_text(RECIPE_BY_ID['dal_tadka'])
    assert 'Dal Tadka' in text and re.search(r'1\. ', text)


def test_ai_recipes_are_checked_and_cleaned():
    r = normalize_ai_recipe({
        'name': 'Paneer Pepper Fry', 'time': 20, 'spice': 2,
        'ingredients': [{'name': 'paneer', 'quantity': '200 g'}, {'name': 'black pepper', 'quantity': '1 tsp'}, {'name': 'kokum', 'quantity': '2', 'optional': True}],
        'steps': [{'text': 'Fry paneer', 'minutes': 3}, 'Add pepper. |2m'],
    })
    assert r['ai'] is True
    assert r['ingredients'][0]['options'][0] == 'paneer'
    assert r['ingredients'][2]['custom'] == 'kokum'
    assert 'dairy' in r['allergens']
    assert r['steps'][1]['minutes'] == 2
    with pytest.raises(ValueError):
        normalize_ai_recipe({'name': 'x', 'ingredients': [], 'steps': []})
    with pytest.raises(ValueError):
        normalize_ai_recipe(None)


def test_publishing_rules_catch_mistakes():
    good = {'id': 'test_dal', 'name': 'Test', 'meal': ['lunch'], 'time': 20, 'serves': 2, 'spice': 1, 'tags': [],
            'ing': ['toor_dal:1 cup'], 'steps': ['Cook the dal well.', 'Add the tadka.']}
    assert validate_recipe(good) == []
    assert 'Unknown ingredient "mystery"' in validate_recipe({**good, 'ing': ['mystery:1']})
    assert any('gluten-free' in e for e in validate_recipe({**good, 'tags': ['gluten-free'], 'ing': ['atta:1 cup']}))
    assert any('food-safety' in e for e in validate_recipe({**good, 'ing': ['chicken:500 g']}))
    assert any('two steps' in e for e in validate_recipe({**good, 'steps': ['One step only']}))
