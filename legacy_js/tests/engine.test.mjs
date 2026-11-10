// Tests for the cooking brain. Run: npm test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { INGREDIENTS, BY_ID, JAIN_BLOCKED, ONION_GARLIC, KITS } from '../shared/ingredients.mjs';
import { RESCUES } from '../shared/rescue.mjs';
import {
  ALL_RECIPES, RECIPE_BY_ID, parseIngredients, parseStep, suggest, buyTips, householdCheck, useSoon, daysLeft,
  defaultExpiry, chatReply, findRescue, normalizeAiRecipe, recipeText,
} from '../shared/engine.mjs';

const pantryOf = ids => ids.map(id => ({ id }));
const DAY = 86400000;

// ---------- Data quality: catches typos in the recipe book ----------
test('every recipe ingredient exists in the catalog', () => {
  for (const r of ALL_RECIPES) for (const it of r.ingredients) for (const id of it.options) {
    assert.ok(BY_ID[id], `${r.id} uses unknown ingredient "${id}"`);
  }
});

test('recipes are complete and ids are unique', () => {
  const ids = new Set();
  for (const r of ALL_RECIPES) {
    assert.ok(!ids.has(r.id), `duplicate id ${r.id}`); ids.add(r.id);
    assert.ok(r.name && r.time > 0 && r.serves > 0, `${r.id} missing basics`);
    assert.ok([1, 2, 3].includes(r.spice), `${r.id} spice must be 1-3`);
    assert.ok(r.steps.length >= 2, `${r.id} needs steps`);
    assert.ok(r.steps.every(s => s.text.length > 5), `${r.id} has an empty step`);
    assert.ok(r.ingredients.some(i => !i.optional), `${r.id} needs a required ingredient`);
    assert.ok(Array.isArray(r.meal) && r.meal.length, `${r.id} needs meal types`);
  }
  assert.ok(ALL_RECIPES.length >= 45);
});

test('ingredient ids and aliases are sane', () => {
  const ids = new Set();
  for (const i of INGREDIENTS) { assert.ok(!ids.has(i.id), i.id); ids.add(i.id); assert.ok(i.aliases.every(a => a === a.trim() && a)); }
  for (const k of KITS) for (const id of k.items) assert.ok(BY_ID[id], `kit ${k.id}: ${id}`);
});

test('tags match the actual ingredients (no false promises)', () => {
  for (const r of ALL_RECIPES) {
    if (r.tags.includes('jain')) assert.ok(r.jainOk, `${r.id} tagged jain but needs root veg/onion/garlic`);
    if (r.tags.includes('vrat')) assert.ok(!r.needsOnionGarlic, `${r.id} vrat dish needs onion/garlic`);
    if (r.tags.includes('gluten-free')) assert.ok(!r.allergens.includes('gluten'), `${r.id} tagged gluten-free but has gluten`);
    if (r.tags.includes('diabetic-friendly')) assert.ok(!r.tags.includes('sweet'), `${r.id}`);
    if (r.tags.includes('leftover')) assert.ok(r.ingredients.some(i => i.options.some(id => BY_ID[id].category === 'Leftovers' || id === 'bread')), `${r.id} leftover tag`);
  }
});

test('risky dishes carry a food-safety note', () => {
  for (const r of ALL_RECIPES) {
    const usesRiskyRice = r.ingredients.some(i => !i.optional && i.options.length === 1 && i.options[0] === 'leftover_rice');
    const meat = r.diet === 'nonveg';
    if ((usesRiskyRice && r.tags.includes('leftover')) || meat) assert.ok(r.safety, `${r.id} should have a safety note`);
  }
});

test('Bachao rescue entries are complete', () => {
  for (const r of RESCUES) assert.ok(r.title && r.fixes.length >= 2, r.id);
  assert.ok(RESCUES.some(r => r.id === 'safe'), 'must include "is it safe" guidance');
});

// ---------- Understanding what people type ----------
test('understands Hindi, Telugu and English words', () => {
  const { found } = parseIngredients('2 tamatar, pyaz aur thoda dahi, palak, kodi, pesarapappu');
  for (const id of ['tomato', 'onion', 'curd', 'spinach', 'chicken', 'moong_dal']) assert.ok(found.includes(id), id);
});

