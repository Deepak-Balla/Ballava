// Ballava planner: decides what to cook, day after day.
// Pure functions only, so the same logic runs in the app, on the server and in the tests.
// Log entries look like { recipeId, name, date: 'YYYY-MM-DD', slot, rating }.
import { BY_ID, ASSUMED } from './ingredients.mjs';
import { ALL_RECIPES, RECIPE_BY_ID, FLAVOURINGS, householdCheck, matchRecipe, useSoon, recipesFrom, parseIngredients, suggest } from './engine.mjs';

export const SLOTS = ['breakfast', 'lunch', 'dinner'];
export const SLOT_LABEL = { breakfast: 'Breakfast', lunch: 'Lunch', dinner: 'Dinner', snack: 'Snack' };
export const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// Health goals a family member can have. These only nudge the ranking; they are not medical advice.
export const GOALS = [['bp', 'Low salt (BP)'], ['weight', 'Weight care'], ['pcos', 'PCOS'], ['pregnancy', 'Pregnant']];
export const AGE_GROUPS = [['toddler', 'Toddler (1-3)'], ['child', 'Child (4-12)'], ['teen', 'Teen'], ['adult', 'Adult'], ['senior', 'Senior']];

// ------------------------------------------------------------------- dates
export const dayKey = (t = Date.now()) => {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const noon = key => new Date(key + 'T12:00:00');
export const addDays = (key, n) => { const d = noon(key); d.setDate(d.getDate() + n); return dayKey(d.getTime()); };
export const daysBetween = (a, b) => Math.round((noon(b) - noon(a)) / 86400000);
export const weekdayOf = key => noon(key).getDay();
export function slotNow(t = Date.now()) {
  const h = new Date(t).getHours();
  return h < 11 ? 'breakfast' : h < 16 ? 'lunch' : 'dinner';
}

// Older history entries only have a timestamp, so fill in the day and meal.
export function normalizeLog(history = []) {
  return history.map(h => ({ ...h, date: h.date || dayKey(h.at), slot: h.slot || slotNow(h.at) }));
}

// ---------------------------------------------------- what is in a dish
const AROMATICS = new Set(['onion', 'tomato', 'garlic', 'ginger', ...FLAVOURINGS]);
const NOT_PROTEIN = new Set(['peanuts', 'cashew']);
const GREENS = new Set(['spinach', 'methi']);
const WHOLE_GRAINS = new Set(['atta', 'oats', 'ragi', 'jowar', 'bajra', 'kuttu', 'samak', 'leftover_roti']);
const NOT_VEG = new Set([...AROMATICS, 'potato', 'sweet_potato', 'sweet_corn']);
const BASES = {
  rice: ['rice', 'leftover_rice', 'dosa_batter', 'poha'],
  wheat: ['atta', 'maida', 'bread', 'sooji', 'noodles', 'pasta', 'vermicelli', 'leftover_roti'],
  millet: ['ragi', 'jowar', 'bajra'],
};

const lookup = (id, extra) => extra?.[id] || RECIPE_BY_ID[id];
const required = r => r.ingredients.filter(i => !i.optional);

// The ingredients a dish is "about" (no masalas, onion, tomato and so on).
export function mainsOf(recipe) {
  const out = new Set();
  for (const it of required(recipe)) {
    const id = it.options[0], cat = BY_ID[id]?.category;
    if (!cat || AROMATICS.has(id) || cat === 'Spices' || cat === 'Basics & Sauces') continue;
    out.add(id);
  }
  return [...out];
}

export function baseOf(recipe) {
  for (const [base, ids] of Object.entries(BASES)) if (recipe.ingredients.some(it => !it.optional && it.options.some(id => ids.includes(id)))) return base;
  return null;
}

// Food groups for the dashboard. A dish counts when it really contains the group.
export function groupsOf(recipe) {
  const ids = recipe.ingredients.filter(i => !i.optional).flatMap(i => i.options);
  const has = fn => ids.some(fn);
  const cat = id => BY_ID[id]?.category;
  const groups = [];
  if (has(id => GREENS.has(id))) groups.push('greens');
  if (has(id => cat(id) === 'Vegetables' && !NOT_VEG.has(id) && !GREENS.has(id))) groups.push('vegetables');
  if (has(id => (cat(id) === 'Dals & Beans' && !NOT_PROTEIN.has(id)) || cat(id) === 'Meat & Fish' || ['egg', 'paneer', 'leftover_dal', 'besan'].includes(id))) groups.push('protein');
  if (has(id => WHOLE_GRAINS.has(id))) groups.push('wholegrain');
  if (has(id => cat(id) === 'Fruits')) groups.push('fruit');
  return groups;
}

// ---------------------------------------------------- no-repeat scoring
const niceList = ids => ids.map(id => (BY_ID[id]?.name || id).toLowerCase()).join(' and ');

// How much to push a dish down because of what was eaten around `date`.
export function repeatCheck(recipe, log, { date = dayKey(), pins = [], extra } = {}) {
  let penalty = 0;
  const reasons = [];
  const pinned = pins.some(p => p.recipeId === recipe.id);
  const mains = mainsOf(recipe), base = baseOf(recipe);
  let mainHit = 0, baseHit = 0, lastDays = null;
  for (const e of log) {
    const gap = Math.abs(daysBetween(e.date, date));
    if (gap > 13) continue;
    if (e.recipeId === recipe.id) {
      if (lastDays === null || gap < lastDays) lastDays = gap;
      continue;
    }
    const other = lookup(e.recipeId, extra);
    if (!other || gap > 2) continue;
    const shared = mainsOf(other).filter(m => mains.includes(m));
    if (shared.length) { mainHit += gap <= 1 ? 16 : 8; if (gap <= 1 && !reasons.length) reasons.push(`Had ${niceList(shared)} ${gap === 0 ? 'today' : 'recently'}`); }
    if (gap === 0 && base && baseOf(other) === base) baseHit += 10;
  }
  if (lastDays !== null && !pinned) {
    penalty += lastDays <= 2 ? 90 : lastDays <= 6 ? 55 : 20;
    reasons.unshift(lastDays === 0 ? 'Already on the menu today' : `Made ${lastDays} day${lastDays > 1 ? 's' : ''} ago`);
  }
  penalty += Math.min(mainHit, 32) + Math.min(baseHit, 20);
  return { penalty, reasons, lastDays };
}

// ---------------------------------------------------- family diet
const SALTY = ['soy_sauce', 'noodles', 'tomato_ketchup', 'chaat_masala', 'cheese'];

export function goalScore(recipe, members = []) {
  let bonus = 0;
  const why = [];
  const tag = t => recipe.tags.includes(t);
  const uses = id => recipe.ingredients.some(it => !it.optional && it.options.includes(id));
  const groups = groupsOf(recipe);
  const note = t => { if (!why.includes(t)) why.push(t); };
  for (const m of members) {
    const goals = m.goals || [];
    const who = m.name || 'someone';
    if (m.diabetic && tag('diabetic-friendly')) { bonus += 10; note(`Good for ${who}'s sugar`); }
    if (goals.includes('bp') && SALTY.some(uses)) bonus -= 14;
    if (goals.includes('weight')) {
      if (tag('high-protein')) { bonus += 6; note(`Filling and light for ${who}`); }
      if (tag('sweet')) bonus -= 15;
    }
    if (goals.includes('pcos') && (tag('diabetic-friendly') || tag('high-protein'))) { bonus += 6; note(`Balanced for ${who}`); }
    if (goals.includes('pregnancy')) {
      if (tag('high-protein') || groups.includes('greens')) { bonus += 6; note(`Protein and iron for ${who}`); }
    }
    if (['toddler', 'child'].includes(m.age) && tag('kid-friendly')) { bonus += 8; note(`${who} will like this`); }
    if ((m.likes || []).some(uses)) { bonus += 6; note(`${who} loves this`); }
    if ((m.dislikes || []).some(uses)) bonus -= 22;
  }
  return { bonus, why };
}

// "One meal, many plates": small changes so one pot works for everyone.
export function platesFor(recipe, members = []) {
  const plates = [];
  const add = (who, text) => {
    const row = plates.find(p => p.who === who);
    if (row) { if (!row.tips.includes(text)) row.tips.push(text); } else plates.push({ who, tips: [text] });
  };
  const uses = (ids, optional) => recipe.ingredients.some(it => (optional === undefined || it.optional === optional) && it.options.some(id => ids.includes(id)));
  const base = baseOf(recipe);
  for (const m of members) {
    const who = m.name || 'Someone';
    const goals = m.goals || [];
    if (m.spice && m.spice < recipe.spice && recipe.hasChilli) add(who, 'Take out their portion before adding chilli.');
    if (m.age === 'toddler') {
      add(who, 'Take out their portion before salt and chilli go in, and mash it well.');
      if (uses(['peanuts', 'cashew'])) add(who, 'Leave out whole nuts, as they can cause choking.');
    }
    if (m.age === 'senior' && recipe.time > 0 && uses(['rice', 'leftover_rice', 'toor_dal', 'moong_dal', 'chana_dal'])) add(who, 'Cook their portion a little softer if chewing is hard.');
    if (goals.includes('bp')) add(who, 'Salt their portion lightly and add lemon for flavour instead.');
    if (m.diabetic && (base === 'rice' || base === 'wheat')) add(who, 'Serve a smaller portion of rice or roti, with more dal and sabzi.');
    if (goals.includes('weight') && uses(['ghee', 'butter', 'cream'])) add(who, 'Use less ghee, butter or cream on their plate.');
    if (goals.includes('pregnancy') && recipe.diet !== 'veg') add(who, 'Make sure meat, fish and eggs are fully cooked.');
    for (const id of m.dislikes || []) if (uses([id], true)) add(who, `Leave out ${BY_ID[id]?.name.toLowerCase() || id} from their portion.`);
    const optAllergen = (m.allergies || []).find(a => recipe.ingredients.some(it => it.optional && it.options.some(id => BY_ID[id]?.allergens.includes(a))));
    if (optAllergen) add(who, `Skip the optional ${optAllergen} items, they are allergic.`);
  }
  return plates;
}

// ---------------------------------------------------- recommendations
function hash(s) { let h = 7; for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0; return Math.abs(h); }

const fitsSlot = (r, slot) => {
  if (slot === 'tiffin') return r.tags.includes('tiffin') || TIFFIN_IDS.has(r.id);
  return r.meal.includes(slot) && !r.meal.includes('side');
};

// Existing dishes that pack well. Leftover-rice dishes are kept out on purpose: a lunchbox sits warm for hours.
export const TIFFIN_IDS = new Set(['kanda_poha', 'rava_upma', 'besan_chilla', 'aloo_paratha', 'veg_pulao', 'veg_fried_rice', 'hakka_noodles', 'masala_pasta',
  'veg_sandwich', 'idli', 'jeera_aloo']);

// Best dishes for one meal on one day. Unlike suggest(), this also considers dishes you'd need to shop for.
export function recommend({ pantry = [], members = [], ratings = {}, log = [], pins = [], filters = {}, slot, date = dayKey(), now = Date.now(),
  extraRecipes = [], hidden = [], extra, onlyVrat = false, fastingApplies = true } = {}) {
  const pantryIds = pantry.map(p => p.id);
  const soonIds = useSoon(pantry, now).map(p => p.id);
  const diners = fastingApplies ? members : members.map(m => ({ ...m, fasting: false }));
  const weekday = weekdayOf(date);
  const out = [];
  for (const recipe of recipesFrom(extraRecipes, hidden)) {
    if (slot && !fitsSlot(recipe, slot)) continue;
    if (onlyVrat && !recipe.tags.includes('vrat')) continue;
    if (filters.veg && recipe.diet !== 'veg') continue;
    if (filters.quick && recipe.time > 20) continue;
    if (filters.healthy && !recipe.tags.includes('diabetic-friendly')) continue;
    const house = householdCheck(recipe, diners);
    if (!house.ok) continue;
    const m = matchRecipe(recipe, pantryIds, { soonIds });
    const coverage = m.majorHave / Math.max(1, m.majorTotal);
    const rep = repeatCheck(recipe, log, { date, pins, extra });
    const goal = goalScore(recipe, diners);
    const pin = pins.find(p => p.recipeId === recipe.id && p.weekday === weekday && (!slot || !p.slot || p.slot === slot));
    const rating = ratings[recipe.id];
    const score = coverage * 60 - m.majorMissing.length * 8 + m.usesSoon.length * 15 + m.optionalHave + (rating ? (rating - 3) * 6 : 0)
      + goal.bonus - rep.penalty + (hash(date + recipe.id) % 9) + (pin ? 200 : 0);
    const why = [];
    if (pin) why.push(`Your ${WEEKDAYS[weekday]} favourite`);
    if (m.usesSoon.length) why.push(`Uses up ${niceList(m.usesSoon)}`);
    why.push(...goal.why);
    if (rating >= 4) why.push('Your family rated this highly');
    if (!m.majorMissing.length) why.push('You have everything');
    out.push({ recipe, ...m, coverage, score, why: why.slice(0, 3), repeat: rep, notes: house.notes });
  }
  return out.sort((a, b) => b.score - a.score || a.recipe.time - b.recipe.time);
}

// Who is fasting on a day: weekly habits plus any festival the family observes.
export function fastersOn(date, members = [], festivals = [], observed = []) {
  const names = members.filter(m => (m.fastWeekdays || []).includes(weekdayOf(date))).map(m => m.name);
  const fest = festivals.find(f => f.date === date && f.fast && observed.includes(f.id));
  return { names, festival: fest || null };
}

// Build a plan: { 'YYYY-MM-DD': { breakfast, lunch, dinner, tiffins: {name: id}, fast: {name: id}, locked: [slot] } }.
// Anything the family has locked is kept, and never overwritten.
export function planWeek({ start = dayKey(), days = 7, existing = {}, log = [], festivals = [], observed = [], members = [], ...rest } = {}) {
  const plan = {};
  const sim = [...log];
  const remember = (recipeId, date, slot) => sim.push({ recipeId, date, slot });
  for (const [date, day] of Object.entries(existing)) for (const s of SLOTS) if (day[s]) remember(day[s], date, s);
  for (let i = 0; i < days; i++) {
    const date = addDays(start, i);
    const old = existing[date] || {};
    const locked = old.locked || [];
    const day = { locked, tiffins: {}, fast: {} };
    for (const slot of SLOTS) {
      if (locked.includes(slot) && old[slot]) { day[slot] = old[slot]; continue; }
      const dayLog = sim.filter(e => !(e.date === date && e.slot === slot));
      const best = recommend({ ...rest, members, slot, date, log: dayLog, fastingApplies: false })[0];
      day[slot] = best ? best.recipe.id : null;
      if (best) remember(best.recipe.id, date, slot);
    }
    // School days: a separate, non-repeating lunchbox for each child who takes one.
    const wd = weekdayOf(date);
    if (wd >= 1 && wd <= 5) {
      for (const kid of members.filter(m => m.tiffin)) {
        const tiffinLog = sim.filter(e => e.slot === 'tiffin:' + kid.name).map(e => ({ ...e, slot: 'tiffin' }));
        const pick = recommend({ ...rest, members: [{ ...kid, fasting: false }], slot: 'tiffin', date, log: tiffinLog, fastingApplies: false })[0];
        if (pick) { day.tiffins[kid.name] = pick.recipe.id; remember(pick.recipe.id, date, 'tiffin:' + kid.name); }
      }
    }
    // Fasting: a separate vrat meal, so the rest of the family still eats normally.
    const { names, festival } = fastersOn(date, members, festivals, observed);
    const fasters = festival ? ['Family'] : names;
    for (const who of fasters) {
      const pool = who === 'Family' ? members : members.filter(m => m.name === who);
      const vrat = recommend({ ...rest, members: pool, slot: 'lunch', date, log: sim, onlyVrat: true, fastingApplies: false })[0];
      if (vrat) { day.fast[who] = vrat.recipe.id; remember(vrat.recipe.id, date, 'fast'); }
    }
    if (festival) day.festival = festival.name;
    plan[date] = day;
  }
  return plan;
}

export function dayRecipeIds(day = {}) {
  return [...SLOTS.map(s => day[s]), ...Object.values(day.tiffins || {}), ...Object.values(day.fast || {})].filter(Boolean);
}

// ---------------------------------------------------- prep and leftovers
// What must be done the night before, so tomorrow's meals actually happen.
export function prepFor(recipe) {
  if (recipe.prep) return recipe.prep;
  const uses = id => recipe.ingredients.some(it => !it.optional && it.options.includes(id));
  if (uses('dosa_batter')) return 'Check you have batter. Fresh batter needs 8-12 hours to ferment.';
  if (['chicken', 'mutton', 'fish', 'prawns'].some(uses)) return 'If it is frozen, move it to the fridge tonight.';
  if (uses('chickpeas')) return 'If using dry chana, soak it tonight.';
  return null;
}

export function prepTonight(plan, date = dayKey(), extra) {
  const tomorrow = plan?.[addDays(date, 1)];
  if (!tomorrow) return [];
  const seen = new Set();
  const out = [];
  for (const id of dayRecipeIds(tomorrow)) {
    const r = lookup(id, extra);
    const text = r && prepFor(r);
    if (text && !seen.has(id)) { seen.add(id); out.push({ recipeId: id, name: r.name, text }); }
  }
  return out;
}

// After cooking: what could be left over, and what it can turn into tomorrow.
const CHAINS = [
  ['leftover_rice', r => baseOf(r) === 'rice' && r.ingredients.some(i => i.options.includes('rice')), ['lemon_rice', 'curd_rice', 'tomato_rice']],
  ['leftover_dal', r => r.ingredients.some(i => !i.optional && i.options.some(id => ['toor_dal', 'moong_dal', 'masoor_dal'].includes(id))), ['dal_paratha']],
  ['leftover_roti', r => r.ingredients.some(i => !i.optional && i.options.includes('atta')), ['chapati_upma']],
  ['leftover_sabzi', r => (r.meal.includes('lunch') || r.meal.includes('dinner')) && groupsOf(r).includes('vegetables'), ['veg_cutlet']],
];

export function leftoverChains(recipe) {
  return CHAINS.filter(([, test]) => test(recipe)).map(([item, , ideas]) => ({
    item, name: BY_ID[item].name, ideas: ideas.map(id => RECIPE_BY_ID[id]?.name).filter(Boolean),
  }));
}

// ---------------------------------------------------- groceries
// Everything the plan needs that is not in the kitchen, with the dishes that need it.
export function planGroceries(plan, { from = dayKey(), days = 7, pantry = [], extra } = {}) {
  const have = new Set([...pantry.map(p => p.id), ...ASSUMED]);
  const need = new Map();
  for (let i = 0; i < days; i++) {
    for (const id of dayRecipeIds(plan?.[addDays(from, i)])) {
      const r = lookup(id, extra);
      if (!r) continue;
      for (const it of required(r)) {
        if (it.options.some(o => have.has(o))) continue;
        const key = it.options[0];
        if (!need.has(key)) need.set(key, new Set());
        need.get(key).add(r.name);
      }
    }
  }
  return [...need].map(([id, dishes]) => ({ id, name: BY_ID[id]?.name || id, category: BY_ID[id]?.category || 'Other', dishes: [...dishes] }))
    .sort((a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name));
}

// ---------------------------------------------------- dashboard
const GROUP_TEXT = { greens: 'leafy greens', vegetables: 'vegetables', protein: 'protein', wholegrain: 'whole grains', fruit: 'fruit' };

export function dashboard(history = [], { now = Date.now(), days = 7, extra } = {}) {
  const log = normalizeLog(history);
  const today = dayKey(now);
  const inRange = e => { const g = daysBetween(e.date, today); return g >= 0 && g < days; };
  const recent = log.filter(inRange);
  const known = e => (e.recipeId ? lookup(e.recipeId, extra) : null);

  const groups = Object.fromEntries(Object.keys(GROUP_TEXT).map(g => [g, 0]));
  const lastGroup = {};
  for (const e of log) {
    const r = known(e);
    if (!r) continue;
    for (const g of groupsOf(r)) {
      if (inRange(e)) groups[g] += 1;
      const gap = daysBetween(e.date, today);
      if (gap >= 0 && (lastGroup[g] === undefined || gap < lastGroup[g])) lastGroup[g] = gap;
    }
  }

  const counts = new Map();
  for (const e of log) {
    const key = e.recipeId || e.name;
    const row = counts.get(key) || { id: e.recipeId, name: e.name, count: 0, last: e.date, rating: null };
    row.count += 1;
    if (e.date > row.last) row.last = e.date;
    if (e.rating) row.rating = e.rating;
    counts.set(key, row);
  }
  const all = [...counts.values()];
  const recentNames = new Set(recent.map(e => e.recipeId || e.name));
  const variety = recent.length ? Math.round((recentNames.size / recent.length) * 100) : null;
  const repeats = [...recentNames].map(k => ({ ...counts.get(k), week: recent.filter(e => (e.recipeId || e.name) === k).length }))
    .filter(r => r.week >= 3).sort((a, b) => b.week - a.week);
  const missed = all.filter(r => r.id && (r.rating >= 4 || r.count >= 3) && daysBetween(r.last, today) >= 21)
    .sort((a, b) => (b.rating || 0) - (a.rating || 0) || a.last.localeCompare(b.last));

  // Friendly, useful nudges. Only say something when there is enough history to be fair.
  const insights = [];
  if (log.length >= 3) {
    for (const g of ['greens', 'vegetables', 'protein']) {
      const gap = lastGroup[g];
      if (gap === undefined) insights.push({ kind: 'tip', text: `No ${GROUP_TEXT[g]} logged yet. Want to add some this week?`, group: g });
      else if (gap >= 4) insights.push({ kind: 'tip', text: `No ${GROUP_TEXT[g]} in ${gap} days. Want to add some tomorrow?`, group: g });
    }
    for (const r of repeats.slice(0, 1)) insights.push({ kind: 'tip', text: `${r.name} was made ${r.week} times this week. Time for a change?` });
    for (const r of missed.slice(0, 2)) insights.push({ kind: 'idea', text: `You haven't made ${r.name} in ${daysBetween(r.last, today)} days. It was a family favourite.`, recipeId: r.id });
    if (variety !== null && variety >= 80 && recent.length >= 5) insights.push({ kind: 'good', text: `Lovely variety! ${recentNames.size} different dishes this week.` });
    if (groups.greens + groups.vegetables >= 4) insights.push({ kind: 'good', text: 'Plenty of vegetables on the table this week.' });
  }

  const byDay = {};
  for (const e of log) (byDay[e.date] ||= []).push(e);
  return {
    total: log.length, weekCount: recent.length, variety, groups, lastGroup, insights, byDay,
    top: all.sort((a, b) => b.count - a.count).slice(0, 5),
    saved: log.reduce((n, h) => n + (h.saved?.length || 0), 0),
    repeats, missed,
  };
}

// ---------------------------------------------------- sharing with a house cook
const MENU_WORDS = {
  en: { hello: 'Today\'s menu', breakfast: 'Breakfast', lunch: 'Lunch', dinner: 'Dinner', note: 'Special portions' },
  hi: { hello: 'आज का मेन्यू', breakfast: 'नाश्ता', lunch: 'दोपहर का खाना', dinner: 'रात का खाना', note: 'खास ध्यान दें' },
  te: { hello: 'ఈ రోజు మెనూ', breakfast: 'అల్పాహారం', lunch: 'మధ్యాహ్న భోజనం', dinner: 'రాత్రి భోజనం', note: 'ప్రత్యేక గమనిక' },
  ta: { hello: 'இன்றைய மெனு', breakfast: 'காலை உணவு', lunch: 'மதிய உணவு', dinner: 'இரவு உணவு', note: 'சிறப்பு குறிப்பு' },
};

export function menuMessage(day, { lang = 'en', members = [], extra } = {}) {
  const w = MENU_WORDS[lang] || MENU_WORDS.en;
  const lines = [w.hello + ':'];
  const notes = [];
  for (const s of SLOTS) {
    const r = day?.[s] && lookup(day[s], extra);
    if (!r) continue;
    lines.push(`${w[s]}: ${r.name}`);
    for (const p of platesFor(r, members)) notes.push(`${p.who} (${r.name}): ${p.tips.join(' ')}`);
  }
  for (const [who, id] of Object.entries(day?.tiffins || {})) { const r = lookup(id, extra); if (r) lines.push(`Tiffin, ${who}: ${r.name}`); }
  for (const [who, id] of Object.entries(day?.fast || {})) { const r = lookup(id, extra); if (r) lines.push(`Vrat, ${who}: ${r.name}`); }
  if (notes.length) lines.push('', w.note + ':', ...notes.slice(0, 6));
  return lines.join('\n');
}

// ---------------------------------------------------- Ask Ballava
// The assistant behind the in-app chat. It knows the family, the plan and the kitchen.
export function assistantReply(text, ctx = {}) {
  const q = String(text || '').toLowerCase();
  const { plan = {}, now = Date.now(), extra } = ctx;
  const today = dayKey(now);
  const nameOf = id => lookup(id, extra)?.name;
  const dishLine = list => list.slice(0, 3).map((r, i) => `${i + 1}. ${r.recipe.name} (${r.recipe.time} min)${r.why[0] ? ', ' + r.why[0].toLowerCase() : ''}`).join('\n');
  const asks = (...w) => w.some(x => q.includes(x));

  if (asks('tomorrow', 'kal')) {
    const day = plan[addDays(today, 1)];
    const names = SLOTS.map(s => day?.[s] && `${SLOT_LABEL[s]}: ${nameOf(day[s])}`).filter(Boolean);
    if (names.length) return { reply: `Tomorrow's plan:\n${names.join('\n')}` };
    return { reply: 'Nothing is planned for tomorrow yet. Open the Plan tab and tap "Plan my week".' };
  }
  if (asks('prep', 'soak', 'tonight i', 'ready for')) {
    const prep = prepTonight(plan, today, extra);
    return { reply: prep.length ? prep.map(p => `${p.name}: ${p.text}`).join('\n') : 'Nothing to prepare tonight.' };
  }
  if (asks('tiffin', 'lunchbox', 'lunch box', 'dabba')) {
    const list = recommend({ ...ctx, log: ctx.log || [], slot: 'tiffin', date: today, fastingApplies: false });
    return { reply: `Good tiffin ideas:\n${dishLine(list)}`, dishes: list.slice(0, 3).map(r => r.recipe.id) };
  }
  const slot = asks('breakfast', 'nashta') ? 'breakfast' : asks('lunch') ? 'lunch' : asks('dinner', 'tonight', 'raat') ? 'dinner' : asks('cook', 'make', 'banau', 'banaun', 'what should') ? slotNow(now) : null;
  const { found } = parseIngredients(q);
  if (slot && !found.length) {
    const planned = plan[today]?.[slot];
    const list = recommend({ ...ctx, log: ctx.log || [], slot, date: today });
    const head = planned ? `Your plan says ${nameOf(planned)}. Other good options:` : `For ${SLOT_LABEL[slot].toLowerCase()}, I'd suggest:`;
    return { reply: `${head}\n${dishLine(list)}`, dishes: list.slice(0, 3).map(r => r.recipe.id) };
  }
  if (found.length) {
    const { ready, almost } = suggest({ pantry: found.map(id => ({ id })), members: ctx.members || [], extraRecipes: ctx.extraRecipes || [], hidden: ctx.hidden || [] });
    const pick = [...ready, ...almost].slice(0, 3);
    if (pick.length) return { reply: `With ${found.map(id => BY_ID[id].name).join(', ')} you could make:\n${pick.map((r, i) => `${i + 1}. ${r.recipe.name} (${r.recipe.time} min)`).join('\n')}`, dishes: pick.map(r => r.recipe.id) };
  }
  return { reply: 'Ask me things like "What should I cook tonight?", "Tiffin ideas", "What\'s planned for tomorrow?", or "I have paneer and spinach".' };
}

export { ALL_RECIPES };
