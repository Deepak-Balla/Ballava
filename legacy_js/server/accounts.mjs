// Everything that needs the database: accounts, family sync, voting and the admin portal.
import { randomBytes } from 'node:crypto';
import { all, one, run, transaction } from './db.mjs';
import {
  fail, limited, clearLimit, hashPassword, checkPassword, startSession, endSession, endOtherSessions, currentUser, requireUser, requireAdmin,
  requestOtp, checkOtp, clearOtp, authConfig, createUser,
} from './auth.mjs';
import { RECIPES } from '../shared/recipes.mjs';
import { CATEGORIES } from '../shared/ingredients.mjs';
import { applyCatalog, prepareRecipe, validateRecipe } from '../shared/engine.mjs';

const STATE_KEYS = new Set(['pantry', 'members', 'shopping', 'history', 'aiRecipes', 'filters', 'plan', 'pins', 'prefs']);
const RECIPE_STATUS = new Set(['draft', 'review', 'published']);
const CONTENT_KINDS = new Set(['ingredient', 'rescue', 'announcement', 'festival']);
const STATE_LIMIT = 1024 * 1024;
const BODY_LIMIT = 200 * 1024;

const parse = s => JSON.parse(s);
const isEmail = s => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s) && s.length <= 200;
const cleanName = s => String(s || '').trim().slice(0, 60);
const contentOf = kind => all('SELECT data FROM content WHERE kind = ?', kind).map(r => parse(r.data));

// -------------------------------------------------------------- live catalog
let live = { recipes: [], hidden: [] };
let loaded = false;

export function refreshCatalog() {
  applyCatalog({ ingredients: contentOf('ingredient'), rescues: contentOf('rescue') });
  live = {
    recipes: all('SELECT live FROM recipes WHERE live IS NOT NULL').map(r => prepareRecipe({ tags: [], ...parse(r.live) })),
    hidden: all('SELECT id FROM hidden_recipes').map(r => r.id),
  };
  loaded = true;
}

export function liveCatalog() {
  if (!loaded) refreshCatalog();
  return live;
}

function publicCatalog() {
  return {
    recipes: all('SELECT live FROM recipes WHERE live IS NOT NULL').map(r => parse(r.live)),
    hidden: all('SELECT id FROM hidden_recipes').map(r => r.id),
    ingredients: contentOf('ingredient'),
    rescues: contentOf('rescue'),
    announcements: contentOf('announcement').filter(a => a.active),
    festivals: contentOf('festival').sort((a, b) => a.date.localeCompare(b.date)),
  };
}

// -------------------------------------------------------------- shapes sent to the browser
const publicUser = u => ({ id: u.id, name: u.name, email: u.email, phone: u.phone, role: u.role });

function householdOf(user) {
  const h = one('SELECT * FROM households WHERE id = ?', user.household_id);
  if (!h) return null;
  return { id: h.id, name: h.name, inviteCode: h.invite_code, people: all('SELECT name FROM users WHERE household_id = ? ORDER BY created_at', h.id).map(r => r.name) };
}

const mask = s => {
  if (!s) return null;
  if (s.includes('@')) { const [a, b] = s.split('@'); return `${a[0]}***@${b}`; }
  return `${s.slice(0, 3)}******${s.slice(-2)}`;
};

// -------------------------------------------------------------- user routes
const CONSENT_ERROR = 'Please agree to how Ballava stores your family\'s food and health details.';

async function signup(req, res, body, ip) {
  if (limited('signup:' + ip, Number(process.env.SIGNUP_RATE_LIMIT || 20), 3600000)) throw fail(429, 'Too many sign-ups from here. Please try again later.');
  const name = cleanName(body.name);
  const email = String(body.email || '').trim().toLowerCase();
  const password = String(body.password || '');
  if (!name) throw fail(400, 'Please enter your name.');
  if (!isEmail(email)) throw fail(400, 'Please enter a valid email address.');
  if (password.length < 8 || password.length > 200) throw fail(400, 'Please use a password of at least 8 characters.');
  if (!body.consent) throw fail(400, CONSENT_ERROR);
  if (one('SELECT id FROM users WHERE email = ?', email)) throw fail(409, 'An account with this email already exists. Please sign in.');
  const id = createUser({ name, email, passwordHash: await hashPassword(password), consent: true });
  startSession(req, res, id);
  return { user: publicUser(one('SELECT * FROM users WHERE id = ?', id)), isNew: true };
}