test('prefers longer names: leftover rice is not raw rice, green chilli is not chilli powder', () => {
  assert.deepEqual(parseIngredients('leftover chawal').found, ['leftover_rice']);
  assert.deepEqual(parseIngredients('lal mirch').found, ['red_chilli_powder']);
  assert.deepEqual(parseIngredients('hari mirch').found, ['green_chilli']);
  assert.deepEqual(parseIngredients('chana dal').found, ['chana_dal']);
  assert.deepEqual(parseIngredients('cottage cheese').found, ['paneer']);
});

test('handles plurals, numbers and reports unknown words', () => {
  const r = parseIngredients('3 Tomatoes, 2 potatoes, eggs and dragonfruit');
  assert.deepEqual(r.found.sort(), ['egg', 'potato', 'tomato']);
  assert.deepEqual(r.unknown, ['dragonfruit']);
  assert.deepEqual(parseIngredients('').found, []);
});

test('step timers and whistles are read correctly', () => {
  assert.deepEqual(parseStep('Simmer. |10m'), { text: 'Simmer.', minutes: 10 });
  assert.deepEqual(parseStep('Pressure cook. |3w'), { text: 'Pressure cook.', whistles: 3 });
  assert.deepEqual(parseStep('Serve hot.'), { text: 'Serve hot.' });
});

// ---------- Suggestions ----------
test('suggests complete dishes first', () => {
  const { ready } = suggest({ pantry: pantryOf(['egg', 'onion', 'tomato', 'green_chilli', 'turmeric']) });
  assert.ok(ready.length > 0);
  assert.ok(ready.some(r => r.recipe.id === 'masala_omelette'));
  assert.ok(ready.every(r => r.missing.length === 0));
});

test('things about to spoil push dishes up', () => {
  const now = Date.now();
  const base = ['onion', 'tomato', 'green_chilli', 'turmeric', 'cumin', 'red_chilli_powder', 'coriander_powder', 'garam_masala', 'ginger', 'garlic', 'peas'];
  const fresh = suggest({ pantry: [...pantryOf(base), { id: 'paneer', expiresAt: now + 10 * DAY }, { id: 'egg', expiresAt: now + 10 * DAY }], now });
  const spoiling = suggest({ pantry: [...pantryOf(base), { id: 'paneer', expiresAt: now + 1 * DAY }, { id: 'egg', expiresAt: now + 10 * DAY }], now });
  const rank = (res, id) => res.ready.findIndex(r => r.recipe.id === id);
  assert.ok(rank(spoiling, 'paneer_bhurji') < rank(fresh, 'paneer_bhurji'), 'paneer dish should rank higher when paneer is spoiling');
  assert.ok(spoiling.ready.find(r => r.recipe.id === 'paneer_bhurji').usesSoon.includes('paneer'));
});

test('filters work: veg, quick, leftover, vrat', () => {
  const pantry = pantryOf(['egg', 'onion', 'tomato', 'chicken', 'leftover_rice', 'curd', 'sabudana', 'peanuts', 'potato', 'cumin', 'green_chilli']);
  const all = (f) => { const s = suggest({ pantry, filters: f }); return [...s.ready, ...s.almost].map(r => r.recipe); };
  assert.ok(all({ veg: true }).every(r => r.diet === 'veg'));
  assert.ok(all({ quick: true }).every(r => r.time <= 20));
  assert.ok(all({ leftover: true }).every(r => r.tags.includes('leftover')));
  assert.ok(all({ vrat: true }).every(r => r.tags.includes('vrat')));
  assert.ok(all({ vrat: true }).some(r => r.id === 'sabudana_khichdi'));
});

test('your ratings change the order (learning your andaaz)', () => {
  const pantry = pantryOf(['egg', 'onion', 'tomato', 'green_chilli', 'turmeric']);
  const before = suggest({ pantry }).ready.map(r => r.recipe.id);
  const loved = before[before.length - 1];
  const after = suggest({ pantry, ratings: { [loved]: 5, [before[0]]: 1 } }).ready.map(r => r.recipe.id);
  assert.ok(after.indexOf(loved) < before.indexOf(loved));
});

test('buy tips point to the single item that unlocks the most dishes', () => {
  const tips = buyTips({ pantry: pantryOf(['onion', 'tomato', 'green_chilli', 'turmeric', 'red_chilli_powder', 'ginger', 'garlic']) });
  assert.ok(tips.length > 0);
  assert.ok(tips[0].dishes.length >= tips[tips.length - 1].dishes.length);
});

// ---------- Family rules ----------
test('vegetarian family member hides meat and egg dishes', () => {
  const members = [{ name: 'Amma', diet: 'veg' }];
  const s = suggest({ pantry: pantryOf(['chicken', 'egg', 'onion', 'tomato', 'ginger', 'garlic', 'paneer']), members });
  assert.ok([...s.ready, ...s.almost].every(r => r.recipe.diet === 'veg'));
  assert.equal(householdCheck(RECIPE_BY_ID.chicken_curry, members).ok, false);
});

