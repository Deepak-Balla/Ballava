"""Tests for calories and nutrition (kitchen/nutrition.py and kitchen/data/nutrition.py)."""
import pytest

from kitchen import nutrition
from kitchen.data.ingredients import INGREDIENTS
from kitchen.data.nutrition import NUTRITION
from kitchen.engine import ALL_RECIPES, RECIPE_BY_ID, normalize_ai_recipe, suggest

R = RECIPE_BY_ID


def test_every_ingredient_has_nutrition():
    assert {i['id'] for i in INGREDIENTS} == set(NUTRITION), 'every ingredient, and nothing extra'
    for i in INGREDIENTS:
        n = i['nutrition']
        assert 0 <= n['kcal'] <= 900, i['id']
        # Protein and digestible carbs give 4 kcal a gram, fibre about 2 and fat 9: the numbers must roughly add up.
        if n['kcal'] > 50:
            energy = 4 * n['protein'] + 4 * max(0, n['carbs'] - n['fibre']) + 2 * n['fibre'] + 9 * n['fat']
            assert 0.75 * n['kcal'] <= energy <= 1.25 * n['kcal'], i['id']


@pytest.mark.parametrize('id_, qty, grams', [
    ('toor_dal', '1/2 cup', 100), ('toor_dal', '3/4 cup', 150), ('atta', '1.5-2 cups', 210), ('onion', '1, chopped', 110),
    ('onion', '1 small, chopped', 66), ('tomato', '2', 200), ('garlic', '4 cloves', 16), ('ginger', '1 inch', 6),
    ('turmeric', '1/2 tsp', 1.5), ('ghee', '1 tbsp', 13), ('paneer', '200 g, cubed', 200), ('chicken', '500 g, curry cut', 500),
    ('spinach', '1 big bunch (about 250 g)', 250), ('hing', 'a pinch', 0.3), ('coriander', 'a handful', 10),
    ('green_chilli', '1-2, chopped', 6), ('lemon', '1/2', 15), ('egg', '4, hard boiled', 200), ('bread', '4 slices', 100),
    ('tamarind', 'a lemon-sized piece', 15), ('leftover_rice', '1/2 cup cooked (or 3 tbsp raw)', 80), ('rice', '1 cup (basmati best)', 185),
])
def test_quantities_become_grams(id_, qty, grams):
    got, guessed = nutrition.grams(id_, qty)
    assert got == pytest.approx(grams, rel=0.02) and not guessed


def test_unclear_amounts_are_small_guesses():
    got, guessed = nutrition.grams('butter', 'to spread')
    assert guessed and got == 5


def test_every_recipe_has_sensible_calories():
    for r in ALL_RECIPES:
        n = r['nutrition']
        assert 3 <= n['kcal'] <= 800, (r['id'], n['kcal'])
        assert n['totalKcal'] == pytest.approx(n['kcal'] * n['serves'], abs=n['serves'])
        assert len(n['lines']) == len(r['ingredients']) and not n['unknown'], r['id']


def test_spot_checks_against_home_cooking():
    assert 180 <= R['dal_tadka']['nutrition']['kcal'] <= 320
    assert 200 <= R['kanda_poha']['nutrition']['kcal'] <= 350
    assert R['chicken_curry']['nutrition']['protein'] >= 20
    assert R['cucumber_raita']['nutrition']['kcal'] < 120
    assert R['dal_tadka']['nutrition']['oilTsp'] == 1.5, 'tadka in oil is counted even though oil is not listed'
    assert R['idli']['nutrition']['oilTsp'] == 0, 'steamed'


def test_light_and_protein_filters():
    pantry = [{'id': i} for i in ['rice', 'toor_dal', 'onion', 'tomato', 'paneer', 'spinach', 'egg', 'curd', 'atta', 'potato']]
    light = suggest(pantry=pantry, filters={'light': True})
    assert light['ready'] and all(r['recipe']['nutrition']['kcal'] <= 400 for r in light['ready'] + light['almost'])
    protein = suggest(pantry=pantry, filters={'protein': True})
    assert protein['ready'] and all(r['recipe']['nutrition']['protein'] >= 12 for r in protein['ready'] + protein['almost'])


def test_ai_recipes_get_calories_and_safe_labels():
    raw = {'name': 'Paneer Wrap', 'meal': ['snack', 'tea-time'], 'diet': 'veg', 'serves': 2, 'time': 15,
           'ingredients': [{'name': 'Paneer', 'quantity': '200 g'}, {'name': 'Wheat flour (atta)', 'quantity': '1 cup'}],
           'steps': ['Make the dough.', 'Fill and roll.'], 'nutrition': {'kcal': 999}}
    r = normalize_ai_recipe(raw)
    assert r['meal'] == ['snack'] and r['nutrition']['source'] == 'ballava', 'we know these ingredients, so we count ourselves'
    assert 'dairy' in r['allergens'] and 'gluten' in r['allergens']
    odd = normalize_ai_recipe({'name': 'Mystery Curry', 'diet': 'veg', 'nutrition': {'kcal': 420, 'protein': 30},
                               'ingredients': [{'name': 'Smoked anchovies', 'quantity': '100 g'}, {'name': 'Almond butter', 'quantity': '2 tbsp'}],
                               'steps': ['Cook it well.', 'Serve it hot.']})
    assert odd['diet'] == 'nonveg', 'words in unknown ingredients are checked too, whatever the AI says'
    assert {'seafood', 'nuts', 'dairy'} <= set(odd['allergens'])
    assert odd['nutrition']['kcal'] == 420 and odd['nutrition']['source'] == 'ai', "unknown ingredients: use the AI's estimate"
