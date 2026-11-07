// Tests for the planner: no-repeat logic, family diets, weekly plans and the dashboard.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ALL_RECIPES, RECIPE_BY_ID, householdCheck, validateRecipe } from '../shared/engine.mjs';
import { RECIPES } from '../shared/recipes.mjs';
import {
  addDays, dayKey, daysBetween, mainsOf, baseOf, groupsOf, repeatCheck, recommend, goalScore, platesFor, planWeek, dayRecipeIds, prepFor,
  prepTonight, leftoverChains, planGroceries, dashboard, normalizeLog, menuMessage, assistantReply, fastersOn, SLOTS, TIFFIN_IDS,
} from '../shared/planner.mjs';

const R = id => RECIPE_BY_ID[id];
const pantryOf = ids => ids.map(id => ({ id }));
const MONDAY = '2026-11-09';
const NOW = new Date(MONDAY + 'T12:00:00').getTime();
const KITCHEN = pantryOf(['rice', 'toor_dal', 'moong_dal', 'onion', 'tomato', 'potato', 'atta', 'curd', 'egg', 'turmeric', 'cumin', 'mustard_seeds',
  'red_chilli_powder', 'coriander_powder', 'poha', 'peas', 'spinach', 'green_chilli', 'ginger', 'garlic', 'lemon']);

test('recipe book is big enough for a no-repeat week, and every recipe passes publishing rules', () => {
  assert.ok(ALL_RECIPES.length >= 100);
  for (const r of RECIPES) assert.deepEqual(validateRecipe(r), [], r.id);
  for (const slot of SLOTS) assert.ok(ALL_RECIPES.filter(r => r.meal.includes(slot)).length >= 25, slot);
  assert.ok(ALL_RECIPES.filter(r => r.tags.includes('vrat')).length >= 5);
  for (const id of TIFFIN_IDS) assert.ok(R(id), id);
});

test('dates work across months', () => {
  assert.equal(addDays('2026-11-30', 1), '2026-12-01');
  assert.equal(daysBetween('2026-11-30', '2026-12-02'), 2);
  assert.equal(dayKey(NOW), MONDAY);
});

test('knows what a dish is about', () => {
  assert.ok(mainsOf(R('aloo_gobi')).includes('potato'));
  assert.ok(!mainsOf(R('aloo_gobi')).includes('onion'));
  assert.equal(baseOf(R('lemon_rice')), 'rice');
  assert.equal(baseOf(R('aloo_paratha')), 'wheat');
  assert.ok(groupsOf(R('palak_paneer')).includes('greens'));
  assert.ok(groupsOf(R('dal_tadka')).includes('protein'));
  assert.ok(!groupsOf(R('jeera_rice')).includes('protein'));
});

test('the same dish is pushed down, more strongly the more recent it was', () => {
  const log = d => [{ recipeId: 'dal_tadka', date: addDays(MONDAY, -d), slot: 'dinner' }];
  const p = d => repeatCheck(R('dal_tadka'), log(d), { date: MONDAY }).penalty;
  assert.ok(p(1) > p(5) && p(5) > p(10) && p(10) > 0);
  assert.equal(p(20), 0);
  assert.match(repeatCheck(R('dal_tadka'), log(1), { date: MONDAY }).reasons[0], /1 day ago/);
});

test('a different dish with the same main ingredient also counts as a repeat', () => {
  const log = [{ recipeId: 'aloo_gobi', date: addDays(MONDAY, -1), slot: 'dinner' }];
  const r = repeatCheck(R('jeera_aloo'), log, { date: MONDAY });
  assert.ok(r.penalty > 0);
  assert.match(r.reasons[0], /potato/i);
  assert.equal(repeatCheck(R('fish_curry'), log, { date: MONDAY }).penalty, 0);
});

test('rice at every meal is noticed', () => {
  const log = [{ recipeId: 'lemon_rice', date: MONDAY, slot: 'lunch' }];
  assert.ok(repeatCheck(R('veg_pulao'), log, { date: MONDAY }).penalty >= 10);
});

test('recommendations stop repeating what the family just ate', () => {
  const first = recommend({ pantry: KITCHEN, slot: 'dinner', date: MONDAY, now: NOW })[0].recipe.id;
  const next = recommend({ pantry: KITCHEN, slot: 'dinner', date: MONDAY, now: NOW, log: [{ recipeId: first, date: addDays(MONDAY, -1), slot: 'dinner' }] });
  assert.notEqual(next[0].recipe.id, first);
});

