"""Tests for the planner (kitchen/planner.py): no repeats, family diets, weekly plans, dashboard."""
from datetime import datetime, timedelta, timezone

from kitchen.engine import ALL_RECIPES, RECIPE_BY_ID, household_check
from kitchen.planner import (SLOTS, TIFFIN_IDS, add_days, assistant_reply, base_of, dashboard, day_key, day_recipe_ids, days_between,
                             fasters_on, goal_score, groups_of, leftover_chains, mains_of, menu_message, normalize_log, plan_groceries,
                             plan_week, plates_for, prep_for, prep_tonight, recommend, repeat_check, slot_now)

R = RECIPE_BY_ID
MONDAY = '2026-11-09'
IST = timezone(timedelta(hours=5, minutes=30))
NOW = int(datetime(2026, 11, 9, 12, 0, tzinfo=IST).timestamp() * 1000)
KITCHEN = [{'id': i} for i in ['rice', 'toor_dal', 'moong_dal', 'onion', 'tomato', 'potato', 'atta', 'curd', 'egg', 'turmeric', 'cumin',
                               'mustard_seeds', 'red_chilli_powder', 'coriander_powder', 'poha', 'peas', 'spinach', 'green_chilli', 'ginger', 'garlic', 'lemon']]


def logged(rid, days_ago, **extra):
    return {'recipeId': rid, 'name': R[rid]['name'] if rid in R else rid, 'date': add_days(MONDAY, -days_ago), 'slot': 'dinner', **extra}


def test_enough_recipes_for_a_varied_week():
    for slot in SLOTS:
        assert len([r for r in ALL_RECIPES if slot in r['meal']]) >= 25, slot
    assert len([r for r in ALL_RECIPES if 'vrat' in r['tags']]) >= 5
    for rid in TIFFIN_IDS:
        assert rid in R


def test_dates_work_across_months_and_time_zones():
    assert add_days('2026-11-30', 1) == '2026-12-01'
    assert days_between('2026-11-30', '2026-12-02') == 2
    assert day_key(NOW) == MONDAY
    # 11:30 pm in India on Monday is still Monday for the family, even though it is Monday 6 pm in London.
    late = int(datetime(2026, 11, 9, 23, 30, tzinfo=IST).timestamp() * 1000)
    assert day_key(late, tz=-330) == MONDAY
    assert day_key(late, tz=0) == MONDAY
    early = int(datetime(2026, 11, 10, 1, 0, tzinfo=IST).timestamp() * 1000)
    assert day_key(early, tz=-330) == '2026-11-10'
    assert day_key(early, tz=0) == MONDAY  # the same moment, but a UTC server would call it Monday
    assert slot_now(int(datetime(2026, 11, 9, 8, 0, tzinfo=IST).timestamp() * 1000)) == 'breakfast'


def test_knows_what_a_dish_is_about():
    assert 'potato' in mains_of(R['aloo_gobi']) and 'onion' not in mains_of(R['aloo_gobi'])
    assert base_of(R['lemon_rice']) == 'rice'
    assert base_of(R['aloo_paratha']) == 'wheat'
    assert 'greens' in groups_of(R['palak_paneer'])
    assert 'protein' in groups_of(R['dal_tadka'])
    assert 'protein' not in groups_of(R['jeera_rice'])


def test_same_dish_pushed_down_more_when_recent():
    p = lambda d: repeat_check(R['dal_tadka'], [logged('dal_tadka', d)], MONDAY)['penalty']  # noqa: E731
    assert p(1) > p(5) > p(10) > 0
    assert p(20) == 0
    assert '1 day ago' in repeat_check(R['dal_tadka'], [logged('dal_tadka', 1)], MONDAY)['reasons'][0]


def test_same_main_ingredient_counts_as_a_repeat():
    log = [logged('aloo_gobi', 1)]
    r = repeat_check(R['jeera_aloo'], log, MONDAY)
    assert r['penalty'] > 0 and 'potato' in r['reasons'][0].lower()
    assert repeat_check(R['fish_curry'], log, MONDAY)['penalty'] == 0


def test_rice_at_every_meal_is_noticed():
    log = [{'recipeId': 'lemon_rice', 'date': MONDAY, 'slot': 'lunch'}]
    assert repeat_check(R['veg_pulao'], log, MONDAY)['penalty'] >= 10