async function login(req, res, body, ip) {
  const email = String(body.email || '').trim().toLowerCase();
  const key = `login:${email}:${ip}`;
  if (limited(key, 6, 900000)) throw fail(429, 'Too many tries. Please wait 15 minutes and try again.');
  const user = one("SELECT * FROM users WHERE email = ? AND role = 'user'", email);
  const ok = await checkPassword(body.password, user?.password_hash);
  if (!ok || user.disabled) throw fail(401, 'That email or password is not right.');
  clearLimit(key);
  startSession(req, res, user.id);
  return { user: publicUser(user) };
}

function verifyOtp(req, res, body) {
  const phone = checkOtp(body.phone, body.code);
  let user = one('SELECT * FROM users WHERE phone = ?', phone);
  if (user?.disabled || user?.role === 'admin') throw fail(403, 'This account cannot sign in here.');
  const isNew = !user;
  if (isNew) {
    if (!body.consent) throw fail(400, CONSENT_ERROR);
    const name = cleanName(body.name);
    if (!name) throw fail(400, 'Please enter your name.');
    user = one('SELECT * FROM users WHERE id = ?', createUser({ name, phone, consent: true }));
  }
  clearOtp(phone);
  startSession(req, res, user.id);
  return { user: publicUser(user), isNew };
}

function readState(user) {
  const items = {};
  for (const row of all('SELECT key, value, version FROM state WHERE household_id = ?', user.household_id)) {
    items[row.key] = { value: parse(row.value), version: row.version };
  }
  return { items };
}

// Saves one piece of family data. If someone else changed it first, the browser gets 409
// with the latest copy, merges the two, and tries again, so nobody's change is lost.
function writeState(user, body) {
  const { key, value, baseVersion = 0 } = body;
  if (!STATE_KEYS.has(key)) throw fail(400, 'Unknown data type.');
  if (value === undefined) throw fail(400, 'Nothing to save.');
  const row = one('SELECT value, version FROM state WHERE household_id = ? AND key = ?', user.household_id, key);
  if ((row?.version || 0) !== baseVersion) {
    const err = fail(409, 'Someone else updated this.');
    err.payload = { error: err.message, value: row ? parse(row.value) : null, version: row?.version || 0 };
    throw err;
  }
  const version = baseVersion + 1;
  run(`INSERT INTO state (household_id, key, value, version, updated_at) VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(household_id, key) DO UPDATE SET value = excluded.value, version = excluded.version, updated_at = excluded.updated_at`,
  user.household_id, key, JSON.stringify(value), version, Date.now());
  return { version };
}

const isLastInHousehold = user => one('SELECT COUNT(*) AS n FROM users WHERE household_id = ? AND id != ?', user.household_id, user.id).n === 0;

function joinHousehold(user, body, ip) {
  if (limited('join:' + ip, 15, 3600000)) throw fail(429, 'Too many tries. Please try again later.');
  const target = one('SELECT * FROM households WHERE invite_code = ?', String(body.code || '').trim().toUpperCase());
  if (!target) throw fail(404, 'That family code is not right.');
  if (target.id === user.household_id) return { ok: true };
  transaction(() => {
    const orphan = isLastInHousehold(user) ? user.household_id : null;
    run('UPDATE users SET household_id = ? WHERE id = ?', target.id, user.id);
    if (orphan) run('DELETE FROM households WHERE id = ?', orphan);
  });
  return { ok: true };
}

function exportAccount(user) {
  const polls = all('SELECT title, date, slot, options FROM polls WHERE household_id = ?', user.household_id);
  return { exportedAt: new Date().toISOString(), account: publicUser(user), household: householdOf(user), data: readState(user).items, polls };
}

function deleteAccount(req, res, user, body) {
  if (body.confirm !== 'DELETE') throw fail(400, 'Please type DELETE to confirm.');
  endSession(req, res);
  transaction(() => {
    const orphan = isLastInHousehold(user) ? user.household_id : null;
    run('DELETE FROM users WHERE id = ?', user.id);
    if (orphan) run('DELETE FROM households WHERE id = ?', orphan);
  });
  return { ok: true };
}

