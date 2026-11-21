"""Ballava cooking brain: understanding what people type, matching dishes, family rules.

Plain Python functions with no Django code, so they are easy to read and test on their own.
Recipe and result dictionaries keep camelCase keys (like 'majorMissing') because the
browser screens read them as-is.
"""
import math
import re
import time

from .data.ingredients import ASSUMED, BY_ID, INGREDIENTS, JAIN_BLOCKED, ONION_GARLIC
from .data.recipes import RECIPES
from .data.rescue import RESCUES
from .nutrition import recipe_nutrition

DAY_MS = 24 * 60 * 60 * 1000
DIET_RANK = {'veg': 0, 'egg': 1, 'nonveg': 2}
DIETS = list(DIET_RANK)


def now_ms():
    return int(time.time() * 1000)


# ------------------------------------------------------------------ recipe prep
def parse_ingredient_line(line):
    """'moong_dal|masoor_dal?:1/2 cup' -> {'options': [...], 'qty': '1/2 cup', 'optional': True}"""
    key, sep, qty = line.partition(':')
    qty = qty.strip() if sep else ''
    optional = key.endswith('?')
    if optional:
        key = key[:-1]
    return {'options': [s.strip() for s in key.split('|') if s.strip()], 'qty': qty, 'optional': optional}


STEP_TAG = re.compile(r'\s*\|(\d+)([mw])\s*$')


def parse_step(step):
    """'Cook the dal. |3w' -> {'text': 'Cook the dal.', 'whistles': 3}"""
    m = STEP_TAG.search(step)
    if not m:
        return {'text': step.strip()}
    text = step[:m.start()].strip()
    return {'text': text, 'minutes': int(m.group(1))} if m.group(2) == 'm' else {'text': text, 'whistles': int(m.group(1))}


def prepare_recipe(raw):
    """Turn the compact recipe format into the full structure the app uses."""
    r = {'tags': [], **raw}
    ingredients = [parse_ingredient_line(line) for line in r['ing']]
    required = [i for i in ingredients if not i['optional']]

    # Diet: the strictest of the required ingredients (optional ones can be skipped).
    diet = 'veg'
    for it in required:
        level = min(DIET_RANK[BY_ID.get(i, {}).get('diet', 'veg')] for i in it['options'])
        if level > DIET_RANK[diet]:
            diet = DIETS[level]

    # Allergens: from required lines where EVERY option has that allergen.
    allergens = []
    for it in required:
        sets = [set(BY_ID.get(i, {}).get('allergens', [])) for i in it['options']]
        for a in BY_ID.get(it['options'][0], {}).get('allergens', []):
            if all(a in s for s in sets) and a not in allergens:
                allergens.append(a)

    def blocked_required(blocked):
        return any(all(i in blocked for i in it['options']) for it in required)

    recipe = {
        **r,
        'ingredients': ingredients,
        'steps': [parse_step(s) for s in r['steps']],
        'diet': diet,
        'allergens': allergens,
        'needsOnionGarlic': blocked_required(ONION_GARLIC),
        'jainOk': not blocked_required(JAIN_BLOCKED),
        'hasChilli': any(any(i in ('green_chilli', 'red_chilli_powder', 'dry_red_chilli') for i in it['options']) for it in ingredients),
    }
    recipe['nutrition'] = recipe_nutrition(recipe)
    return recipe


ALL_RECIPES = [prepare_recipe(r) for r in RECIPES]
RECIPE_BY_ID = {r['id']: r for r in ALL_RECIPES}


def recipes_from(extra_recipes=(), hidden=()):
    """The live recipe book: built-in dishes, admin edits replacing them by id, hidden ones removed."""
    replaced = {r['id'] for r in extra_recipes}
    gone = set(hidden)
    return [r for r in [*(r for r in ALL_RECIPES if r['id'] not in replaced), *extra_recipes] if r['id'] not in gone]