test('allergies, Jain, no onion-garlic, diabetic and fasting rules', () => {
  assert.equal(householdCheck(RECIPE_BY_ID.palak_paneer, [{ name: 'A', allergies: ['dairy'] }]).ok, false);
  assert.equal(householdCheck(RECIPE_BY_ID.rava_upma, [{ name: 'A', allergies: ['gluten'] }]).ok, false);
  // Peanuts are optional in poha, so a nut allergy gives a tip instead of hiding it.
  const poha = householdCheck(RECIPE_BY_ID.kanda_poha, [{ name: 'Riya', allergies: ['nuts'] }]);
  assert.equal(poha.ok, true); assert.match(poha.notes.join(' '), /nuts/);
  assert.equal(householdCheck(RECIPE_BY_ID.aloo_gobi, [{ name: 'A', jain: true }]).ok, false);
  assert.equal(householdCheck(RECIPE_BY_ID.idli, [{ name: 'A', jain: true }]).ok, true);
  assert.equal(householdCheck(RECIPE_BY_ID.chana_masala, [{ name: 'A', noOnionGarlic: true }]).ok, false);
  assert.equal(householdCheck(RECIPE_BY_ID.sooji_halwa, [{ name: 'Dad', diabetic: true }]).ok, false);
  assert.equal(householdCheck(RECIPE_BY_ID.dal_tadka, [{ name: 'Maa', fasting: true }]).ok, false);
  assert.equal(householdCheck(RECIPE_BY_ID.sabudana_khichdi, [{ name: 'Maa', fasting: true }]).ok, true);
});

test('low spice member gets a "mild portion" tip', () => {
  const r = householdCheck(RECIPE_BY_ID.tomato_pappu, [{ name: 'Chintu', spice: 1 }]);
  assert.equal(r.ok, true);
  assert.match(r.notes.join(' '), /mild portion for Chintu/);
});

// ---------- Freshness ----------
test('expiry tracking', () => {
  const now = Date.now();
  assert.equal(daysLeft({ expiresAt: now + 2 * DAY }, now), 2);
  assert.equal(daysLeft({ expiresAt: null }, now), null);
  assert.ok(defaultExpiry('tomato', now) > now);
  assert.equal(defaultExpiry('rice', now), null);
  const soon = useSoon([{ id: 'a', expiresAt: now + 5 * DAY }, { id: 'b', expiresAt: now + DAY }, { id: 'c', expiresAt: null }], now);
  assert.deepEqual(soon.map(s => s.id), ['b']);
});

// ---------- Chat brain, rescue, sharing, AI safety ----------
test('chat reply works like a WhatsApp bot', () => {
  const r = chatReply('I have poha, onion, potato, peanuts and lemon');
  assert.match(r.reply, /Kanda Poha/);
  assert.match(chatReply('hello').reply, /Tell me what you have/);
});

test('Bachao finds the right fix', () => {
  assert.equal(findRescue('dal is too salty')[0].id, 'too_salty');
  assert.ok(findRescue('it got burnt').some(r => r.id === 'burnt_bottom'));
  assert.equal(findRescue('').length, RESCUES.length);
});

test('recipe text for sharing includes steps', () => {
  const t = recipeText(RECIPE_BY_ID.dal_tadka);
  assert.match(t, /Dal Tadka/); assert.match(t, /1\. /);
});

test('AI recipes are checked and cleaned before showing', () => {
  const r = normalizeAiRecipe({
    name: 'Paneer Pepper Fry', time: 20, spice: 2,
    ingredients: [{ name: 'paneer', quantity: '200 g' }, { name: 'black pepper', quantity: '1 tsp' }, { name: 'kokum', quantity: '2', optional: true }],
    steps: [{ text: 'Fry paneer', minutes: 3 }, 'Add pepper. |2m'],
  });
  assert.equal(r.ai, true);
  assert.equal(r.ingredients[0].options[0], 'paneer');
  assert.equal(r.ingredients[2].custom, 'kokum');
  assert.ok(r.allergens.includes('dairy'));
  assert.equal(r.steps[1].minutes, 2);
  assert.throws(() => normalizeAiRecipe({ name: 'x', ingredients: [], steps: [] }));
  assert.throws(() => normalizeAiRecipe(null));
});
