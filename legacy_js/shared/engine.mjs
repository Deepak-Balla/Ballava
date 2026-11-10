// Ballava cooking brain. Pure functions only (no browser or server code), so the
// same logic runs in the app, on the server and inside the tests.
import { INGREDIENTS, BY_ID, ASSUMED, JAIN_BLOCKED, ONION_GARLIC } from './ingredients.mjs';
import { RECIPES } from './recipes.mjs';
import { RESCUES } from './rescue.mjs';

const DAY = 24 * 60 * 60 * 1000;

// ---------------------------------------------------------------- recipe prep
// Turn the compact recipe text format into structured objects (once).
export function parseIngredientLine(line) {
  const idx = line.indexOf(':');
  let key = idx === -1 ? line : line.slice(0, idx);
  const qty = idx === -1 ? '' : line.slice(idx + 1).trim();
  const optional = key.endsWith('?');
  if (optional) key = key.slice(0, -1);
  const options = key.split('|').map(s => s.trim()).filter(Boolean);
  return { options, qty, optional };
}

export function parseStep(step) {
  const m = step.match(/\s*\|(\d+)([mw])\s*$/);
  if (!m) return { text: step.trim() };
  const text = step.slice(0, m.index).trim();
  return m[2] === 'm' ? { text, minutes: Number(m[1]) } : { text, whistles: Number(m[1]) };
}

const DIET_RANK = { veg: 0, egg: 1, nonveg: 2 };

export function prepareRecipe(r) {
  const ingredients = r.ing.map(parseIngredientLine);
  const required = ingredients.filter(i => !i.optional);
  // Diet level: worst of the required ingredients (optional ones can be skipped).
  let diet = 'veg';
  for (const it of required) {
    const lvl = Math.min(...it.options.map(id => DIET_RANK[BY_ID[id]?.diet || 'veg']));
    if (lvl > DIET_RANK[diet]) diet = Object.keys(DIET_RANK)[lvl];
  }
  // Allergens: from required lines where EVERY option has that allergen.
  const allergens = new Set();
  for (const it of required) {
    const sets = it.options.map(id => new Set(BY_ID[id]?.allergens || []));
    for (const a of sets[0]) if (sets.every(s => s.has(a))) allergens.add(a);
  }
  const blockedRequired = (blocked) => required.some(it => it.options.every(id => blocked.includes(id)));
  return {
    ...r,
    ingredients,
    steps: r.steps.map(parseStep),
    diet,
    allergens: [...allergens],
    needsOnionGarlic: blockedRequired(ONION_GARLIC),
    jainOk: !blockedRequired(JAIN_BLOCKED),
    hasChilli: ingredients.some(it => it.options.some(id => ['green_chilli', 'red_chilli_powder', 'dry_red_chilli'].includes(id))),
  };
}

export const ALL_RECIPES = RECIPES.map(prepareRecipe);
export const RECIPE_BY_ID = Object.fromEntries(ALL_RECIPES.map(r => [r.id, r]));

// ---------------------------------------------------------- text -> ingredients
let ALIAS_LIST = buildAliases();
function buildAliases() {
  const list = [];
  for (const ing of INGREDIENTS) {
    const names = new Set([ing.id.replace(/_/g, ' '), ing.name.toLowerCase(), ...ing.aliases.map(a => a.toLowerCase())]);
    for (const n of names) list.push([normalize(n), ing.id]);
  }
  // Longest names first so "leftover rice" beats "rice" and "hari mirch" beats "mirch".
  return list.sort((a, b) => b[0].length - a[0].length);
}