# ---------------------------------------------------------- text -> ingredients
def normalize(s):
    s = str(s).lower()
    s = re.sub(r'\(.*?\)', ' ', s)
    s = re.sub(r'[^a-zऀ-ൿ\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _build_aliases():
    pairs = []
    for ing in INGREDIENTS:
        names = {ing['id'].replace('_', ' '), ing['name'].lower(), *(a.lower() for a in ing['aliases'])}
        pairs.extend((normalize(n), ing['id']) for n in names)
    # Longest names first, so "leftover rice" beats "rice" and "hari mirch" beats "mirch".
    return sorted(pairs, key=lambda p: -len(p[0]))


ALIASES = _build_aliases()

FILLER = set('''and some a an the few of little bit kg g gm grams packet packets bunch piece pieces cup cups i have got in my
fridge aur hai kuch thoda with also fresh from only just there is are we left over leftover yesterday today for what can cook make'''.split())


def parse_ingredients(text):
    """'2 tamatar, pyaz and leftover chawal' -> {'found': ['tomato', 'onion', 'leftover_rice'], 'unknown': []}"""
    rest = ' ' + normalize(text) + ' '
    found = []
    for alias, id_ in ALIASES:
        if not alias:
            continue
        for variant in (alias, alias + 's', alias + 'es'):
            needle = ' ' + variant + ' '
            if needle in rest:
                if id_ not in found:
                    found.append(id_)
                rest = ' | '.join(rest.split(needle))
    unknown = []
    for chunk in rest.split('|'):
        words = [w for w in chunk.strip().split(' ') if w and w not in FILLER]
        if words and ' '.join(words) not in unknown:
            unknown.append(' '.join(words))
    return {'found': found, 'unknown': unknown}


# ------------------------------------------------------------------- kitchen
def default_expiry(id_, now=None):
    days = BY_ID.get(id_, {}).get('shelfDays')
    return (now or now_ms()) + days * DAY_MS if days else None


def days_left(item, now=None):
    if not item.get('expiresAt'):
        return None
    return math.ceil((item['expiresAt'] - (now or now_ms())) / DAY_MS)


def use_soon(pantry, now=None, within=2):
    now = now or now_ms()
    soon = [p for p in pantry if (d := days_left(p, now)) is not None and d <= within]
    return sorted(soon, key=lambda p: p['expiresAt'])


# ------------------------------------------------------------------ household
def household_check(recipe, members=()):
    """Can everyone eat this? member: {name, diet, jain, noOnionGarlic, diabetic, fasting, allergies, spice, goals}"""
    notes = []
    for m in members:
        who = m.get('name') or 'Someone'
        allergies = m.get('allergies') or []
        if DIET_RANK[recipe['diet']] > DIET_RANK.get(m.get('diet') or 'nonveg', 2):
            return {'ok': False, 'reason': f"{who} doesn't eat {'egg' if recipe['diet'] == 'egg' else 'meat or fish'}"}
        allergy = next((a for a in allergies if a in recipe['allergens']), None)
        if allergy:
            return {'ok': False, 'reason': f'{who} is allergic to {allergy}'}
        if m.get('jain') and not recipe['jainOk']:
            return {'ok': False, 'reason': f'Not Jain-friendly (for {who})'}
        if m.get('noOnionGarlic') and recipe['needsOnionGarlic']:
            return {'ok': False, 'reason': f'{who} avoids onion and garlic'}
        if m.get('diabetic') and 'sweet' in recipe['tags']:
            return {'ok': False, 'reason': f'Sweet dish ({who} is diabetic)'}
        if m.get('fasting') and 'vrat' not in recipe['tags']:
            return {'ok': False, 'reason': f'{who} is fasting today'}
        if 'pregnancy' in (m.get('goals') or []) and recipe['time'] <= 15 and any(
                not it['optional'] and 'sprouts' in it['options'] for it in recipe['ingredients']):
            return {'ok': False, 'reason': f"Raw or lightly cooked sprouts aren't advised for {who} during pregnancy"}
        # Things we can work around: give a tip instead of hiding the dish.
        opt_allergen = next((a for a in allergies if any(
            it['optional'] and any(a in BY_ID.get(i, {}).get('allergens', []) for i in it['options']) for it in recipe['ingredients'])), None)
        if opt_allergen:
            notes.append(f'Skip the optional {opt_allergen} items for {who}.')
        if m.get('jain'):
            notes.append(f'For {who}: skip onion, garlic, ginger and root vegetables.')
        elif m.get('noOnionGarlic') and any(it['optional'] and any(i in ONION_GARLIC for i in it['options']) for it in recipe['ingredients']):
            notes.append(f'Skip onion and garlic for {who}.')
        if m.get('spice') and m['spice'] < recipe['spice'] and recipe['hasChilli']:
            notes.append(f'Take out a mild portion for {who} before adding chilli.')
    return {'ok': True, 'notes': list(dict.fromkeys(notes))}


# ------------------------------------------------------------------ matching
# Flavourings: nice to have, but a cook can manage without one.
FLAVOURINGS = ['green_chilli', 'coriander', 'curry_leaves', 'ginger', 'garlic', 'lemon']


def is_spice(id_):
    return BY_ID.get(id_, {}).get('category') == 'Spices' or id_ in FLAVOURINGS


def match_recipe(recipe, pantry_ids, soon_ids=()):
    have = set(pantry_ids) | set(ASSUMED)
    required = [i for i in recipe['ingredients'] if not i['optional']]
    missing = [it for it in required if not any(i in have for i in it['options'])]
    # A missing masala is a smaller problem than a missing main ingredient.
    spice_missing = [it for it in missing if all(is_spice(i) for i in it['options'])]
    major_missing = [it for it in missing if not all(is_spice(i) for i in it['options'])]
    major = [it for it in required if not all(is_spice(i) for i in it['options'])]
    uses = lambda id_: any(id_ in it['options'] for it in recipe['ingredients'])  # noqa: E731
    return {
        'used': sum(1 for i in pantry_ids if not is_spice(i) and uses(i)),
        'total': len(required),
        'haveCount': len(required) - len(missing),
        'majorTotal': len(major),
        'majorHave': len(major) - len(major_missing),
        'missing': [it['options'] for it in missing],
        'majorMissing': [it['options'] for it in major_missing],
        'spiceMissing': [it['options'] for it in spice_missing],
        'usesSoon': [i for i in soon_ids if uses(i)],
        'optionalHave': sum(1 for i in recipe['ingredients'] if i['optional'] and any(o in have for o in i['options'])),
    }


LIGHT_KCAL, PROTEIN_G = 400, 12


def nutrition_ok(recipe, filters):
    """The 'Light' (400 kcal or less a serving) and 'Protein-rich' (12 g or more) filters."""
    n = recipe.get('nutrition') or {}
    if filters.get('light') and (n.get('kcal') is None or n['kcal'] > LIGHT_KCAL):
        return False
    if filters.get('protein') and (n.get('protein') or 0) < PROTEIN_G:
        return False
    return True


def suggest(pantry=(), members=(), filters=None, ratings=None, now=None, extra_recipes=(), hidden=()):
    """Dishes you can cook now ('ready') and nearly cook ('almost'), best first. ratings: {recipe id: 1-5}"""
    filters, ratings = filters or {}, ratings or {}
    pantry_ids = [p['id'] for p in pantry]
    soon_ids = [p['id'] for p in use_soon(pantry, now)]
    results = []
    for recipe in recipes_from(extra_recipes, hidden):
        tags = recipe['tags']
        if filters.get('veg') and recipe['diet'] != 'veg':
            continue
        if filters.get('quick') and recipe['time'] > 20:
            continue
        if filters.get('leftover') and 'leftover' not in tags:
            continue
        if filters.get('vrat') and 'vrat' not in tags:
            continue
        if filters.get('healthy') and 'diabetic-friendly' not in tags:
            continue
        if filters.get('meal') and filters['meal'] not in recipe['meal']:
            continue
        if not nutrition_ok(recipe, filters):
            continue
        house = household_check(recipe, members)
        if not house['ok']:
            continue
        m = match_recipe(recipe, pantry_ids, soon_ids)
        if m['majorHave'] == 0:
            continue
        coverage = m['majorHave'] / max(1, m['majorTotal'])
        rating = ratings.get(recipe['id'])
        score = (coverage * 100 - len(m['majorMissing']) * 12 - len(m['spiceMissing']) * 3 + len(m['usesSoon']) * 15
                 + m['optionalHave'] * 2 + m['used'] * 5 + ((rating - 3) * 6 if rating else 0))
        results.append({'recipe': recipe, **m, 'coverage': coverage, 'score': score, 'notes': house['notes']})
    results.sort(key=lambda r: (-r['score'], r['recipe']['time']))
    return {
        'ready': [r for r in results if not r['missing']],
        'almost': [r for r in results if r['missing'] and len(r['majorMissing']) <= 2],
    }


def buy_tips(limit=3, **params):
    """'Buy just one thing': the missing ingredient that unlocks the most new dishes."""
    counts = {}
    for r in suggest(**params)['almost']:
        if len(r['majorMissing']) != 1:
            continue
        counts.setdefault(r['majorMissing'][0][0], []).append(r['recipe']['name'])
    tips = [{'id': id_, 'name': BY_ID.get(id_, {}).get('name', id_), 'dishes': dishes} for id_, dishes in counts.items()]
    return sorted(tips, key=lambda t: -len(t['dishes']))[:limit]


# ------------------------------------------------------------------- rescue
STOP = {'too', 'much', 'the', 'and', 'got', 'has', 'have', 'its', 'very', 'bit', 'my', 'is', 'it', 'or', 'gaya', 'hai', 'ho'}


def find_rescue(text):
    words = [w for w in normalize(text).split(' ') if len(w) > 2 and w not in STOP]
    if not words:
        return list(RESCUES)
    scored = []
    for r in RESCUES:
        keys = [k for k in re.split(r'[^a-z]+', (r['title'] + ' ' + r['keywords']).lower()) if len(k) > 2 and k not in STOP]
        score = sum(1 for w in words if any(k.startswith(w) or w.startswith(k) for k in keys))
        if score:
            scored.append((score, r))
    return [r for _, r in sorted(scored, key=lambda x: -x[0])]


# ------------------------------------------------------------------- sharing
def name_of(id_):
    return BY_ID.get(id_, {}).get('name', id_)


def shopping_text(items):
    return 'Ballava shopping list:\n' + '\n'.join(f'- {name_of(i)}' for i in items)


def recipe_text(recipe):
    ing = [f"- {' / '.join(name_of(i) for i in it['options'])}{': ' + it['qty'] if it['qty'] else ''}{' (optional)' if it['optional'] else ''}"
           for it in recipe['ingredients']]
    steps = [f"{n}. {s['text']}" for n, s in enumerate(recipe['steps'], 1)]
    return f"{recipe['name']} ({recipe['time']} min)\n\nIngredients:\n" + '\n'.join(ing) + '\n\nSteps:\n' + '\n'.join(steps) + '\n\nShared from Ballava'


def chat_reply(text, **opts):
    """A short, WhatsApp-style reply: the same brain a chat bot would use."""
    parsed = parse_ingredients(text)
    found, unknown = parsed['found'], parsed['unknown']
    if not found:
        return {'found': found, 'unknown': unknown,
                'reply': 'Tell me what you have, for example: "rice, 2 tomatoes, onion, curd". I\'ll suggest what to cook.'}
    result = suggest(pantry=[{'id': i} for i in found], **opts)
    pick = (result['ready'] + result['almost'])[:3]
    if not pick:
        return {'found': found, 'unknown': unknown,
                'reply': "I couldn't find a dish with just that. Add a few more items, like onion, tomato or rice."}

    def line(n, r):
        if r['majorMissing']:
            status = ', needs ' + ', '.join(name_of(o[0]) for o in r['majorMissing'])
        else:
            status = ', you have the main items' if r['spiceMissing'] else ', you have everything'
        return f"{n}. {r['recipe']['name']} ({r['recipe']['time']} min){status}"

    lines = [line(n, r) for n, r in enumerate(pick, 1)]
    return {'found': found, 'unknown': unknown, 'dishes': [r['recipe']['id'] for r in pick],
            'reply': f"With {', '.join(name_of(i) for i in found)} you can make:\n" + '\n'.join(lines)
                     + '\n(I assume you have salt, oil and basic masalas.)'}


# ------------------------------------------------------------------- AI recipes
def normalize_ai_recipe(raw):
    """Check and clean a recipe the AI invented, so it can be shown like any other."""
    if not isinstance(raw, dict):
        raise ValueError('AI returned no recipe')
    name = str(raw.get('name') or '')[:80]
    if not name:
        raise ValueError('AI recipe has no name')
    ing = []
    for x in (raw.get('ingredients') if isinstance(raw.get('ingredients'), list) else [])[:25]:
        label = (x if isinstance(x, str) else str((x or {}).get('name') or '')).strip()[:60]
        parsed = parse_ingredients(label)
        id_ = parsed['found'][0] if parsed['found'] else None
        qty = '' if isinstance(x, str) else str(x.get('quantity') or x.get('qty') or '')
        item = {'options': [id_ or label.lower()[:40]], 'qty': qty, 'optional': bool(isinstance(x, dict) and x.get('optional'))}
        if not id_ or parsed['unknown']:
            # Keep the AI's own words when they say more than the ingredient we matched
            # ("Almond butter" is not just butter): they are shown, and checked for diet and allergens.
            item['custom'] = label
        ing.append(item)
    steps = []
    for s in (raw.get('steps') if isinstance(raw.get('steps'), list) else [])[:15]:
        if isinstance(s, str):
            step = parse_step(s)
        else:
            step = {'text': str((s or {}).get('text') or '')}
            if (s or {}).get('minutes'):
                step['minutes'] = min(240, int(s['minutes']))
        if step['text']:
            steps.append(step)
    if not ing or not steps:
        raise ValueError('AI recipe is incomplete')

    def number(v, default):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    h = 7
    for c in name:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    h = h - 0x100000000 if h >= 0x80000000 else h
    required = [i for i in ing if not i['optional']]
    first = lambda it: it['options'][0]  # noqa: E731
    # Diet and allergens: never trust a single source. Take the strictest of the matched ingredients,
    # words in the ingredient names we couldn't match, and what the AI itself says.
    diet = 'veg'
    allergens = []
    for it in required:
        for d in (BY_ID.get(first(it), {}).get('diet'), _diet_from_words(it.get('custom'))):
            if d and DIET_RANK[d] > DIET_RANK[diet]:
                diet = d
        allergens.extend(BY_ID.get(first(it), {}).get('allergens', []))
        allergens.extend(_allergens_from_words(it.get('custom')))
    if raw.get('diet') in DIET_RANK and DIET_RANK[raw['diet']] > DIET_RANK[diet]:
        diet = raw['diet']
    if isinstance(raw.get('allergens'), list):
        allergens.extend(a for a in map(str, raw['allergens']) if a in ALLERGENS)
    meal = [m for m in (raw.get('meal') if isinstance(raw.get('meal'), list) else []) if m in ('breakfast', 'lunch', 'dinner', 'snack')]
    spice = number(raw.get('spice'), 2)
    recipe = {
        'id': 'ai_' + _base36(abs(h)), 'name': name, 'alt': str(raw['alt'])[:60] if raw.get('alt') else None,
        'cuisine': str(raw.get('cuisine') or 'Ballava original')[:40], 'meal': list(dict.fromkeys(meal)) or ['lunch', 'dinner'],
        'time': max(5, min(240, number(raw.get('time'), 30) or 30)), 'serves': max(1, min(12, number(raw.get('serves'), 2) or 2)),
        'spice': spice if spice in (1, 2, 3) else 2, 'tags': ['ai'],
        'tip': str(raw['why'])[:400] if raw.get('why') else None,
        'safety': str(raw['safety'])[:400] if raw.get('safety') else None,
        'ingredients': ing, 'steps': steps, 'ai': True, 'diet': diet,
        'allergens': list(dict.fromkeys(allergens)),
        'needsOnionGarlic': any(first(it) in ONION_GARLIC for it in required),
        'jainOk': not any(first(it) in JAIN_BLOCKED for it in required),
        'hasChilli': any(first(it) in ('green_chilli', 'red_chilli_powder', 'dry_red_chilli') for it in ing),
    }
    recipe['nutrition'] = _ai_nutrition(recipe, raw.get('nutrition'))
    if raw.get('requested') is True:
        recipe['requested'] = True  # the user asked for this dish by name
    return recipe


GENERIC_WORDS = {'quick', 'easy', 'simple', 'style', 'home', 'homestyle', 'special', 'recipe', 'with', 'and', 'the', 'healthy', 'tasty', 'classic'}


def names_dish(question, dish_name):
    """Did the question ask for this dish by name? 'give me chicken biryani' names 'Chicken Biryani' (and 'Easy Chicken Biryani')."""
    q = set(normalize(question).split())
    words = [w for w in normalize(dish_name).split() if len(w) > 2 and w not in GENERIC_WORDS]
    hits = sum(1 for w in words if w in q or w.rstrip('s') in q)
    return bool(words) and hits >= min(2, len(words)) and hits / len(words) >= 0.6


ALLERGENS = ('dairy', 'gluten', 'nuts', 'egg', 'seafood')
_WORDS = {
    'nonveg': r'chicken|mutton|lamb|goat|meat|keema|beef|pork|bacon|ham|fish|prawn|shrimp|crab|squid|anchov|sardine|tuna|salmon',
    'egg': r'\begg',
    'dairy': r'milk|cream|cheese|butter|ghee|paneer|curd|yog(h)?urt|khoa|khoya|malai|dahi',
    'gluten': r'wheat|maida|atta|bread|semolina|rava|sooji|suji|pasta|noodle|vermicelli|semiya|barley|biscuit',
    'nuts': r'peanut|groundnut|cashew|almond|walnut|pistachio|hazelnut|\bnuts?\b',
    'seafood': r'fish|prawn|shrimp|crab|squid|lobster|anchov|sardine|tuna|salmon',
}


def _diet_from_words(text):
    t = str(text or '').lower()
    return 'nonveg' if re.search(_WORDS['nonveg'], t) else 'egg' if re.search(_WORDS['egg'], t) else None


def _allergens_from_words(text):
    t = str(text or '').lower()
    return [a for a in ALLERGENS if re.search(_WORDS[a], t)] if t else []


def _ai_nutrition(recipe, claimed):
    """Our own calorie count when we know most of the ingredients; otherwise the AI's estimate, marked as such."""
    ours = recipe_nutrition(recipe)
    required = [i for i in recipe['ingredients'] if not i['optional']]
    known = sum(1 for i in required if BY_ID.get(i['options'][0], {}).get('nutrition'))
    if required and known / len(required) >= 0.75:
        return ours
    try:
        kcal = float((claimed or {}).get('kcal'))
    except (TypeError, ValueError, AttributeError):
        return ours
    if not 20 <= kcal <= 2500:
        return ours

    def grams(key):
        try:
            return round(max(0.0, min(300.0, float(claimed.get(key) or 0))), 1)
        except (TypeError, ValueError):
            return 0.0
    return {**ours, 'kcal': round(kcal), 'protein': grams('protein'), 'carbs': grams('carbs'), 'fat': grams('fat'),
            'fibre': ours['fibre'], 'totalKcal': round(kcal * ours['serves']), 'source': 'ai'}


def _base36(n):
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    out = ''
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out


# ------------------------------------------------------------------- admin content
_BUILTIN_INGREDIENTS = len(INGREDIENTS)
_BUILTIN_RESCUES = len(RESCUES)


def apply_catalog(ingredients=(), rescues=()):
    """Add what admins published (new ingredients and Bachao fixes) to the built-in catalog."""
    global ALIASES
    for old in INGREDIENTS[_BUILTIN_INGREDIENTS:]:
        BY_ID.pop(old['id'], None)
    del INGREDIENTS[_BUILTIN_INGREDIENTS:]
    for raw in ingredients:
        if raw['id'] in BY_ID:
            continue
        item = {'allergens': [], 'diet': 'veg', 'aliases': [], 'shelfDays': None, 'nutrition': None, 'measures': {}, **raw}
        INGREDIENTS.append(item)
        BY_ID[item['id']] = item
    ALIASES = _build_aliases()
    del RESCUES[_BUILTIN_RESCUES:]
    RESCUES.extend(rescues)


def validate_recipe(raw):
    """The checks every recipe must pass before it can be published. Returns a list of problems."""
    if not isinstance(raw, dict):
        return ['Recipe is empty']
    errors = []
    if not re.fullmatch(r'[a-z0-9_]{2,40}', str(raw.get('id') or '')):
        errors.append('Id must be 2-40 lowercase letters, numbers or underscores')
    if not str(raw.get('name') or '').strip():
        errors.append('Name is required')

    def positive(v):
        try:
            return float(v) > 0
        except (TypeError, ValueError):
            return False

    if not positive(raw.get('time')):
        errors.append('Time must be more than 0 minutes')
    if not positive(raw.get('serves')):
        errors.append('Serves must be more than 0')
    if raw.get('spice') not in (1, 2, 3):
        errors.append('Spice must be 1, 2 or 3')
    if not raw.get('meal'):
        errors.append('Choose at least one meal type')
    if not raw.get('ing'):
        errors.append('Add at least one ingredient')
    if len(raw.get('steps') or []) < 2:
        errors.append('Add at least two steps')
    if errors:
        return errors
    for line in raw['ing']:
        for id_ in parse_ingredient_line(line)['options']:
            if id_ not in BY_ID:
                errors.append(f'Unknown ingredient "{id_}"')
    if errors:
        return errors
    r = prepare_recipe(raw)
    tags = r['tags']
    if not any(not i['optional'] for i in r['ingredients']):
        errors.append('At least one ingredient must be required')
    if any(len(s['text']) <= 5 for s in r['steps']):
        errors.append('One of the steps is too short')
    if 'jain' in tags and not r['jainOk']:
        errors.append('Tagged jain but needs onion, garlic or root vegetables')
    if 'vrat' in tags and r['needsOnionGarlic']:
        errors.append('Tagged vrat but needs onion or garlic')
    if 'gluten-free' in tags and 'gluten' in r['allergens']:
        errors.append('Tagged gluten-free but contains gluten')
    if 'diabetic-friendly' in tags and 'sweet' in tags:
        errors.append('A sweet dish cannot be tagged diabetic-friendly')
    if r['diet'] == 'nonveg' and not r.get('safety'):
        errors.append('Meat and fish dishes need a food-safety note')
    return errors