def test_recommendations_avoid_what_was_just_eaten():
    first = recommend(pantry=KITCHEN, slot='dinner', date=MONDAY, now=NOW)[0]['recipe']['id']
    nxt = recommend(pantry=KITCHEN, slot='dinner', date=MONDAY, now=NOW, log=[{'recipeId': first, 'date': add_days(MONDAY, -1), 'slot': 'dinner'}])
    assert nxt[0]['recipe']['id'] != first


def test_pinned_tradition_is_not_a_repeat_and_comes_first():
    pins = [{'recipeId': 'rajma_masala', 'weekday': 0, 'slot': 'lunch'}]
    sunday = add_days(MONDAY, 6)
    log = [{'recipeId': 'rajma_masala', 'date': add_days(sunday, -7), 'slot': 'lunch'}]
    assert repeat_check(R['rajma_masala'], log, sunday, pins)['penalty'] == 0
    top = recommend(pantry=KITCHEN, slot='lunch', date=sunday, now=NOW, pins=pins, log=log)[0]
    assert top['recipe']['id'] == 'rajma_masala' and 'Sun favourite' in top['why'][0]


def test_family_goals_change_the_ranking():
    assert goal_score(R['dal_palak'], [{'name': 'Amma', 'diabetic': True}])['bonus'] > goal_score(R['jeera_rice'], [{'name': 'Amma', 'diabetic': True}])['bonus']
    assert goal_score(R['hakka_noodles'], [{'name': 'Dad', 'goals': ['bp']}])['bonus'] < 0
    kid = goal_score(R['veg_sandwich'], [{'name': 'Riya', 'age': 'child'}])
    assert kid['bonus'] > 0 and 'Riya' in kid['why'][0]
    hates = goal_score(R['karela_fry'], [{'name': 'Ravi', 'dislikes': ['bitter_gourd']}])['bonus']
    loves = goal_score(R['karela_fry'], [{'name': 'Ravi', 'likes': ['bitter_gourd']}])['bonus']
    assert hates < loves


def test_family_safety_rules_always_win():
    veg = [{'name': 'Amma', 'diet': 'veg'}]
    rows = recommend(pantry=[{'id': i} for i in ['chicken', 'onion', 'tomato']], members=veg, slot='dinner', date=MONDAY, now=NOW)
    assert rows and all(r['recipe']['diet'] == 'veg' for r in rows)
    nuts = [{'name': 'Riya', 'allergies': ['nuts']}]
    assert all('nuts' not in r['recipe']['allergens'] for r in recommend(pantry=KITCHEN, members=nuts, date=MONDAY, now=NOW))


def test_pregnancy_hides_raw_sprouts():
    mum = [{'name': 'Sita', 'goals': ['pregnancy']}]
    assert household_check(R['sprouts_chaat'], mum)['ok'] is False
    assert household_check(R['sprouts_curry'], mum)['ok'] is True


def test_one_meal_many_plates():
    family = [{'name': 'Riya', 'age': 'toddler', 'spice': 1}, {'name': 'Dadaji', 'goals': ['bp'], 'age': 'senior', 'spice': 2},
              {'name': 'Amma', 'diabetic': True, 'spice': 2}, {'name': 'Ravi', 'spice': 3, 'dislikes': ['peanuts']}]
    plates = plates_for(R['kanda_poha'], family)
    tips = lambda who: ' '.join(next((p['tips'] for p in plates if p['who'] == who), []))  # noqa: E731
    assert 'before salt and chilli' in tips('Riya') and 'whole nuts' in tips('Riya')
    assert 'lightly' in tips('Dadaji')
    assert 'smaller portion' in tips('Amma')
    assert 'Leave out peanuts' in tips('Ravi')
    assert 'before adding chilli' in plates_for(R['mutton_curry'], [{'name': 'Sita', 'spice': 1}])[0]['tips'][0]
    assert plates_for(R['jeera_rice'], []) == []


def test_weekly_plan_has_21_different_meals():
    plan = plan_week(start=MONDAY, pantry=KITCHEN, now=NOW)
    ids = [d[s] for d in plan.values() for s in SLOTS]
    assert len(ids) == 21 and all(ids) and len(set(ids)) == 21


def test_weekly_plan_respects_the_whole_family():
    members = [{'name': 'Amma', 'diet': 'veg', 'noOnionGarlic': True, 'allergies': ['nuts']}]
    plan = plan_week(start=MONDAY, pantry=KITCHEN, now=NOW, members=members)
    for day in plan.values():
        for rid in day_recipe_ids(day):
            assert household_check(R[rid], members)['ok'], rid