export function normalize(s) {
  return String(s).toLowerCase()
    .replace(/\(.*?\)/g, ' ')
    .replace(/[^a-zऀ-ൿ\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

const FILLER = new Set(['and', 'some', 'a', 'an', 'the', 'few', 'of', 'little', 'bit', 'kg', 'g', 'gm', 'grams', 'packet', 'packets',
  'bunch', 'piece', 'pieces', 'cup', 'cups', 'i', 'have', 'got', 'in', 'my', 'fridge', 'aur', 'hai', 'kuch', 'thoda', 'with', 'also',
  'fresh', 'from', 'only', 'just', 'there', 'is', 'are', 'we', 'left', 'over', 'leftover', 'yesterday', 'today', 'for', 'what', 'can', 'cook', 'make']);

// Parse free text like "2 tamatar, pyaz and leftover chawal" into ingredient ids.
export function parseIngredients(text) {
  let rest = ' ' + normalize(text) + ' ';
  const found = [];
  for (const [alias, id] of ALIAS_LIST) {
    if (!alias) continue;
    const variants = [alias, alias + 's', alias + 'es'];
    for (const v of variants) {
      const needle = ' ' + v + ' ';
      if (rest.includes(needle)) {
        if (!found.includes(id)) found.push(id);
        rest = rest.split(needle).join(' | ');
      }
    }
  }
  const unknown = [...new Set(rest.split(/[|]/).flatMap(chunk => {
    const words = chunk.trim().split(' ').filter(w => w && !FILLER.has(w));
    return words.length ? [words.join(' ')] : [];
  }))];
  return { found, unknown };
}

// ------------------------------------------------------------------- pantry
export function defaultExpiry(id, now = Date.now()) {
  const d = BY_ID[id]?.shelfDays;
  return d ? now + d * DAY : null;
}

export function daysLeft(item, now = Date.now()) {
  if (!item.expiresAt) return null;
  return Math.ceil((item.expiresAt - now) / DAY);
}

export function useSoon(pantry, now = Date.now(), within = 2) {
  return pantry.filter(p => { const d = daysLeft(p, now); return d !== null && d <= within; })
    .sort((a, b) => a.expiresAt - b.expiresAt);
}

// ------------------------------------------------------------------ household
// member: { name, diet: 'veg'|'egg'|'nonveg', jain, noOnionGarlic, diabetic, fasting, allergies: [], spice: 1-3 }
export function householdCheck(recipe, members = []) {
  const notes = [];
  for (const m of members) {
    const who = m.name || 'Someone';
    if (DIET_RANK[recipe.diet] > DIET_RANK[m.diet || 'nonveg']) return { ok: false, reason: `${who} doesn't eat ${recipe.diet === 'egg' ? 'egg' : 'meat or fish'}` };
    const allergy = (m.allergies || []).find(a => recipe.allergens.includes(a));
    if (allergy) return { ok: false, reason: `${who} is allergic to ${allergy}` };
    if (m.jain && !recipe.jainOk) return { ok: false, reason: `Not Jain-friendly (for ${who})` };
    if (m.noOnionGarlic && recipe.needsOnionGarlic) return { ok: false, reason: `${who} avoids onion and garlic` };
    if (m.diabetic && recipe.tags.includes('sweet')) return { ok: false, reason: `Sweet dish (${who} is diabetic)` };
    if (m.fasting && !recipe.tags.includes('vrat')) return { ok: false, reason: `${who} is fasting today` };
    if (m.goals?.includes('pregnancy') && recipe.time <= 15 && recipe.ingredients.some(it => !it.optional && it.options.includes('sprouts'))) return { ok: false, reason: `Raw or lightly cooked sprouts aren't advised for ${who} during pregnancy` };
    // Things we can work around: give a tip instead of hiding the dish.
    const optAllergen = (m.allergies || []).find(a => recipe.ingredients.some(it => it.optional && it.options.some(id => BY_ID[id]?.allergens.includes(a))));
    if (optAllergen) notes.push(`Skip the optional ${optAllergen} items for ${who}.`);
    if (m.jain) notes.push(`For ${who}: skip onion, garlic, ginger and root vegetables.`);
    else if (m.noOnionGarlic && recipe.ingredients.some(it => it.optional && it.options.some(id => ONION_GARLIC.includes(id)))) notes.push(`Skip onion and garlic for ${who}.`);
    if (m.spice && m.spice < recipe.spice && recipe.hasChilli) notes.push(`Take out a mild portion for ${who} before adding chilli.`);
  }
  return { ok: true, notes: [...new Set(notes)] };
}

// ------------------------------------------------------------------ matching
// Flavourings: nice to have, but a cook can manage without one.
export const FLAVOURINGS = ['green_chilli', 'coriander', 'curry_leaves', 'ginger', 'garlic', 'lemon'];
const isSpice = id => BY_ID[id]?.category === 'Spices' || FLAVOURINGS.includes(id);

export function matchRecipe(recipe, pantryIds, { soonIds = [] } = {}) {
  const have = new Set([...pantryIds, ...ASSUMED]);
  const required = recipe.ingredients.filter(i => !i.optional);
  const missing = required.filter(it => !it.options.some(id => have.has(id)));
  // A missing masala is a smaller problem than a missing main ingredient.
  const spiceMissing = missing.filter(it => it.options.every(isSpice));
  const majorMissing = missing.filter(it => !it.options.every(isSpice));
  const major = required.filter(it => !it.options.every(isSpice));
  const usesSoon = soonIds.filter(id => recipe.ingredients.some(it => it.options.includes(id)));
  const optionalHave = recipe.ingredients.filter(i => i.optional && i.options.some(id => have.has(id))).length;
  // How many of the user's own (non-masala) items this dish uses up.
  const used = pantryIds.filter(id => !isSpice(id) && recipe.ingredients.some(it => it.options.includes(id))).length;
  return {
    used,
    total: required.length,
    haveCount: required.length - missing.length,
    majorTotal: major.length,
    majorHave: major.length - majorMissing.length,
    missing: missing.map(it => it.options),
    majorMissing: majorMissing.map(it => it.options),
    spiceMissing: spiceMissing.map(it => it.options),
    usesSoon,
    optionalHave,
  };
}

// The live recipe book: built-in dishes, with admin edits replacing them by id and hidden ones removed.
export function recipesFrom(extraRecipes = [], hidden = []) {
  const replaced = new Set(extraRecipes.map(r => r.id));
  const gone = new Set(hidden);
  return [...ALL_RECIPES.filter(r => !replaced.has(r.id)), ...extraRecipes].filter(r => !gone.has(r.id));
}

// ratings: { [recipeId]: number 1-5 }
export function suggest({ pantry = [], members = [], filters = {}, ratings = {}, now = Date.now(), extraRecipes = [], hidden = [] } = {}) {
  const pantryIds = pantry.map(p => p.id);
  const soonIds = useSoon(pantry, now).map(p => p.id);
  const results = [];
  for (const recipe of recipesFrom(extraRecipes, hidden)) {
    if (filters.veg && recipe.diet !== 'veg') continue;
    if (filters.quick && recipe.time > 20) continue;
    if (filters.leftover && !recipe.tags.includes('leftover')) continue;
    if (filters.vrat && !recipe.tags.includes('vrat')) continue;
    if (filters.healthy && !recipe.tags.includes('diabetic-friendly')) continue;
    if (filters.meal && !recipe.meal.includes(filters.meal)) continue;
    const house = householdCheck(recipe, members);
    if (!house.ok) continue;
    const m = matchRecipe(recipe, pantryIds, { soonIds });
    if (m.majorHave === 0) continue;
    const coverage = m.majorHave / Math.max(1, m.majorTotal);
    const rating = ratings[recipe.id];
    const score = coverage * 100 - m.majorMissing.length * 12 - m.spiceMissing.length * 3 + m.usesSoon.length * 15 + m.optionalHave * 2 + m.used * 5
      + (rating ? (rating - 3) * 6 : 0);
    results.push({ recipe, ...m, coverage, score, notes: house.notes });
  }
  results.sort((a, b) => b.score - a.score || a.recipe.time - b.recipe.time);
  return {
    ready: results.filter(r => r.missing.length === 0),
    almost: results.filter(r => r.missing.length > 0 && r.majorMissing.length <= 2),
  };
}

// "Buy just one thing" tips: which single missing ingredient unlocks the most new dishes.
export function buyTips(params, limit = 3) {
  const { almost } = suggest(params);
  const counts = {};
  for (const r of almost) {
    if (r.majorMissing.length !== 1) continue;
    const id = r.majorMissing[0][0];
    (counts[id] ||= []).push(r.recipe.name);
  }
  return Object.entries(counts)
    .map(([id, dishes]) => ({ id, name: BY_ID[id]?.name || id, dishes }))
    .sort((a, b) => b.dishes.length - a.dishes.length)
    .slice(0, limit);
}

// ------------------------------------------------------------------- rescue
const STOP = new Set(['too', 'much', 'the', 'and', 'got', 'has', 'have', 'its', 'very', 'bit', 'my', 'is', 'it', 'or', 'gaya', 'hai', 'ho']);

export function findRescue(text) {
  const words = normalize(text).split(' ').filter(w => w.length > 2 && !STOP.has(w));
  if (!words.length) return RESCUES;
  return RESCUES
    .map(r => {
      const keys = (r.title + ' ' + r.keywords).toLowerCase().split(/[^a-z]+/).filter(k => k.length > 2 && !STOP.has(k));
      const score = words.filter(w => keys.some(k => k.startsWith(w) || w.startsWith(k))).length;
      return { r, score };
    })
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .map(x => x.r);
}

// ------------------------------------------------------------------- sharing
export function shoppingText(items) {
  return 'Ballava shopping list:\n' + items.map(i => `- ${BY_ID[i]?.name || i}`).join('\n');
}

export function recipeText(recipe) {
  const ing = recipe.ingredients.map(it => `- ${it.options.map(id => BY_ID[id]?.name || id).join(' / ')}${it.qty ? ': ' + it.qty : ''}${it.optional ? ' (optional)' : ''}`);
  const steps = recipe.steps.map((s, i) => `${i + 1}. ${s.text}`);
  return `${recipe.name} (${recipe.time} min)\n\nIngredients:\n${ing.join('\n')}\n\nSteps:\n${steps.join('\n')}\n\nShared from Ballava`;
}

// A short, WhatsApp-style reply: the same brain a chat bot would use.
export function chatReply(text, opts = {}) {
  const { found, unknown } = parseIngredients(text);
  if (!found.length) return { found, unknown, reply: 'Tell me what you have, for example: "rice, 2 tomatoes, onion, curd". I\'ll suggest what to cook.' };
  const pantry = found.map(id => ({ id }));
  const { ready, almost } = suggest({ pantry, ...opts });
  const pick = [...ready, ...almost].slice(0, 3);
  if (!pick.length) return { found, unknown, reply: 'I couldn\'t find a dish with just that. Add a few more items, like onion, tomato or rice.' };
  const lines = pick.map((r, i) => `${i + 1}. ${r.recipe.name} (${r.recipe.time} min)` + (r.majorMissing.length ? `, needs ${r.majorMissing.map(o => BY_ID[o[0]]?.name || o[0]).join(', ')}` : r.spiceMissing.length ? ', you have the main items' : ', you have everything'));
  return { found, unknown, dishes: pick.map(r => r.recipe.id), reply: `With ${found.map(id => BY_ID[id].name).join(', ')} you can make:\n${lines.join('\n')}\n(I assume you have salt, oil and basic masalas.)` };
}

// Validate a recipe that came from the AI so it can be shown like any other.
export function normalizeAiRecipe(raw) {
  if (!raw || typeof raw !== 'object') throw new Error('AI returned no recipe');
  const name = String(raw.name || '').slice(0, 80);
  if (!name) throw new Error('AI recipe has no name');
  const ing = (Array.isArray(raw.ingredients) ? raw.ingredients : []).slice(0, 25).map(x => {
    const label = typeof x === 'string' ? x : `${x.name || ''}`;
    const { found } = parseIngredients(label);
    const id = found[0] || null;
    const qty = typeof x === 'string' ? '' : String(x.quantity || x.qty || '');
    return { options: [id || label.toLowerCase().slice(0, 40)], qty, optional: !!(x && x.optional), custom: !id ? label : undefined };
  });
  const steps = (Array.isArray(raw.steps) ? raw.steps : []).slice(0, 15).map(s => {
    if (typeof s === 'string') return parseStep(s);
    return { text: String(s.text || ''), ...(s.minutes ? { minutes: Math.min(240, Number(s.minutes)) } : {}) };
  }).filter(s => s.text);
  if (!ing.length || !steps.length) throw new Error('AI recipe is incomplete');
  const base = {
    id: 'ai_' + Math.abs([...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)).toString(36),
    name, alt: raw.alt ? String(raw.alt).slice(0, 60) : undefined, cuisine: String(raw.cuisine || 'Ballava original').slice(0, 40),
    meal: ['lunch', 'dinner'], time: Math.max(5, Math.min(240, Number(raw.time) || 30)), serves: Number(raw.serves) || 2,
    spice: [1, 2, 3].includes(Number(raw.spice)) ? Number(raw.spice) : 2, tags: ['ai'],
    tip: raw.why ? String(raw.why).slice(0, 400) : undefined,
    safety: raw.safety ? String(raw.safety).slice(0, 400) : undefined,
  };
  const prepared = { ...base, ingredients: ing, steps, ai: true };
  const required = ing.filter(i => !i.optional);
  let diet = 'veg';
  for (const it of required) { const d = BY_ID[it.options[0]]?.diet; if (d && DIET_RANK[d] > DIET_RANK[diet]) diet = d; }
  prepared.diet = diet;
  prepared.allergens = [...new Set(required.flatMap(it => BY_ID[it.options[0]]?.allergens || []))];
  prepared.needsOnionGarlic = required.some(it => ONION_GARLIC.includes(it.options[0]));
  prepared.jainOk = !required.some(it => JAIN_BLOCKED.includes(it.options[0]));
  prepared.hasChilli = ing.some(it => ['green_chilli', 'red_chilli_powder', 'dry_red_chilli'].includes(it.options[0]));
  return prepared;
}

// ------------------------------------------------------------------- admin content
const BUILTIN_INGREDIENTS = INGREDIENTS.length;
const BUILTIN_RESCUES = RESCUES.length;

// Add what admins published (new ingredients and Bachao fixes) to the built-in catalog.
export function applyCatalog({ ingredients = [], rescues = [] } = {}) {
  for (const old of INGREDIENTS.splice(BUILTIN_INGREDIENTS)) delete BY_ID[old.id];
  for (const raw of ingredients) {
    if (BY_ID[raw.id]) continue;
    const item = { allergens: [], diet: 'veg', aliases: [], shelfDays: null, ...raw };
    INGREDIENTS.push(item); BY_ID[item.id] = item;
  }
  ALIAS_LIST = buildAliases();
  RESCUES.splice(BUILTIN_RESCUES);
  RESCUES.push(...rescues);
}

// The checks every recipe must pass before it can be published. Returns a list of problems.
export function validateRecipe(raw) {
  const errors = [];
  if (!raw || typeof raw !== 'object') return ['Recipe is empty'];
  if (!/^[a-z0-9_]{2,40}$/.test(raw.id || '')) errors.push('Id must be 2-40 lowercase letters, numbers or underscores');
  if (!String(raw.name || '').trim()) errors.push('Name is required');
  if (!(Number(raw.time) > 0)) errors.push('Time must be more than 0 minutes');
  if (!(Number(raw.serves) > 0)) errors.push('Serves must be more than 0');
  if (![1, 2, 3].includes(Number(raw.spice))) errors.push('Spice must be 1, 2 or 3');
  if (!Array.isArray(raw.meal) || !raw.meal.length) errors.push('Choose at least one meal type');
  if (!Array.isArray(raw.ing) || !raw.ing.length) errors.push('Add at least one ingredient');
  if (!Array.isArray(raw.steps) || raw.steps.length < 2) errors.push('Add at least two steps');
  if (errors.length) return errors;
  for (const line of raw.ing) for (const id of parseIngredientLine(line).options) if (!BY_ID[id]) errors.push(`Unknown ingredient "${id}"`);
  if (errors.length) return errors;
  const r = prepareRecipe({ tags: [], ...raw });
  if (!r.ingredients.some(i => !i.optional)) errors.push('At least one ingredient must be required');
  if (r.steps.some(st => st.text.length <= 5)) errors.push('One of the steps is too short');
  const tags = r.tags;
  if (tags.includes('jain') && !r.jainOk) errors.push('Tagged jain but needs onion, garlic or root vegetables');
  if (tags.includes('vrat') && r.needsOnionGarlic) errors.push('Tagged vrat but needs onion or garlic');
  if (tags.includes('gluten-free') && r.allergens.includes('gluten')) errors.push('Tagged gluten-free but contains gluten');
  if (tags.includes('diabetic-friendly') && tags.includes('sweet')) errors.push('A sweet dish cannot be tagged diabetic-friendly');
  if (r.diet === 'nonveg' && !r.safety) errors.push('Meat and fish dishes need a food-safety note');
  return errors;
}
