"""The brain behind the admin's recipe editor (kitchen/static/kitchen/recipe_editor.js).

- read_text: turns a recipe pasted from anywhere (WhatsApp, a website, a notebook) into the editor's fields, without AI.
- from_ai: the same, for a recipe the AI wrote or read.
- check: what still needs fixing before publishing, in plain words, plus calories, diet, allergens and suggested tags.
- make_id: the recipe's internal id, so admins never have to invent one.

Nothing here publishes anything: an admin always looks it over first.
"""
import re

from . import engine, nutrition
from .data.ingredients import CATEGORIES
from .models import Ingredient, Recipe

MEALS = [('breakfast', 'Breakfast'), ('lunch', 'Lunch'), ('dinner', 'Dinner'), ('snack', 'Snack'), ('side', 'Side dish'), ('dessert', 'Dessert')]
TAGS = [
    ('quick', 'Quick', '20 minutes or less'), ('kid-friendly', 'Kid-friendly', ''), ('tiffin', 'Good for tiffin', 'Packs well in a lunchbox'),
    ('high-protein', 'High protein', '12 g or more a serving'), ('diabetic-friendly', 'Diabetic-friendly', ''), ('gluten-free', 'Gluten-free', ''),
    ('jain', 'Jain', 'No onion, garlic, ginger or root vegetables'), ('vrat', 'Fasting (vrat)', 'Suggested on fasting days'),
    ('one-pot', 'One pot', ''), ('no-cook', 'No cooking', ''), ('leftover', 'Uses leftovers', ''), ('sweet', 'Sweet', 'Hidden from diabetic family members'),
    ('comfort', 'Comfort food', ''),
]
AMOUNTS = ['1 cup', '1/2 cup', '1/4 cup', '2 cups', '1 tbsp', '2 tbsp', '1 tsp', '1/2 tsp', '1/4 tsp', '1', '2', '1 medium, chopped', '2 cloves',
           '1 inch', '100 g', '200 g', '250 g', '500 g', 'a pinch', 'a handful', 'to taste', 'a few']
SAFETY = {
    'chicken': 'Cook chicken until no pink remains and juices run clear. Wash hands and boards after touching raw meat.',
    'mutton': 'Cook mutton until tender all through, and keep raw meat away from ready-to-eat food.',
    'fish': 'Use fish the day you buy it, or keep it frozen. Cook until it flakes easily.',
    'prawns': 'Prawns are done when pink and curled. Use them the day you buy them or keep them frozen.',
    'rajma': 'Always boil rajma fully until very soft. Undercooked kidney beans can make you sick.',
    'leftover_rice': 'Use rice that went into the fridge within 1-2 hours of cooking.',
}
MEAT_NOTE = 'Cook until done all the way through, and wash hands and boards after touching it raw.'


# ---------------------------------------------------------------- ids
def make_id(name):
    """'Gongura Pappu' -> 'gongura_pappu'. Never one that is in use (or a built-in one, which it would replace)."""
    base = re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')[:34] or 'recipe'
    if len(base) < 2:
        base = 'recipe_' + base
    taken = set(engine.RECIPE_BY_ID) | set(Recipe.objects.filter(recipe_id__startswith=base).values_list('recipe_id', flat=True))
    return next(i for i in [base, *(f'{base}_{n}' for n in range(2, 10000))] if i not in taken)


