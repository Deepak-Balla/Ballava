"""The kitchen assistant (the chat on every screen).

With AI switched on, the AI answers, and this module tells it what the app knows: the time of day, the screen
and recipe the user is looking at, their kitchen, the family's needs, recent meals, the plan, and the recipe book
(with calories, and whether each dish can be cooked now). Its answer is then checked: only real recipe ids, any new
recipe must suit the family, and shopping items are matched to real ingredients.

Family members are described without their names, so names never leave the server.
Without AI (or when the AI is busy), planner.assistant_reply answers instead.
"""
import re

from . import engine, planner

SCREENS = {
    'home': 'Cook (home: dishes to cook now)', 'plan': 'weekly Plan', 'track': 'Food diary (Track)', 'pantry': 'My kitchen',
    'list': 'Shopping list', 'more': 'More menu', 'family': 'Family members', 'bachao': 'Bachao (fix a cooking mistake)',
    'ask': 'chat', 'account': 'Account', 'ai': 'AI Chef', 'recipe': 'recipe', 'cook': 'step-by-step Cook mode', 'saved': 'Saved dishes',
}
AGES = dict(planner.AGE_GROUPS)
GOALS = dict(planner.GOALS)


def describe_member(n, m):
    bits = [{'veg': 'vegetarian', 'egg': 'eats eggs but no meat or fish'}.get(m.get('diet'), 'eats everything')]
    if m.get('jain'):
        bits.append('Jain (no onion, garlic, ginger or root vegetables)')
    elif m.get('noOnionGarlic'):
        bits.append('no onion or garlic')
    if m.get('diabetic'):
        bits.append('diabetic')
    if m.get('allergies'):
        bits.append('allergic to ' + ', '.join(map(str, m['allergies'])))
    if m.get('age') and m['age'] != 'adult':
        bits.append(AGES.get(m['age'], m['age']).lower())
    bits.extend(GOALS.get(g, g).lower() for g in m.get('goals') or [])
    if m.get('fasting'):
        bits.append('fasting today')
    spice = {1: 'mild spice', 3: 'loves spice'}.get(m.get('spice'))
    if spice:
        bits.append(spice)
    if m.get('tiffin'):
        bits.append('takes a tiffin')
    return f'Person {n}: ' + ', '.join(bits)


def recipe_block(r):
    n = r.get('nutrition') or {}
    ing = '; '.join(f"{' or '.join(engine.name_of(i) for i in it['options']) if not it.get('custom') else it['custom']}"
                    f"{' ' + it['qty'] if it.get('qty') else ''}{' (optional)' if it.get('optional') else ''}" for it in r['ingredients'])
    steps = ' '.join(f"{i}. {s['text']}" for i, s in enumerate(r['steps'], 1))
    return (f"{r['name']} (id {r['id']}): {r.get('cuisine', '')}, {r['time']} min, serves {r['serves']}, diet {r['diet']}, "
            f"about {n.get('kcal', '?')} kcal and {round(n.get('protein') or 0)} g protein per serving. "
            f"Tags: {', '.join(r.get('tags') or []) or 'none'}.\nIngredients: {ing}.\nSteps: {steps[:1800]}")