test('a pinned family tradition is not a repeat, and comes first on its day', () => {
  const pins = [{ recipeId: 'rajma_masala', weekday: 0, slot: 'lunch' }];
  const sunday = addDays(MONDAY, 6);
  const log = [{ recipeId: 'rajma_masala', date: addDays(sunday, -7), slot: 'lunch' }];
  assert.equal(repeatCheck(R('rajma_masala'), log, { date: sunday, pins }).penalty, 0);
  const top = recommend({ pantry: KITCHEN, slot: 'lunch', date: sunday, now: NOW, pins, log })[0];
  assert.equal(top.recipe.id, 'rajma_masala');
  assert.match(top.why[0], /Sun favourite/);
});

test('family goals change the ranking', () => {
  const diabetic = [{ name: 'Amma', diabetic: true }];
  assert.ok(goalScore(R('dal_palak'), diabetic).bonus > goalScore(R('jeera_rice'), diabetic).bonus);
  const bp = [{ name: 'Dad', goals: ['bp'] }];
  assert.ok(goalScore(R('hakka_noodles'), bp).bonus < 0);
  const kid = [{ name: 'Riya', age: 'child' }];
  assert.ok(goalScore(R('veg_sandwich'), kid).bonus > 0);
  assert.match(goalScore(R('veg_sandwich'), kid).why[0], /Riya/);
});

test('dislikes push a dish down, likes pull it up', () => {
  const hates = [{ name: 'Ravi', dislikes: ['bitter_gourd'] }];
  const loves = [{ name: 'Ravi', likes: ['bitter_gourd'] }];
  assert.ok(goalScore(R('karela_fry'), hates).bonus < goalScore(R('karela_fry'), loves).bonus);
});

test('family safety rules always win, however good the score', () => {
  const veg = [{ name: 'Amma', diet: 'veg' }];
  const list = recommend({ pantry: pantryOf(['chicken', 'onion', 'tomato']), members: veg, slot: 'dinner', date: MONDAY, now: NOW });
  assert.ok(list.length > 0 && list.every(r => r.recipe.diet === 'veg'));
  const nuts = [{ name: 'Riya', allergies: ['nuts'] }];
  assert.ok(recommend({ pantry: KITCHEN, members: nuts, date: MONDAY, now: NOW }).every(r => !r.recipe.allergens.includes('nuts')));
});

test('pregnancy: raw sprouts are hidden', () => {
  const mum = [{ name: 'Sita', goals: ['pregnancy'] }];
  assert.equal(householdCheck(R('sprouts_chaat'), mum).ok, false);
  assert.equal(householdCheck(R('sprouts_curry'), mum).ok, true);
});

test('one meal, many plates: each person gets their own tip', () => {
  const family = [
    { name: 'Riya', age: 'toddler', spice: 1 }, { name: 'Dadaji', goals: ['bp'], age: 'senior', spice: 2 },
    { name: 'Amma', diabetic: true, spice: 2 }, { name: 'Ravi', spice: 3, dislikes: ['peanuts'] },
  ];
  const plates = platesFor(R('kanda_poha'), family);
  const tips = name => plates.find(p => p.who === name)?.tips.join(' ') || '';
  assert.match(tips('Riya'), /before salt and chilli/);
  assert.match(tips('Riya'), /whole nuts/);
  assert.match(tips('Dadaji'), /lightly/);
  assert.match(tips('Amma'), /smaller portion/);
  assert.match(tips('Ravi'), /Leave out peanuts/);
  const spicy = platesFor(R('mutton_curry'), [{ name: 'Sita', spice: 1 }]);
  assert.match(spicy[0].tips[0], /before adding chilli/);
  assert.deepEqual(platesFor(R('jeera_rice'), []), []);
});

test('weekly plan: 21 meals with no dish repeated', () => {
  const plan = planWeek({ start: MONDAY, pantry: KITCHEN, now: NOW });
  const ids = Object.values(plan).flatMap(d => SLOTS.map(s => d[s]));
  assert.equal(ids.length, 21);
  assert.ok(ids.every(Boolean));
  assert.equal(new Set(ids).size, 21, ids.join());
});

test('weekly plan respects the whole family', () => {
  const members = [{ name: 'Amma', diet: 'veg', noOnionGarlic: true, allergies: ['nuts'] }];
  const plan = planWeek({ start: MONDAY, pantry: KITCHEN, now: NOW, members });
  for (const day of Object.values(plan)) for (const id of dayRecipeIds(day)) {
    assert.equal(householdCheck(R(id), members.map(m => ({ ...m, fasting: false }))).ok, true, id);
  }
});