# ---------------------------------------------------------------- reading one ingredient line
_NUM = r'(?:\d+\s+\d+/\d+|\d+\s*[½¼¾⅓⅔]|[½¼¾⅓⅔]|\d+/\d+|\d+(?:\.\d+)?)'
_RANGE = rf'{_NUM}(?:\s*(?:-|–|to)\s*{_NUM})?'
_UNIT = '|'.join(sorted({*nutrition.UNITS, *nutrition.SIZES, 'sprig', 'sprigs', 'tin', 'can', 'cubes', 'stick', 'sticks', 'pods', 'strands', 'nos', 'no'}, key=len, reverse=True))
_WORDS = r'(?:a|one)?\s*(?:big |small )?(?:pinch|handful|bunch|few|little|sprig|dash|splash)'
_LATER = r'to taste|as needed|as required|as per taste|for (?:deep )?frying|for garnish(?:ing)?|for tempering'
QTY_FIRST = re.compile(rf'^(?P<qty>{_RANGE}(?:\s*(?:{_UNIT})\b\.?)?(?:\s+(?:{_UNIT})\b)?)\s*(?:of\s+)?(?P<name>[^\d\s].*)$', re.I)
WORDS_FIRST = re.compile(rf'^(?P<qty>{_WORDS})\s+(?:of\s+)?(?P<name>.+)$', re.I)
NAME_FIRST = re.compile(r'^(?P<name>[^\d:]+?)\s*(?::|\s[-–—]|[-–—](?=\s*[\d½¼¾⅓⅔]))\s*(?P<qty>.+)$')
QTY_LAST = re.compile(rf'^(?P<name>\D+?)[\s,]+(?P<qty>(?:{_RANGE}|{_WORDS}|{_LATER}).*)$', re.I)
BULLET = re.compile(r'^\s*(?:[-*•▪◦‣▢☐✓✔·●–—]+|\(?\d{1,2}[.)](?!\d)|step\s*\d+\s*[:.)-]?)\s*', re.I)
OPTIONAL = re.compile(r'[(,\s]*\b(?:optional|if you like|if available)\b\)?', re.I)
# "Chicken masala powder" isn't chicken: with one of these words left over, ask instead of guessing.
OTHER_THING = {'powder', 'masala', 'flour', 'sauce', 'stock', 'broth', 'essence', 'syrup', 'pickle', 'chutney', 'jam', 'extract', 'seeds', 'seed', 'mix', 'cube', 'chips', 'oil'}
PREP_WORDS = set('''tsp tbsp teaspoon teaspoons tablespoon tablespoons large small medium big whole finely roughly thinly chopped sliced diced grated crushed
minced ground roasted boiled cooked soaked washed rinsed cleaned peeled cubed mashed beaten melted warm hot cold fresh dry dried raw ripe tender thick thin slit
cut cubes pieces paste puree pureed juice leaves leaf sprigs sprig pods pod strands clove cloves inch inches stick sticks or to taste as needed required for frying
garnish garnishing tempering per your choice any deseeded deveined boneless skinless full fat split sour sweet green red white yellow black brown big'''.split())


def resolve(text):
    """(ingredient ids found, leftover words worth a look) in an ingredient's name."""
    got = engine.parse_ingredients(text)
    left = {w for chunk in got['unknown'] for w in chunk.split()} - PREP_WORDS
    spice = all(engine.BY_ID.get(i, {}).get('category') == 'Spices' for i in got['found'])
    if left & OTHER_THING and not (spice and left <= {'powder', 'seeds', 'seed'}):
        return [], left
    return got['found'], left - {'powder', 'seeds', 'seed'}