// -------------------------------------------------------------- family voting
function createPoll(user, body) {
  const options = (Array.isArray(body.options) ? body.options : []).slice(0, 5)
    .map(o => ({ id: String(o.id || '').slice(0, 40), name: String(o.name || '').slice(0, 80) })).filter(o => o.id && o.name);
  if (options.length < 2) throw fail(400, 'A vote needs at least two dishes.');
  if (limited('poll:' + user.id, 30, 3600000)) throw fail(429, 'Too many votes started. Please try again later.');
  const token = randomBytes(16).toString('hex');
  const now = Date.now();
  run('INSERT INTO polls (token, household_id, title, date, slot, options, created_at, closes_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
    token, user.household_id, String(body.title || 'What should we eat?').slice(0, 100), String(body.date || '').slice(0, 10),
    String(body.slot || 'dinner').slice(0, 20), JSON.stringify(options), now, now + 3 * 86400000);
  return { token };
}

function pollView(token) {
  const p = one('SELECT * FROM polls WHERE token = ?', token);
  if (!p) throw fail(404, 'This vote was not found.');
  const counts = Object.fromEntries(all('SELECT option_id, COUNT(*) AS n FROM votes WHERE poll_token = ? GROUP BY option_id', token).map(r => [r.option_id, r.n]));
  const options = parse(p.options).map(o => ({ ...o, votes: counts[o.id] || 0 }));
  return { title: p.title, date: p.date, slot: p.slot, options, closed: p.closes_at < Date.now(), total: options.reduce((n, o) => n + o.votes, 0) };
}

function castVote(token, body, ip) {
  if (limited('vote:' + ip, 60, 3600000)) throw fail(429, 'Too many votes. Please try again later.');
  const view = pollView(token);
  if (view.closed) throw fail(410, 'This vote has closed.');
  const voter = String(body.voter || '').slice(0, 64);
  if (!voter) throw fail(400, 'Missing voter.');
  if (!view.options.some(o => o.id === body.optionId)) throw fail(400, 'Please choose one of the dishes.');
  run(`INSERT INTO votes (poll_token, voter, option_id, name) VALUES (?, ?, ?, ?)
    ON CONFLICT(poll_token, voter) DO UPDATE SET option_id = excluded.option_id, name = excluded.name`, token, voter, body.optionId, cleanName(body.name) || null);
  return pollView(token);
}

// -------------------------------------------------------------- admin
const audit = (admin, action, target) => run('INSERT INTO audit (admin_id, action, target, at) VALUES (?, ?, ?, ?)', admin.id, action, target || null, Date.now());

async function changeAdminPassword(req, admin, body) {
  const key = 'adminpw:' + admin.id;
  if (limited(key, 5, 900000)) throw fail(429, 'Too many tries. Please wait 15 minutes and try again.');
  const next = String(body.next || '');
  if (!(await checkPassword(body.current, admin.password_hash))) throw fail(400, 'Your current password is not right.');
  if (next.length < 12) throw fail(400, 'Please use a new password of at least 12 characters.');
  if (next.length > 200) throw fail(400, 'That password is too long.');
  if (next === body.current) throw fail(400, 'The new password must be different from the current one.');
  clearLimit(key);
  run('UPDATE users SET password_hash = ? WHERE id = ?', await hashPassword(next), admin.id);
  endOtherSessions(req, admin.id, 'admin');
  audit(admin, 'password.change');
  return { ok: true };
}

async function adminLogin(req, res, body, ip) {
  const email = String(body.email || '').trim().toLowerCase();
  const key = `admin:${email}:${ip}`;
  if (limited(key, 5, 900000)) throw fail(429, 'Too many tries. Please wait 15 minutes and try again.');
  const user = one("SELECT * FROM users WHERE email = ? AND role = 'admin' AND disabled = 0", email);
  const ok = await checkPassword(body.password, user?.password_hash);
  if (!ok) throw fail(401, 'That email or password is not right.');
  clearLimit(key);
  startSession(req, res, user.id, 'admin');
  audit(user, 'login');
  return { admin: { name: user.name, email: user.email } };
}

