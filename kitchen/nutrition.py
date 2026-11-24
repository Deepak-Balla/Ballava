"""Calories and nutrition for recipes, worked out from the ingredient list.

How it works:
1. Read each quantity the way a cook writes it ("1/2 cup", "2 cloves", "1 medium, chopped", "a pinch")
   and turn it into grams, using what a cup, spoon or piece of that ingredient weighs (data/nutrition.py).
2. Add up the nutrition of the required ingredients. Optional extras are shown per line but not counted.
3. Recipes rarely list cooking oil (it is "always in the kitchen"), so when the steps fry or temper,
   about 1.5 tsp of oil per serving is added (1 tbsp per serving for deep frying).
4. Divide by the number of servings.

Everything is an estimate, and the app always says so.
"""
import re

from .data.ingredients import BY_ID
from .data.nutrition import FIELDS

FRACTIONS = {'½': ' 1/2', '¼': ' 1/4', '¾': ' 3/4', '⅓': ' 1/3', '⅔': ' 2/3', '–': '-', '—': '-'}
NUMBER = r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)'
AMOUNT = re.compile(rf'({NUMBER})(?:\s*(?:-|to)\s*({NUMBER}))?')
UNITS = {
    'kg': 'kg', 'kgs': 'kg', 'g': 'g', 'gm': 'g', 'gms': 'g', 'gram': 'g', 'grams': 'g', 'ml': 'ml',
    'l': 'l', 'litre': 'l', 'litres': 'l', 'liter': 'l', 'liters': 'l',
    'tsp': 'tsp', 'teaspoon': 'tsp', 'teaspoons': 'tsp', 'tbsp': 'tbsp', 'tablespoon': 'tbsp', 'tablespoons': 'tbsp',
    'cup': 'cup', 'cups': 'cup', 'inch': 'inch', 'inches': 'inch', 'clove': 'clove', 'cloves': 'clove',
    'slice': 'slice', 'slices': 'slice', 'bunch': 'bunch', 'bunches': 'bunch', 'packet': 'packet', 'packets': 'packet',
    'handful': 'handful', 'handfuls': 'handful', 'pinch': 'pinch', 'pinches': 'pinch', 'piece': 'piece', 'pieces': 'piece',
}
SIZES = {'small': 0.6, 'medium': 1.0, 'large': 1.5, 'big': 1.5}
DEFAULT_GRAMS = {'inch': 6, 'clove': 4, 'slice': 25, 'bunch': 100, 'packet': 70, 'handful': 30, 'pinch': 0.3}
# "to serve", "a little", "for roasting": a small amount.
A_LITTLE = {'ghee': 5, 'butter': 5, 'oil': 5, 'bread': 25, 'sooji': 15, 'lemon': 15}
OIL_TSP = 4.5


def to_number(text):
    text = text.strip()
    if ' ' in text:
        whole, frac = text.split(None, 1)
        return float(whole) + to_number(frac)
    if '/' in text:
        top, bottom = text.split('/')
        return float(top) / float(bottom) if float(bottom) else 0.0
    return float(text)


def measures_of(id_):
    return (BY_ID.get(id_) or {}).get('measures') or {}


def unit_grams(id_, unit):
    """What one unit (cup, tsp, piece...) of this ingredient weighs, in grams."""
    m = measures_of(id_)
    cup = m.get('cup') or (m['tsp'] * 48 if m.get('tsp') else None)
    if unit == 'g':
        return 1.0
    if unit == 'kg':
        return 1000.0
    if unit in ('ml', 'l'):
        per_ml = (cup or 240) / 240
        return per_ml * (1000 if unit == 'l' else 1)
    if unit == 'cup':
        return cup or 120
    if unit == 'tbsp':
        return m.get('tbsp') or (m['tsp'] * 3 if m.get('tsp') else (cup or 120) / 16)
    if unit == 'tsp':
        return m.get('tsp') or (m['tbsp'] / 3 if m.get('tbsp') else (cup or 120) / 48)
    if unit in ('piece', None):
        return m.get('piece') or m.get(unit or 'piece') or 10
    return m.get(unit) or m.get('piece') or DEFAULT_GRAMS.get(unit, 10)