def read_ingredient(line):
    """'2 cups toor dal, washed' -> [{'options': ['toor_dal'], 'qty': '2 cups, washed', 'optional': False, 'from': ''}].
    `from` is the original words, when they need a second look. What isn't in the ingredient list keeps its words."""
    line = BULLET.sub('', str(line)).strip(' .;,')
    if not line:
        return []
    optional = bool(OPTIONAL.search(line))
    text = OPTIONAL.sub('', line).strip(' ,;.-')
    m = QTY_FIRST.match(text) or WORDS_FIRST.match(text) or NAME_FIRST.match(text) or QTY_LAST.match(text)
    name, qty = (m.group('name'), m.group('qty')) if m else (text, '')
    inside = re.findall(r'\(([^)]*)\)', name)
    name = re.sub(r'\([^)]*\)', ' ', name)
    name, _, detail = name.partition(',')
    details = [detail.strip(), *(x.strip() for x in inside if not engine.parse_ingredients(x)['found'])]
    qty = ', '.join(x for x in [qty.strip(' ,.-:'), *details] if x)[:60]
    name = re.sub(r'\s+', ' ', name).strip(' ,.-:')
    parts = [p for p in re.split(r'\s+or\s+|\s*/\s*', name) if p.strip()]
    row = {'qty': qty, 'optional': optional, 'from': ''}
    if len(parts) > 1:  # "ghee or oil": any one of these
        options, look = [], False
        for p in parts:
            ids, left = resolve(p)
            options.append(ids[0] if ids else tidy(p))
            look = look or bool(left) or len(ids) > 1
        return [{**row, 'options': list(dict.fromkeys(options)), 'from': line if look else ''}]
    ids, left = resolve(name)
    if not ids:
        return [{**row, 'options': [tidy(name)]}] if tidy(name) else []
    # "Ginger garlic paste" and "salt and pepper" are two ingredients.
    return [{**row, 'options': [i], 'from': line if left or (len(ids) > 1 and not re.search(r'\band\b|&|paste', name, re.I)) else ''} for i in ids]


def tidy(text):
    """The words of an ingredient we don't know, safe to keep in a recipe line."""
    return re.sub(r'\s+', ' ', re.sub(r'[|?:\n\r]', ' ', str(text))).strip(' ,.-').lower()[:40]


def drop_basics(rows):
    """Salt and water are always in the kitchen, so recipes don't list them."""
    return [r for r in rows if not set(r['options']) <= {'salt', 'water'}]


# ---------------------------------------------------------------- reading steps
_WHISTLES = re.compile(r'(\d+)(?:\s*(?:-|–|to)\s*(\d+))?\s*whistles?', re.I)
_MINUTES = re.compile(r'(\d+)(?:\s*(?:-|–|to)\s*(\d+))?\s*(minutes?|mins?|hours?|hrs?)\b', re.I)


def read_step(text):
    """{'text', 'minutes' or 'whistles'}: 'Pressure cook for 3 whistles' gets a whistle counter by itself."""
    text = re.sub(r'\s+', ' ', BULLET.sub('', str(text))).strip()
    step = engine.parse_step(text)
    if 'minutes' in step or 'whistles' in step:
        return step
    if m := _WHISTLES.search(text):
        return {'text': text, 'whistles': int(m.group(2) or m.group(1))}
    if m := _MINUTES.search(text):
        n = int(m.group(2) or m.group(1)) * (60 if m.group(3).lower().startswith('h') else 1)
        if 0 < n <= 240:
            return {'text': text, 'minutes': n}
    return {'text': text}


def sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z"“])', text) if s.strip()]


# ---------------------------------------------------------------- reading a whole recipe
HEAD = {
    'ing': re.compile(r"^(?:the )?(?:main )?(?:ingredients?|what you(?:'ll| will)? need|you(?:'ll| will) need|samagri|saamagri|kavalsinavi|kaavalsinavi|सामग्री|కావలసినవి|కావలసిన పదార్థాలు|தேவையான பொருட்கள்)\b", re.I),
    'step': re.compile(r'^(?:method|steps?|directions?|instructions?|preparation|procedure|process|how to (?:make|cook|prepare)|vidhi|banane ki vidhi|tayari vidhanam|विधि|తయారీ విధానం|செய்முறை)\b(?!\s*time)', re.I),
    'tip': re.compile(r"^(?:tips?|notes?|chef'?s? (?:tips?|notes?)|serving suggestions?)\b", re.I),
}
_TIME = r'(?:(\d+)\s*(?:hours?|hrs?|h)\b)?\s*(?:(\d+)\s*(?:minutes?|mins?|m)\b)?'
META = [
    ('serves', re.compile(r'^(?:serves|servings?|yield|for)\s*[:\-–]?\s*(\d+)', re.I)),
    ('total', re.compile(rf'^(?:total time|time|ready in|takes)\s*[:\-–]?\s*{_TIME}', re.I)),
    ('part', re.compile(rf'^(?:prep(?:aration)?|cook(?:ing)?)(?: time)\s*[:\-–]?\s*{_TIME}', re.I)),
    ('cuisine', re.compile(r'^cuisine\s*[:\-–]\s*(.+)', re.I)),
    ('meal', re.compile(r'^(?:course|meal|category)\s*[:\-–]\s*(.+)', re.I)),
]