def test_weekly_plan_keeps_locked_meals():
    first = plan_week(start=MONDAY, pantry=KITCHEN, now=NOW)
    first[MONDAY].update(dinner='chole', locked=['dinner'])
    again = plan_week(start=MONDAY, pantry=KITCHEN, now=NOW, existing=first)
    assert again[MONDAY]['dinner'] == 'chole'
    assert not any(day[s] == 'chole' for d, day in again.items() if d != MONDAY for s in SLOTS)


def test_tiffin_on_school_days_for_each_child_never_repeated():
    members = [{'name': 'Riya', 'age': 'child', 'tiffin': True}, {'name': 'Kabir', 'age': 'teen', 'tiffin': True, 'allergies': ['gluten']}, {'name': 'Amma'}]
    plan = plan_week(start=MONDAY, pantry=KITCHEN, now=NOW, members=members)
    week = list(plan)[:5]
    for kid in ('Riya', 'Kabir'):
        boxes = [plan[d]['tiffins'][kid] for d in week]
        assert all(boxes) and len(set(boxes)) == 5
    assert all('gluten' not in R[plan[d]['tiffins']['Kabir']]['allergens'] for d in week)
    assert plan[add_days(MONDAY, 5)]['tiffins'] == {} and plan[add_days(MONDAY, 6)]['tiffins'] == {}


def test_fasting_gets_a_separate_vrat_meal():
    plan = plan_week(start=MONDAY, pantry=KITCHEN, now=NOW, members=[{'name': 'Dad', 'fastWeekdays': [1]}, {'name': 'Riya'}])
    assert 'vrat' in R[plan[MONDAY]['fast']['Dad']]['tags']
    assert plan[MONDAY]['dinner']
    assert plan[add_days(MONDAY, 1)]['fast'] == {}


def test_festival_fasts_only_when_observed():
    festivals = [{'id': 'ek', 'name': 'Ekadashi', 'date': add_days(MONDAY, 2), 'fast': True}]
    assert fasters_on(add_days(MONDAY, 2), [{'name': 'Amma'}], festivals, [])['festival'] is None
    plan = plan_week(start=MONDAY, pantry=KITCHEN, now=NOW, members=[{'name': 'Amma'}], festivals=festivals, observed=['ek'])
    day = plan[add_days(MONDAY, 2)]
    assert day['festival'] == 'Ekadashi' and 'vrat' in R[day['fast']['Family']]['tags']


def test_prep_reminders():
    assert 'Soak' in prep_for(R['rajma_masala'])
    assert 'batter' in prep_for(R['idli']).lower()
    assert 'fridge' in prep_for(R['chicken_curry'])
    prep = prep_tonight({add_days(MONDAY, 1): {'lunch': 'rajma_masala', 'breakfast': 'jeera_rice'}}, MONDAY)
    assert [p['name'] for p in prep] == ['Rajma Masala']
    assert prep_tonight({}, MONDAY) == []


def test_leftover_chains():
    rice = leftover_chains(R['jeera_rice'])
    assert rice[0]['item'] == 'leftover_rice' and 'Lemon Rice' in rice[0]['ideas']
    assert any(c['item'] == 'leftover_dal' for c in leftover_chains(R['dal_tadka']))
    assert any(c['item'] == 'leftover_roti' for c in leftover_chains(R['aloo_paratha']))


def test_grocery_list_only_what_is_missing():
    groceries = plan_groceries({MONDAY: {'dinner': 'palak_paneer', 'lunch': 'matar_paneer'}}, MONDAY, pantry=[{'id': 'spinach'}])
    assert len(next(g for g in groceries if g['id'] == 'paneer')['dishes']) == 2
    assert not any(g['id'] in ('spinach', 'salt') for g in groceries)


def test_old_history_entries_still_work():
    entry = normalize_log([{'recipeId': 'idli', 'name': 'Idli', 'at': NOW}])[0]
    assert entry['date'] == MONDAY and entry['slot'] in SLOTS


def test_dashboard_is_calm_when_empty():
    d = dashboard([], now=NOW)
    assert d['total'] == 0 and d['variety'] is None and d['insights'] == []


def test_dashboard_spots_missing_greens_and_repeats():
    d = dashboard([logged('jeera_rice', 0), logged('jeera_rice', 1), logged('jeera_rice', 2), logged('dal_tadka', 3), logged('palak_paneer', 6)], now=NOW)
    text = ' | '.join(i['text'] for i in d['insights'])
    assert d['weekCount'] == 5 and d['groups']['greens'] == 1 and d['lastGroup']['greens'] == 6
    assert 'No leafy greens in 6 days' in text and 'Jeera Rice was made 3 times' in text
    assert d['variety'] == 60