test('weekly plan keeps what you locked, and only replaces the rest', () => {
  const first = planWeek({ start: MONDAY, pantry: KITCHEN, now: NOW });
  first[MONDAY].dinner = 'chole';
  first[MONDAY].locked = ['dinner'];
  const again = planWeek({ start: MONDAY, pantry: KITCHEN, now: NOW, existing: first });
  assert.equal(again[MONDAY].dinner, 'chole');
  assert.ok(!Object.entries(again).some(([d, day]) => d !== MONDAY && SLOTS.some(s => day[s] === 'chole')));
});

test('tiffin: school days only, for each child, never repeated in the week', () => {
  const members = [{ name: 'Riya', age: 'child', tiffin: true }, { name: 'Kabir', age: 'teen', tiffin: true, allergies: ['gluten'] }, { name: 'Amma' }];
  const plan = planWeek({ start: MONDAY, pantry: KITCHEN, now: NOW, members });
  const week = Object.keys(plan).slice(0, 5);
  for (const kid of ['Riya', 'Kabir']) {
    const boxes = week.map(d => plan[d].tiffins[kid]);
    assert.ok(boxes.every(Boolean), kid);
    assert.equal(new Set(boxes).size, 5, boxes.join());
  }
  for (const d of week) assert.equal(R(plan[d].tiffins.Kabir).allergens.includes('gluten'), false);
  assert.deepEqual(plan[addDays(MONDAY, 5)].tiffins, {});
  assert.deepEqual(plan[addDays(MONDAY, 6)].tiffins, {});
});

test('fasting: a separate vrat meal, while the family eats normally', () => {
  const members = [{ name: 'Dad', fastWeekdays: [1] }, { name: 'Riya' }];
  const plan = planWeek({ start: MONDAY, pantry: KITCHEN, now: NOW, members });
  assert.ok(R(plan[MONDAY].fast.Dad).tags.includes('vrat'));
  assert.ok(plan[MONDAY].dinner);
  assert.deepEqual(plan[addDays(MONDAY, 1)].fast, {});
});

test('festival fasts only apply when the family observes them', () => {
  const festivals = [{ id: 'ek', name: 'Ekadashi', date: addDays(MONDAY, 2), fast: true }];
  const members = [{ name: 'Amma' }];
  assert.equal(fastersOn(addDays(MONDAY, 2), members, festivals, []).festival, null);
  const plan = planWeek({ start: MONDAY, pantry: KITCHEN, now: NOW, members, festivals, observed: ['ek'] });
  const day = plan[addDays(MONDAY, 2)];
  assert.equal(day.festival, 'Ekadashi');
  assert.ok(R(day.fast.Family).tags.includes('vrat'));
});

test('prep reminders: tonight tells you what tomorrow needs', () => {
  assert.match(prepFor(R('rajma_masala')), /Soak/);
  assert.match(prepFor(R('idli')), /ferment|batter/i);
  assert.match(prepFor(R('chicken_curry')), /fridge/);
  const plan = { [addDays(MONDAY, 1)]: { lunch: 'rajma_masala', breakfast: 'jeera_rice' } };
  const prep = prepTonight(plan, MONDAY);
  assert.equal(prep.length, 1);
  assert.equal(prep[0].name, 'Rajma Masala');
  assert.deepEqual(prepTonight({}, MONDAY), []);
});

test('leftover chains: rice tonight becomes lemon rice tomorrow', () => {
  const rice = leftoverChains(R('jeera_rice'));
  assert.equal(rice[0].item, 'leftover_rice');
  assert.ok(rice[0].ideas.includes('Lemon Rice'));
  assert.ok(leftoverChains(R('dal_tadka')).some(c => c.item === 'leftover_dal'));
  assert.ok(leftoverChains(R('aloo_paratha')).some(c => c.item === 'leftover_roti'));
});

test('grocery list: only what the plan needs and you do not have', () => {
  const plan = { [MONDAY]: { dinner: 'palak_paneer', lunch: 'matar_paneer' } };
  const list = planGroceries(plan, { from: MONDAY, pantry: pantryOf(['spinach']) });
  const paneer = list.find(i => i.id === 'paneer');
  assert.equal(paneer.dishes.length, 2);
  assert.ok(!list.some(i => i.id === 'spinach' || i.id === 'salt'));
});