def looks_like_ingredient(line):
    text = BULLET.sub('', line)
    words = text.split()
    if len(words) > 10 or (len(words) > 5 and text.endswith('.')):
        return False
    return bool(QTY_FIRST.match(text) or WORDS_FIRST.match(text) or (QTY_LAST.match(text) and len(words) <= 7)
                or (len(words) <= 4 and engine.parse_ingredients(text)['found']))


def read_text(text):
    """A recipe pasted from anywhere -> the editor's fields. Headings like "Ingredients" and "Method" help, but aren't needed."""
    out = {'name': '', 'cuisine': '', 'meal': [], 'time': None, 'serves': None, 'tip': '', 'prep': ''}
    ings, steps, tips, section, parts = [], [], [], None, 0
    text = re.sub(r'(?i)(?<=\S)[ \t]*\b(ingredients|method|directions|instructions|preparation|procedure)\s*:', r'\n\1:', str(text)[:12000])
    for raw in text.replace('\r', '\n').split('\n'):
        line = re.sub(r'[*_#`~]+', ' ', raw)
        line = re.sub(r'\s+', ' ', line).strip()
        if not line:
            continue
        bare = BULLET.sub('', line).strip()
        head = next((k for k, rx in HEAD.items() if (m := rx.match(bare)) and len(bare[:m.end()].split()) <= 5
                     and (len(bare.split()) <= 6 or ':' in bare[m.end():m.end() + 12])), None)
        if head:
            section = head
            line = bare = bare.partition(':')[2].strip()
            if not line:
                continue
        elif section != 'step':
            hit = False
            for piece in re.split(r'\s*[|;•]\s*|,\s*(?=(?:serves|prep|cook|total|time|cuisine|course))', bare, flags=re.I):
                for key, rx in META:
                    if not (m := rx.match(piece)):
                        continue
                    if key == 'serves':
                        out['serves'] = max(1, min(30, int(m.group(1))))
                    elif key in ('total', 'part'):
                        mins = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
                        if not mins:
                            continue
                        if key == 'total':
                            out['time'] = mins
                        else:
                            parts += mins
                    elif key == 'cuisine':
                        out['cuisine'] = m.group(1).strip()[:40]
                    else:
                        out['meal'] = [k for k, _ in MEALS if k in m.group(1).lower()]
                    hit = True
                    break
            if hit:
                continue
        if not out['name'] and section is None and not QTY_FIRST.match(bare):
            out['name'] = re.sub(r'\s*\brecipe\b\s*$', '', re.sub(r'^[\W_]+|[^\w)]+$', '', bare), flags=re.I).strip(' :-')[:80]
            continue
        kind = section or ('ing' if looks_like_ingredient(line) else 'step')
        if kind == 'tip':
            tips.append(bare)
        elif kind == 'ing':
            if line.endswith(':') and not re.search(r'\d', line):
                continue  # "For the tempering:"
            many = [p for p in re.split(r',\s*(?=[^)]*(?:\(|$))', line) if p.strip()]
            if len(many) >= 3 and sum(1 for p in many if looks_like_ingredient(p.strip())) >= len(many) - 1:
                ings.extend(many)  # "rice 1 cup, dal 1/2 cup, salt"
            else:
                ings.append(line)
        elif len(bare.split()) > 1:
            steps.append(bare)
    if len(steps) <= 2 and any(len(sentences(s)) >= 3 for s in steps):  # one paragraph
        steps = [x for s in steps for x in sentences(s)]
    out['time'] = out['time'] or (parts or None)
    out['ingredients'] = drop_basics([r for line in ings for r in read_ingredient(line)])[:40]
    out['steps'] = [read_step(s) for s in steps][:25]
    out['tip'] = ' '.join(tips)[:400]
    out['prep'] = find_prep([s['text'] for s in out['steps']] + ings)
    return out