function adminStats() {
  const count = (sql, ...a) => one(sql, ...a).n;
  const weekAgo = Date.now() - 7 * 86400000;
  const since = new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10);
  return {
    users: count("SELECT COUNT(*) AS n FROM users WHERE role = 'user'"),
    activeWeek: count("SELECT COUNT(*) AS n FROM users WHERE role = 'user' AND last_seen > ?", weekAgo),
    households: count('SELECT COUNT(*) AS n FROM households'),
    mealsLogged: count("SELECT COALESCE(SUM(json_array_length(value)), 0) AS n FROM state WHERE key = 'history'"),
    recipesBuiltIn: RECIPES.length,
    recipesCustom: count('SELECT COUNT(*) AS n FROM recipes WHERE live IS NOT NULL'),
    recipesWaiting: count("SELECT COUNT(*) AS n FROM recipes WHERE status = 'review'"),
    aiCalls30d: count('SELECT COALESCE(SUM(calls), 0) AS n FROM ai_usage WHERE day >= ?', since),
    aiByDay: all('SELECT day, SUM(calls) AS calls FROM ai_usage WHERE day >= ? GROUP BY day ORDER BY day', since),
  };
}

// Deliberately contains no family or health details: admins see accounts, not kitchens.
function adminUsers() {
  return all(`SELECT u.id, u.name, u.email, u.phone, u.created_at, u.last_seen, u.disabled,
    (SELECT COUNT(*) FROM users x WHERE x.household_id = u.household_id) AS household_size
    FROM users u WHERE u.role = 'user' ORDER BY u.created_at DESC LIMIT 500`)
    .map(u => ({ id: u.id, name: u.name, contact: mask(u.email || u.phone), joined: u.created_at, lastSeen: u.last_seen, disabled: !!u.disabled, householdSize: u.household_size }));
}

function setUserDisabled(admin, id, disabled) {
  if (!one("SELECT id FROM users WHERE id = ? AND role = 'user'", id)) throw fail(404, 'User not found.');
  run('UPDATE users SET disabled = ? WHERE id = ?', disabled ? 1 : 0, id);
  if (disabled) run('DELETE FROM sessions WHERE user_id = ?', id);
  audit(admin, disabled ? 'user.disable' : 'user.enable', id);
  return { ok: true };
}

function adminRecipes() {
  const custom = new Map(all('SELECT * FROM recipes').map(r => [r.id, r]));
  const hidden = new Set(all('SELECT id FROM hidden_recipes').map(r => r.id));
  const row = (raw, source) => {
    const c = custom.get(raw.id);
    const data = c ? parse(c.data) : raw;
    return { id: raw.id, name: data.name, cuisine: data.cuisine, source, status: c ? c.status : 'published', live: c ? !!c.live : true, hidden: hidden.has(raw.id), data };
  };
  const ids = new Set(RECIPES.map(r => r.id));
  return [...[...custom.values()].filter(c => !ids.has(c.id)).map(c => row(parse(c.data), 'custom')), ...RECIPES.map(r => row(r, 'built-in'))];
}

// Editing never touches what users see: the live copy only changes when a recipe is published.
function saveRecipe(admin, body) {
  const recipe = body.recipe;
  if (!recipe || !/^[a-z0-9_]{2,40}$/.test(recipe.id || '')) throw fail(400, 'Id must be 2-40 lowercase letters, numbers or underscores.');
  const old = one('SELECT id FROM recipes WHERE id = ?', recipe.id);
  run(`INSERT INTO recipes (id, status, data, live, updated_at) VALUES (?, 'draft', ?, NULL, ?)
    ON CONFLICT(id) DO UPDATE SET status = 'draft', data = excluded.data, updated_at = excluded.updated_at`, recipe.id, JSON.stringify(recipe), Date.now());
  audit(admin, old ? 'recipe.edit' : 'recipe.create', recipe.id);
  return { ok: true, errors: validateRecipe(recipe) };
}