def grams(id_, qty):
    """'1/2 cup' of toor_dal -> (100.0, False). The second value is True when the amount had to be guessed."""
    text = str(qty or '').lower()
    for k, v in FRACTIONS.items():
        text = text.replace(k, v)
    main = re.sub(r'\(.*?\)', ' ', text)
    inside = ' '.join(re.findall(r'\((.*?)\)', text))
    for part in (main, inside):
        found = _amount(id_, part)
        if found is not None:
            return found, False
    for word, unit in (('lemon-sized', 'lemon-sized'), ('lemon sized', 'lemon-sized'), ('pinch', 'pinch'), ('handful', 'handful'),
                       ('bunch', 'bunch'), ('bay leaf', 'piece')):
        if word in text:
            return unit_grams(id_, unit) * _size(text), False
    if 'piece' in text:
        return unit_grams(id_, 'piece') * _size(text), False
    return A_LITTLE.get(id_, 5.0), True


def _size(text):
    return next((v for k, v in SIZES.items() if re.search(rf'\b{k}\b', text)), 1.0)


def _amount(id_, text):
    m = AMOUNT.search(text)
    if not m:
        return None
    low = to_number(m.group(1))
    n = (low + to_number(m.group(2))) / 2 if m.group(2) else low
    after = re.findall(r'[a-z-]+', text[m.end():])[:3]
    unit = next((UNITS[w] for w in after if w in UNITS), None)
    if unit is None and 'lemon-sized' in after:
        unit = 'lemon-sized'
    size = _size(' '.join(after)) if unit in (None, 'piece') else 1.0
    return n * unit_grams(id_, unit) * size


def per100(id_):
    return (BY_ID.get(id_) or {}).get('nutrition')


def line(id_, qty):
    """Nutrition of one ingredient line, or None if we have no data for that ingredient."""
    info = per100(id_)
    if not info:
        return None
    g, guessed = grams(id_, qty)
    out = {k: info.get(k, 0) * g / 100 for k in FIELDS}
    out['grams'] = g
    out['guessed'] = guessed
    return out


DEEP_FRY = re.compile(r'deep[- ]?fr|fry (?:them |it )?in hot oil|until puffed')
FRYING = re.compile(r'\boil\b|tadka|temper|fry|saut|roast .* in')
FATS = {'oil', 'ghee', 'butter'}


def oil_per_serving(recipe):
    """Tsp of cooking oil per serving that the recipe uses but doesn't list."""
    steps = ' '.join(s.get('text', '') for s in recipe.get('steps') or []).lower()
    if DEEP_FRY.search(steps):
        return 3.0
    if any(it['options'][0] == 'oil' and not it.get('optional') for it in recipe.get('ingredients') or [] if it.get('options')):
        return 0.0  # the recipe says how much oil, so it's already counted
    lists_fat = any(it['options'][0] in FATS for it in recipe.get('ingredients') or [] if it.get('options'))
    if re.search(r'\boil\b', steps) or (not lists_fat and FRYING.search(steps)):
        return 1.5
    return 0.0


def recipe_nutrition(recipe):
    """{'kcal', 'protein', 'carbs', 'fat', 'fibre'} per serving, plus the whole dish and each line's calories."""
    totals = dict.fromkeys(FIELDS, 0.0)
    lines, unknown, guessed = [], [], 0
    for it in recipe.get('ingredients') or []:
        id_ = it['options'][0] if it.get('options') else None
        got = line(id_, it.get('qty')) if id_ else None
        lines.append({'kcal': round(got['kcal']), 'grams': round(got['grams'])} if got else None)
        if it.get('optional'):
            continue
        if not got:
            unknown.append(it.get('custom') or id_)
            continue
        guessed += got['guessed']
        for k in FIELDS:
            totals[k] += got[k]
    serves = max(1, int(recipe.get('serves') or 1))
    oil_tsp = oil_per_serving(recipe)
    if oil_tsp:
        oil = per100('oil')
        for k in FIELDS:
            totals[k] += oil[k] * oil_tsp * OIL_TSP * serves / 100
    per = {k: round(v / serves) if k == 'kcal' else round(v / serves, 1) for k, v in totals.items()}
    return {**per, 'totalKcal': round(totals['kcal']), 'serves': serves, 'oilTsp': oil_tsp,
            'lines': lines, 'unknown': unknown, 'source': 'ballava'}


def summary(n):
    """'about 230 kcal per serving (protein 12 g, carbs 30 g, fat 7 g)'"""
    if not n:
        return ''
    return (f"about {n['kcal']} kcal per serving (protein {round(n['protein'])} g, carbs {round(n['carbs'])} g, "
            f"fat {round(n['fat'])} g, fibre {round(n['fibre'])} g)")