def find_prep(texts):
    """A night-before reminder, when something soaks for hours or overnight."""
    for t in texts:
        if re.search(r'\bsoak|ferment|marinat', t, re.I) and re.search(r'overnight|\d\s*(?:-\s*\d+\s*)?(?:hours?|hrs?)', t, re.I):
            return next((s for s in sentences(t) if re.search(r'soak|ferment|marinat', s, re.I)), t)[:200]
    return ''


WAITING = re.compile(r'\b(?:simmer|cook|boil|fry|saut[eé]|roast|bake|steam|rest|soak|marinate|ferment|stand|brown)\b', re.I)


def from_ai(raw):
    """The AI's recipe (already JSON) -> the editor's fields. Raises ValueError when it isn't a usable recipe."""
    r = engine.normalize_ai_recipe(raw)
    rows = []
    for it in r['ingredients']:
        label = it.get('custom')
        known = it['options'][0] in engine.BY_ID
        if known and label and resolve(label)[0][:1] != it['options']:
            known = False  # "chicken masala" isn't chicken
        rows.append({'options': it['options'] if known else [tidy(label or it['options'][0])], 'qty': it['qty'][:60], 'optional': it['optional'],
                     'from': label if label and known else ''})
    steps = []
    for s in r['steps']:
        step = read_step(s['text'])
        # The AI gives every step minutes, even "wash the dal". A timer is for steps that need watching.
        if s.get('minutes') and 'minutes' not in step and 'whistles' not in step and WAITING.search(step['text']):
            step['minutes'] = s['minutes']
        steps.append(step)
    return {'name': r['name'], 'alt': (r.get('alt') or '')[:60], 'cuisine': '' if r['cuisine'] == 'Ballava original' else r['cuisine'], 'meal': r['meal'],
            'time': r['time'], 'serves': r['serves'], 'spice': r['spice'], 'tip': r.get('tip') or '', 'safety': r.get('safety') or '',
            'prep': find_prep([s['text'] for s in steps]), 'ingredients': drop_basics(rows), 'steps': steps}


def fields_of(raw):
    """A recipe in the book's compact format -> the editor's fields (to copy or edit it)."""
    return {**{k: raw.get(k) or '' for k in ('name', 'alt', 'cuisine', 'prep', 'safety', 'tip')}, 'meal': raw.get('meal') or [], 'tags': raw.get('tags') or [],
            'time': raw.get('time'), 'serves': raw.get('serves'), 'spice': raw.get('spice'), 'recipe_id': raw.get('id', ''),
            'ingredients': [engine.parse_ingredient_line(x) for x in raw.get('ing') or []], 'steps': [engine.parse_step(s) for s in raw.get('steps') or []]}


# ---------------------------------------------------------------- checking
PROBLEM_FIELD = [
    ('Id must', 'recipe_id', 'The id (under Advanced) may only have lowercase letters, numbers and _.'), ('Name is required', 'name', 'Give the dish a name.'), ('Time must', 'time', 'Say how many minutes it takes.'),
    ('Serves must', 'serves', 'Say how many people it serves.'), ('Choose at least one meal', 'meal', 'Choose at least one meal.'),
    ('Add at least one ingredient', 'ingredients', 'Add the ingredients.'), ('Add at least two steps', 'steps', 'Add at least two steps.'),
    ('At least one ingredient must be required', 'ingredients', 'At least one ingredient must not be optional.'),
    ('One of the steps is too short', 'steps', 'One of the steps is too short to follow.'),
    ('Tagged jain', 'tags', 'It is tagged Jain, but it needs onion, garlic or root vegetables.'),
    ('Tagged vrat', 'tags', 'It is tagged for fasting, but it needs onion or garlic.'),
    ('Tagged gluten-free', 'tags', 'It is tagged gluten-free, but it contains gluten.'),
    ('A sweet dish', 'tags', 'A sweet dish cannot be tagged diabetic-friendly.'),
    ('Meat and fish', 'safety', 'Meat and fish dishes need a food-safety note.'),
]