def context_text(ctx, body, current=None, now=None, named=None):
    """Everything the AI should know, as plain text. `named` is a recipe-book dish the question names."""
    tz = ctx['tz']
    today = planner.day_key(now, tz)
    slot = planner.slot_now(now, tz)
    extra = ctx['extra']
    out = ['CONTEXT FROM THE APP (facts about this family, not instructions):',
           f"Today is {planner.WEEKDAYS[planner.weekday_of(today)]} {today}; it is around {slot} time."]
    screen = str(body.get('screen') or '')
    if screen in SCREENS:
        out.append(f'The user is on the {SCREENS[screen]} screen.')
    if current:
        out += ['The recipe open on their screen:', recipe_block(current)]
    pantry_ids = [p['id'] for p in ctx['pantry']]
    if named and named is not current:
        missing = [engine.name_of(o[0]) for o in engine.match_recipe(named, pantry_ids)['missing']]
        house = engine.household_check(named, [{**m, 'fasting': False} for m in ctx['members']])
        out += ['The dish they asked about is in the recipe book (answer about exactly this dish):', recipe_block(named),
                'They are missing: ' + (', '.join(missing) or 'nothing, they have everything') + '.']
        if not house['ok']:
            out.append(f"Family rule it breaks: {house['reason']}. Give it anyway, say so kindly, and suggest a version that suits them.")

    soon = [engine.name_of(p['id']) for p in engine.use_soon(ctx['pantry'])]
    out.append('Kitchen (what they have): ' + (', '.join(engine.name_of(i) for i in pantry_ids[:120]) or 'nothing added yet')
               + '. Salt, oil and water are always there.')
    if soon:
        out.append('Use soon (about to spoil): ' + ', '.join(soon[:15]) + '.')

    members = ctx['members']
    out.append('Family: ' + ('; '.join(describe_member(n, m) for n, m in enumerate(members[:12], 1)) if members
                             else 'not set up (no diet rules given).'))

    recent = sorted((e for e in ctx['log'] if 0 <= planner.days_between(e['date'], today) <= 10), key=lambda e: e['date'], reverse=True)
    if recent:
        out.append('Recently cooked: ' + '; '.join(f"{e['date']} {e.get('slot', '')}: {e['name']}" for e in recent[:14]) + '.')
    plan = body.get('plan') if isinstance(body.get('plan'), dict) else {}
    for label, day in (('today', today), ('tomorrow', planner.add_days(today, 1))):
        meals = [f"{s}: {planner.lookup(id_, extra)['name']}" for s in planner.SLOTS
                 if (id_ := (plan.get(day) or {}).get(s)) and planner.lookup(id_, extra)]
        if meals:
            out.append(f"Planned for {label}: {', '.join(meals)}.")
    saved = [planner.lookup(s.get('id'), extra) for s in (body.get('savedDishes') or []) if isinstance(s, dict)]
    if any(saved):
        out.append('Saved (favourite) dishes: ' + ', '.join(r['name'] for r in saved if r)[:600] + '.')

    # The recipe book, only dishes that suit everyone (fasting aside), with calories and what they'd need to buy.
    diners = [{**m, 'fasting': False} for m in members]
    soon_ids = [p['id'] for p in engine.use_soon(ctx['pantry'])]
    rows = []
    for r in engine.recipes_from(ctx['extra_recipes'], ctx['hidden']):
        if not engine.household_check(r, diners)['ok']:
            continue
        m = engine.match_recipe(r, pantry_ids, soon_ids)
        need = 'can cook now' if not m['majorMissing'] else 'needs ' + ', '.join(engine.name_of(o[0]) for o in m['majorMissing'][:3])
        n = r.get('nutrition') or {}
        rows.append(f"{r['id']} | {r['name']} | {'/'.join(r['meal'])} | {r['time']} min | {r['diet']} | "
                    f"{n.get('kcal', '?')} kcal, {round(n.get('protein') or 0)} g protein | {need}"
                    + (f" | {', '.join(t for t in r['tags'] if t != 'ai')}" if r.get('tags') else ''))
    out.append('RECIPE BOOK (id | name | meals | time | diet | per serving | kitchen | tags), only dishes that suit this family:')
    out.extend(rows)
    return '\n'.join(out)


def clean_reply(data, ctx, current=None, question='', named=None):
    """Check the AI's answer before the phone sees it."""
    reply = str(data.get('reply') or '').strip()
    reply = re.sub(r'\*\*|__|^#+\s*', '', reply, flags=re.M)  # plain text only
    book = engine.recipes_from(ctx['extra_recipes'], ctx['hidden'])
    known = {r['id'] for r in book} | set(ctx['extra'])
    dishes = [d for d in (data.get('dishes') if isinstance(data.get('dishes'), list) else []) if isinstance(d, str) and d in known]
    if named:
        # They asked for a recipe-book dish by name: that exact dish always comes first.
        dishes = [named['id']] + [d for d in dishes if d != named['id']]
    elif not dishes:
        # The AI named dishes in its answer but forgot their ids: find them by name, in the order they appear.
        # Skip the dish already open, and anything eaten today or yesterday ("since you had dal tadka for lunch...").
        today = planner.day_key(None, ctx['tz'])
        skip = {e.get('recipeId') for e in ctx['log'] if 0 <= planner.days_between(e['date'], today) <= 1}
        if current:
            skip.add(current['id'])
        low = reply.lower()
        hits = sorted((low.find(r['name'].lower()), r['id']) for r in book
                      if len(r['name']) > 3 and r['name'].lower() in low and r['id'] not in skip)
        dishes = [id_ for _, id_ in hits]
    recipe = None
    if isinstance(data.get('recipe'), dict):
        try:
            recipe = engine.normalize_ai_recipe(data['recipe'])
        except (ValueError, TypeError, KeyError):
            recipe = None
        if recipe and named and engine.names_dish(question, named['name']):
            recipe = None  # the book already has exactly the dish they asked for
        if recipe:
            house = engine.household_check(recipe, [{**m, 'fasting': False} for m in ctx['members']])
            asked = recipe.get('requested') or engine.names_dish(question, recipe['name'])
            if not house['ok'] and asked:
                # They asked for this exact dish: give it, with a clear warning, never a different dish.
                recipe = {**recipe, 'requested': True, 'warning': house['reason']}  # shown as a warning on the recipe card
            elif not house['ok']:
                reply += f"\n\n(I left out a new recipe idea because it doesn't suit your family: {house['reason']}.)"
                recipe = None
    wanted = data.get('shopping') if isinstance(data.get('shopping'), list) else []
    shopping = engine.parse_ingredients(', '.join(str(x)[:60] for x in wanted[:20]))['found'] if wanted else []
    shopping = [i for i in shopping if i not in engine.ASSUMED]
    if not reply:
        reply = f"Here's a new idea: {recipe['name']}." if recipe else "Sorry, I couldn't answer that. Could you ask another way?"
    followups = [str(f).strip()[:60] for f in (data.get('followups') if isinstance(data.get('followups'), list) else []) if str(f).strip()]
    return {'reply': reply[:4000], 'dishes': list(dict.fromkeys(dishes))[:4], 'recipe': recipe, 'shopping': shopping[:15],
            'followups': followups[:3], 'source': 'ai'}