function setRecipeStatus(admin, id, status) {
  if (!RECIPE_STATUS.has(status)) throw fail(400, 'Unknown status.');
  const row = one('SELECT * FROM recipes WHERE id = ?', id);
  if (!row) throw fail(404, 'Save this recipe first.');
  if (status === 'published') {
    const errors = validateRecipe(parse(row.data));
    if (errors.length) { const e = fail(422, 'This recipe cannot be published yet.'); e.payload = { error: e.message, errors }; throw e; }
    if (row.status !== 'review') throw fail(409, 'Send the recipe to review before publishing.');
    run("UPDATE recipes SET status = 'published', live = data, updated_at = ? WHERE id = ?", Date.now(), id);
    refreshCatalog();
  } else run('UPDATE recipes SET status = ?, updated_at = ? WHERE id = ?', status, Date.now(), id);
  audit(admin, 'recipe.' + status, id);
  return { ok: true };
}

function setRecipeHidden(admin, id, hidden) {
  if (hidden) run('INSERT OR IGNORE INTO hidden_recipes (id) VALUES (?)', id);
  else run('DELETE FROM hidden_recipes WHERE id = ?', id);
  refreshCatalog();
  audit(admin, hidden ? 'recipe.hide' : 'recipe.show', id);
  return { ok: true };
}

function cleanContent(kind, d) {
  const id = String(d?.id || '').trim();
  if (!/^[a-z0-9_-]{2,40}$/.test(id)) throw fail(400, 'Id must be 2-40 lowercase letters, numbers, dashes or underscores.');
  const text = (v, max = 300) => String(v || '').trim().slice(0, max);
  if (kind === 'ingredient') {
    const name = text(d.name, 60);
    if (!name) throw fail(400, 'Name is required.');
    if (!CATEGORIES.includes(d.category)) throw fail(400, 'Please choose a category.');
    const list = v => (Array.isArray(v) ? v : String(v || '').split(',')).map(s => String(s).trim()).filter(Boolean).slice(0, 30);
    const shelf = Number(d.shelfDays);
    return { id, name, category: d.category, shelfDays: shelf > 0 ? shelf : null, aliases: list(d.aliases), allergens: list(d.allergens), diet: ['veg', 'egg', 'nonveg'].includes(d.diet) ? d.diet : 'veg' };
  }
  if (kind === 'rescue') {
    const title = text(d.title, 80);
    const fixes = (Array.isArray(d.fixes) ? d.fixes : String(d.fixes || '').split('\n')).map(s => text(s, 400)).filter(Boolean).slice(0, 10);
    if (!title || !fixes.length) throw fail(400, 'A title and at least one fix are required.');
    return { id, title, keywords: text(d.keywords), fixes, myth: text(d.myth, 400) || undefined };
  }
  if (kind === 'announcement') {
    const body = text(d.text, 240);
    if (!body) throw fail(400, 'Please write the announcement.');
    return { id, text: body, active: !!d.active };
  }
  const name = text(d.name, 80);
  if (!name || !/^\d{4}-\d{2}-\d{2}$/.test(d.date || '')) throw fail(400, 'A name and a date (YYYY-MM-DD) are required.');
  return { id, name, date: d.date, fast: !!d.fast };
}

function saveContent(admin, kind, body) {
  const data = cleanContent(kind, body.data);
  run('INSERT INTO content (kind, id, data) VALUES (?, ?, ?) ON CONFLICT(kind, id) DO UPDATE SET data = excluded.data', kind, data.id, JSON.stringify(data));
  refreshCatalog();
  audit(admin, kind + '.save', data.id);
  return { ok: true, data };
}

function deleteContent(admin, kind, id) {
  run('DELETE FROM content WHERE kind = ? AND id = ?', kind, id);
  refreshCatalog();
  audit(admin, kind + '.delete', id);
  return { ok: true };
}

