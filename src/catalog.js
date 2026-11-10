// The recipe book and ingredient list, as sent by the Python server (GET /api/catalog).
// Kept on the phone so recipes, cook mode and the kitchen list still work offline.
// Only small display helpers live here. All the real thinking happens in Python (kitchen/engine.py, kitchen/planner.py).

const EMPTY = { recipes: [], hidden: [], ingredients: [], categories: [], kits: [], assumed: ['salt', 'oil', 'water'], rescues: [],
  announcements: [], festivals: [], goals: [], ageGroups: [] };

let current = load();
let byId = index(current);

function load() {
  try { return { ...EMPTY, ...JSON.parse(localStorage.getItem('ballava.catalog') || '{}') }; } catch { return { ...EMPTY }; }
}

function index(c) {
  return {
    ingredients: Object.fromEntries(c.ingredients.map(i => [i.id, i])),
    recipes: Object.fromEntries(c.recipes.map(r => [r.id, r])),
  };
}

export function setCatalog(c) {
  current = { ...EMPTY, ...c };
  byId = index(current);
  try { localStorage.setItem('ballava.catalog', JSON.stringify(current)); } catch { /* storage full: keep in memory */ }
}

export const getCatalog = () => current;
export const hasCatalog = () => current.recipes.length > 0;
export const ingredient = id => byId.ingredients[id];
export const ingName = id => byId.ingredients[id]?.name || id;
export const recipeById = id => byId.recipes[id];

// ---- Dates, as the family sees them (the server is told our time zone).
export const DAY = 86400000;
export const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export const SLOTS = ['breakfast', 'lunch', 'dinner'];
export const SLOT_LABEL = { breakfast: 'Breakfast', lunch: 'Lunch', dinner: 'Dinner', snack: 'Snack' };

export function dayKey(t = Date.now()) {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function addDays(key, n) {
  const d = new Date(key + 'T12:00:00');
  d.setDate(d.getDate() + n);
  return dayKey(d.getTime());
}
export function slotNow(t = Date.now()) {
  const h = new Date(t).getHours();
  return h < 11 ? 'breakfast' : h < 16 ? 'lunch' : 'dinner';
}

// ---- Freshness labels for the kitchen list.
export function defaultExpiry(id, now = Date.now()) {
  const d = ingredient(id)?.shelfDays;
  return d ? now + d * DAY : null;
}
export function daysLeft(item, now = Date.now()) {
  return item.expiresAt ? Math.ceil((item.expiresAt - now) / DAY) : null;
}
export function useSoon(pantry, now = Date.now(), within = 2) {
  return pantry.filter(p => { const d = daysLeft(p, now); return d !== null && d <= within; }).sort((a, b) => a.expiresAt - b.expiresAt);
}

export const shoppingText = ids => 'Ballava shopping list:\n' + ids.map(id => `- ${ingName(id)}`).join('\n');