def friendly(problem):
    for start, field, text in PROBLEM_FIELD:
        if problem.startswith(start):
            return {'field': field, 'text': text}
    return {'field': '', 'text': problem}


def problems_of(raw):
    """Everything that must be fixed before publishing, in plain words: [{'field', 'text'}]."""
    unknown = list(dict.fromkeys(i for line in raw['ing'] for i in engine.parse_ingredient_line(line)['options'] if i not in engine.BY_ID))
    found = [{'field': 'ingredients', 'text': f'"{i}" is not in the ingredient list yet. Choose one that is, or add it.', 'unknown': i} for i in unknown]
    return [friendly(p) for p in engine.validate_recipe(raw) if not p.startswith('Unknown ingredient')] + found


def safety_note(r):
    ids = [i for it in r['ingredients'] if not it['optional'] for i in it['options']]
    return next((SAFETY[i] for i in ids if i in SAFETY), MEAT_NOTE if r['diet'] == 'nonveg' else '')


def suggested_tags(r):
    n = r.get('nutrition') or {}
    fits = {'gluten-free': 'gluten' not in r['allergens'], 'quick': 0 < r['time'] <= 20, 'high-protein': (n.get('protein') or 0) >= engine.PROTEIN_G,
            'vrat': engine.vrat_ok(r)}
    return [t for t, ok in fits.items() if ok and t not in r['tags']]


def check(raw, own_id=''):
    """What the side panel of the editor shows, as the admin types."""
    out = {'problems': problems_of(raw), 'advice': [], 'lines': [], 'nutrition': None, 'suggested': [], 'safety': ''}
    name = raw['name'].strip().lower()
    for r in engine.recipes_from([engine.prepare_recipe(x.live) for x in Recipe.objects.exclude(live=None)], ()):
        if name and r['name'].lower() == name and r['id'] != own_id:
            out['advice'].append({'text': f"Users already have a dish called {r['name']}. You could edit that one instead.", 'edit': r['id']})
    if not raw['ing']:
        return out
    r = engine.prepare_recipe(raw)
    n = r['nutrition']
    known = all(i in engine.BY_ID for it in r['ingredients'] for i in it['options'])
    for it, got in zip(r['ingredients'], n['lines']):
        info = nutrition.line(it['options'][0], it['qty']) if it['options'] else None
        flavour = engine.is_spice(it['options'][0]) if it['options'] else False
        unclear = bool(info and info['guessed'] and not flavour and not it['optional'])
        out['lines'].append({**(got or {}), 'unclear': unclear} if got else None)
        if unclear:
            what = engine.name_of(it['options'][0])
            out['advice'].append({'text': f'How much {what.lower()}? ' + ('That amount was not understood' if it['qty'] else 'There is no amount') + ', so the calories may be off.', 'field': 'ingredients'})
    out.update(
        nutrition={k: n[k] for k in ('kcal', 'protein', 'carbs', 'fat', 'fibre', 'totalKcal', 'serves', 'oilTsp')},
        uncounted=[engine.name_of(i) if i in engine.BY_ID else i for i in n['unknown']], diet=r['diet'], allergens=r['allergens'], jainOk=r['jainOk'],
        needsOnionGarlic=r['needsOnionGarlic'], suggested=suggested_tags(r) if known else [], safety='' if raw.get('safety') else safety_note(r))
    return out