async function adminRoutes(req, res, path, body, ip) {
  const method = req.method;
  if (method === 'POST' && path === '/api/admin/login') return adminLogin(req, res, await body(BODY_LIMIT), ip);
  const admin = requireAdmin(req);
  const [area, id, action] = path.split('/').slice(3).map(p => decodeURIComponent(p));
  const route = `${method} ${area}`;
  if (route === 'POST logout') { endSession(req, res, 'admin'); return { ok: true }; }
  if (route === 'GET me') return { admin: { name: admin.name, email: admin.email } };
  if (route === 'POST password') return changeAdminPassword(req, admin, await body(BODY_LIMIT));
  if (route === 'GET stats') return adminStats();
  if (route === 'GET users') return { users: adminUsers() };
  if (route === 'POST users' && action === 'disable') return setUserDisabled(admin, id, !!(await body(BODY_LIMIT)).disabled);
  if (route === 'GET recipes') return { recipes: adminRecipes() };
  if (route === 'POST recipes' && !id) return saveRecipe(admin, await body(BODY_LIMIT));
  if (route === 'POST recipes' && action === 'status') return setRecipeStatus(admin, id, (await body(BODY_LIMIT)).status);
  if (route === 'POST recipes' && action === 'hide') return setRecipeHidden(admin, id, !!(await body(BODY_LIMIT)).hidden);
  if (route === 'GET audit') return { entries: all('SELECT a.action, a.target, a.at, u.name FROM audit a LEFT JOIN users u ON u.id = a.admin_id ORDER BY a.id DESC LIMIT 100') };
  if (area === 'content' && CONTENT_KINDS.has(id)) {
    if (method === 'GET') return { items: contentOf(id) };
    const b = await body(BODY_LIMIT);
    return action === 'delete' ? deleteContent(admin, id, String(b.id)) : saveContent(admin, id, b);
  }
  throw fail(404, 'Unknown API route');
}

// -------------------------------------------------------------- routing
// Returns the JSON to send, or undefined when the route belongs to someone else.
export async function accountRoutes(req, res, path, readBody) {
  const ip = req.socket.remoteAddress || 'x';
  const body = limit => readBody(req, limit);

  if (path.startsWith('/api/admin/')) return adminRoutes(req, res, path, body, ip);

  if (req.method === 'GET') {
    if (path === '/api/catalog') return publicCatalog();
    if (path === '/api/auth/config') return authConfig();
    if (path === '/api/me') {
      const user = currentUser(req);
      if (!user) return { user: null };
      run('UPDATE users SET last_seen = ? WHERE id = ?', Date.now(), user.id);
      return { user: publicUser(user), household: householdOf(user) };
    }
    if (path === '/api/state') return readState(requireUser(req));
    if (path === '/api/account/export') return exportAccount(requireUser(req));
    const poll = path.match(/^\/api\/polls\/([a-f0-9]{32})$/);
    return poll ? pollView(poll[1]) : undefined;
  }
  if (req.method !== 'POST') return undefined;

  switch (path) {
    case '/api/auth/signup': return signup(req, res, await body(BODY_LIMIT), ip);
    case '/api/auth/login': return login(req, res, await body(BODY_LIMIT), ip);
    case '/api/auth/otp/request': return requestOtp((await body(BODY_LIMIT)).phone, ip);
    case '/api/auth/otp/verify': return verifyOtp(req, res, await body(BODY_LIMIT));
    case '/api/auth/logout': endSession(req, res); return { ok: true };
    case '/api/state': return writeState(requireUser(req), await body(STATE_LIMIT));
    case '/api/household/join': return joinHousehold(requireUser(req), await body(BODY_LIMIT), ip);
    case '/api/household/rename': {
      const user = requireUser(req);
      const name = cleanName((await body(BODY_LIMIT)).name);
      if (!name) throw fail(400, 'Please enter a name.');
      run('UPDATE households SET name = ? WHERE id = ?', name, user.household_id);
      return { ok: true };
    }
    case '/api/account/delete': return deleteAccount(req, res, requireUser(req), await body(BODY_LIMIT));
    case '/api/polls': return createPoll(requireUser(req), await body(BODY_LIMIT));
    default: {
      const vote = path.match(/^\/api\/polls\/([a-f0-9]{32})\/vote$/);
      return vote ? castVote(vote[1], await body(BODY_LIMIT), ip) : undefined;
    }
  }
}

export function recordAiCall(who) {
  const day = new Date().toISOString().slice(0, 10);
  run('INSERT INTO ai_usage (day, who, calls) VALUES (?, ?, 1) ON CONFLICT(day, who) DO UPDATE SET calls = calls + 1', day, who);
}

export { currentUser };