test('old history entries still work', () => {
  const [e] = normalizeLog([{ recipeId: 'idli', name: 'Idli', at: NOW }]);
  assert.equal(e.date, MONDAY);
  assert.ok(SLOTS.includes(e.slot));
});

const logged = (id, daysAgo, extra = {}) => ({ recipeId: id, name: R(id)?.name || id, date: addDays(MONDAY, -daysAgo), slot: 'dinner', ...extra });

test('dashboard: empty history is calm, with no made-up advice', () => {
  const d = dashboard([], { now: NOW });
  assert.equal(d.total, 0);
  assert.equal(d.variety, null);
  assert.deepEqual(d.insights, []);
});

test('dashboard: spots missing greens and repeats, kindly', () => {
  const d = dashboard([logged('jeera_rice', 0), logged('jeera_rice', 1), logged('jeera_rice', 2), logged('dal_tadka', 3), logged('palak_paneer', 6)], { now: NOW });
  assert.equal(d.weekCount, 5);
  assert.equal(d.groups.greens, 1);
  assert.equal(d.lastGroup.greens, 6);
  const text = d.insights.map(i => i.text).join(' | ');
  assert.match(text, /No leafy greens in 6 days/);
  assert.match(text, /Jeera Rice was made 3 times/);
  assert.equal(d.variety, 60);
});

test('dashboard: remembers favourites you have not made in a while', () => {
  const d = dashboard([logged('rajma_masala', 30, { rating: 5 }), logged('idli', 1), logged('dal_tadka', 2)], { now: NOW });
  assert.match(d.insights.map(i => i.text).join(), /haven't made Rajma Masala in 30 days/);
  assert.equal(d.missed[0].id, 'rajma_masala');
});

test('dashboard: meals from outside are counted without crashing', () => {
  const d = dashboard([{ recipeId: null, name: 'Pizza (ordered)', date: MONDAY, slot: 'dinner' }], { now: NOW });
  assert.equal(d.total, 1);
  assert.equal(d.top[0].name, 'Pizza (ordered)');
});

test('dashboard: praises real variety', () => {
  const ids = ['idli', 'dal_tadka', 'palak_paneer', 'poriyal', 'mixed_veg', 'kootu'];
  const d = dashboard(ids.map((id, i) => logged(id, i)), { now: NOW });
  assert.ok(d.insights.some(i => i.kind === 'good' && /variety/.test(i.text)));
});

test('menu for the house cook comes in their language, with portion notes', () => {
  const day = { breakfast: 'idli', lunch: 'dal_tadka', dinner: 'mutton_curry', tiffins: { Riya: 'veg_sandwich' } };
  const hi = menuMessage(day, { lang: 'hi', members: [{ name: 'Sita', spice: 1 }] });
  assert.match(hi, /आज का मेन्यू/);
  assert.match(hi, /नाश्ता: Idli/);
  assert.match(hi, /Tiffin, Riya/);
  assert.match(hi, /Sita \(Home-style Mutton Curry\)/);
  assert.match(menuMessage(day, { lang: 'te' }), /ఈ రోజు మెనూ/);
  assert.match(menuMessage(day, { lang: 'ta' }), /இன்றைய மெனு/);
});

test('Ask Ballava answers common questions', () => {
  const plan = { [MONDAY]: { dinner: 'dal_tadka' }, [addDays(MONDAY, 1)]: { lunch: 'rajma_masala' } };
  const ctx = { pantry: KITCHEN, plan, now: NOW, log: [] };
  assert.match(assistantReply('What should I cook tonight?', ctx).reply, /Your plan says Dal Tadka/);
  assert.match(assistantReply('tiffin ideas', ctx).reply, /tiffin ideas/);
  assert.match(assistantReply("what's for tomorrow?", ctx).reply, /Rajma Masala/);
  assert.match(assistantReply('what should I prep tonight', ctx).reply, /Soak/);
  assert.match(assistantReply('I have paneer and spinach', ctx).reply, /Palak Paneer/);
  assert.match(assistantReply('hello', ctx).reply, /Ask me/);
  assert.match(assistantReply('tomorrow', { ...ctx, plan: {} }).reply, /Plan my week/);
});

test('Ask Ballava respects the family', () => {
  const ctx = { pantry: pantryOf(['chicken', 'onion', 'tomato']), members: [{ name: 'Amma', diet: 'veg' }], now: NOW, log: [] };
  assert.ok(!/chicken/i.test(assistantReply('dinner ideas', ctx).reply));
  assert.ok(!/Chicken/.test(assistantReply('I have chicken and onion', ctx).reply.split('make:')[1] || ''));
});