# ---------------------------------------------------------------- a new ingredient, without leaving the recipe
def guess_ingredient(name):
    """A first guess from the words alone. The admin checks it."""
    low = str(name).lower()
    diet = engine._diet_from_words(low) or 'veg'
    category = ('Meat & Fish' if diet == 'nonveg' else 'Dairy & Eggs' if diet == 'egg' or re.search(r'cheese|milk|cream|butter|yog', low)
                else 'Spices' if re.search(r'masala|powder|spice|seeds?\b|saffron|clove|cinnamon', low)
                else 'Grains & Flours' if re.search(r'flour|rice|atta|rava|millet|noodle|pasta|oats|vermicelli', low)
                else 'Dals & Beans' if re.search(r'\bdal\b|pappu|beans?\b|gram\b|lentil|nuts?\b|almond|walnut', low)
                else 'Basics & Sauces' if re.search(r'sauce|oil|vinegar|syrup|paste|essence|sugar', low)
                else 'Fruits' if re.search(r'fruit|berry|grape|orange|pineapple|guava|pomegranate|dates?\b|raisin', low) else 'Vegetables')
    return {'name': str(name).strip()[:60].capitalize(), 'category': category if category in CATEGORIES else CATEGORIES[0], 'diet': diet,
            'allergens': engine._allergens_from_words(low), 'aliases': ''}


def clean_ingredient(data):
    """Checked fields for a new Ingredient, from the form in the editor or from the AI. Raises ValueError."""
    name = re.sub(r'\s+', ' ', str(data.get('name') or '')).strip()[:60]
    if not re.search(r'[^\W\d_]', name):
        raise ValueError('Please give the ingredient a name.')

    def number(key, top):
        try:
            v = float(data.get(key))
        except (TypeError, ValueError):
            return None
        return round(v, 1) if 0 <= v <= top else None
    aliases = data.get('aliases') or ''
    if isinstance(aliases, list):
        aliases = ', '.join(map(str, aliases))
    allergens = data.get('allergens') if isinstance(data.get('allergens'), list) else []
    shelf = number('shelf_days', 1000)
    return {'name': name, 'category': data.get('category') if data.get('category') in CATEGORIES else 'Vegetables',
            'diet': data.get('diet') if data.get('diet') in ('veg', 'egg', 'nonveg') else 'veg',
            'allergens': ', '.join(a for a in engine.ALLERGENS if a in allergens), 'aliases': re.sub(r'\s+', ' ', aliases)[:300],
            'shelf_days': int(shelf) if shelf else None, 'kcal': number('kcal', 900), 'protein': number('protein', 100), 'carbs': number('carbs', 100),
            'fat': number('fat', 100), 'fibre': number('fibre', 100), 'grams_per_cup': number('grams_per_cup', 1000) or None,
            'grams_per_piece': number('grams_per_piece', 5000) or None}


def new_ingredient(data):
    """Adds it, or returns the one that already has that name."""
    fields = clean_ingredient(data)
    same = engine.parse_ingredients(fields['name'])
    if len(same['found']) == 1 and not same['unknown']:
        return None, same['found'][0]
    base = re.sub(r'[^a-z0-9]+', '_', fields['name'].lower()).strip('_')[:34] or 'ingredient'
    taken = set(engine.BY_ID) | set(Ingredient.objects.values_list('ingredient_id', flat=True))
    id_ = next(i for i in [base, *(f'{base}_{n}' for n in range(2, 1000))] if i not in taken)
    return Ingredient.objects.create(ingredient_id=id_, **fields), id_


def ingredient_list():
    """For the search box: every ingredient with its other names (tamatar, pyaz, kandi pappu...)."""
    return [{'id': i['id'], 'name': i['name'], 'aliases': i.get('aliases') or [], 'category': i['category'], 'diet': i.get('diet', 'veg')}
            for i in engine.INGREDIENTS if i['id'] not in ('salt', 'water')]