def test_dashboard_remembers_forgotten_favourites():
    d = dashboard([logged('rajma_masala', 30, rating=5), logged('idli', 1), logged('dal_tadka', 2)], now=NOW)
    assert "haven't made Rajma Masala in 30 days" in ' '.join(i['text'] for i in d['insights'])
    assert d['missed'][0]['id'] == 'rajma_masala'


def test_dashboard_counts_meals_from_outside():
    d = dashboard([{'recipeId': None, 'name': 'Pizza (ordered)', 'date': MONDAY, 'slot': 'dinner'}], now=NOW)
    assert d['total'] == 1 and d['top'][0]['name'] == 'Pizza (ordered)'


def test_dashboard_praises_real_variety():
    ids = ['idli', 'dal_tadka', 'palak_paneer', 'poriyal', 'mixed_veg', 'kootu']
    d = dashboard([logged(i, n) for n, i in enumerate(ids)], now=NOW)
    assert any(i['kind'] == 'good' and 'variety' in i['text'] for i in d['insights'])


def test_menu_for_the_cook_in_their_language():
    day = {'breakfast': 'idli', 'lunch': 'dal_tadka', 'dinner': 'mutton_curry', 'tiffins': {'Riya': 'veg_sandwich'}}
    hi = menu_message(day, lang='hi', members=[{'name': 'Sita', 'spice': 1}])
    assert 'आज का मेन्यू' in hi and 'नाश्ता: Idli' in hi and 'Tiffin, Riya' in hi and 'Sita (Home-style Mutton Curry)' in hi
    assert 'ఈ రోజు మెనూ' in menu_message(day, lang='te')
    assert 'இன்றைய மெனு' in menu_message(day, lang='ta')


def test_ask_ballava_answers_common_questions():
    plan = {MONDAY: {'dinner': 'dal_tadka'}, add_days(MONDAY, 1): {'lunch': 'rajma_masala'}}
    ask = lambda q, **kw: assistant_reply(q, pantry=KITCHEN, plan=kw.get('plan', plan), now=NOW, log=[])['reply']  # noqa: E731
    assert 'Your plan says Dal Tadka' in ask('What should I cook tonight?')
    assert 'tiffin ideas' in ask('tiffin ideas')
    assert 'Rajma Masala' in ask("what's for tomorrow?")
    assert 'Soak' in ask('what should I prep tonight')
    assert 'Palak Paneer' in ask('I have paneer and spinach')
    assert 'Try "What should I cook tonight?"' in ask('hello')
    assert 'Plan my week' in ask('tomorrow', plan={})


def test_ask_ballava_answers_food_questions_without_ai():
    """The questions the old keyword matcher got wrong: calories, protein, fixes, and two named ingredients."""
    ask = lambda q, **kw: assistant_reply(q, pantry=KITCHEN, now=NOW, log=[], **kw)  # noqa: E731
    kcal = R['dal_tadka']['nutrition']['kcal']
    assert f'Dal Tadka: about {kcal} kcal per serving' in ask('How many calories in dal tadka?')['reply']
    assert 'Curd Rice: about' in ask('Is curd rice healthy?')['reply']
    assert 'Paneer: 265 kcal' in ask('calories in paneer')['reply']
    assert 'Kanda Poha: about' in ask('calories in this?', current=R['kanda_poha'])['reply'], 'the open recipe'
    protein = ask('Give me a high protein lunch')
    assert protein['reply'].startswith('Protein-rich ideas') and all(R[i]['nutrition']['protein'] >= 12 for i in protein['dishes'])
    light = ask('light dinner ideas for weight loss')
    assert light['dishes'] and all(R[i]['nutrition']['kcal'] <= 400 for i in light['dishes'])
    assert 'Spread it on a plate' in ask('My rice is too sticky')['reply'], 'a Bachao fix'
    eggs = ask('what can I make with egg and onion')
    assert eggs['dishes'] and all('egg' in {o for it in R[i]['ingredients'] for o in it['options']} for i in eggs['dishes'][:2])


def test_ask_ballava_respects_the_family():
    kw = dict(pantry=[{'id': i} for i in ['chicken', 'onion', 'tomato']], members=[{'name': 'Amma', 'diet': 'veg'}], now=NOW, log=[])
    assert 'chicken' not in assistant_reply('dinner ideas', **kw)['reply'].lower()
    assert 'Chicken' not in assistant_reply('I have chicken and onion', **kw)['reply'].split('make:')[-1]
