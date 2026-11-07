// Tests for accounts, family sync, voting and the admin portal, against a real server and an in-memory database.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';

process.env.DB_PATH = ':memory:';
delete process.env.TWILIO_SID;
process.env.OTP_DEV_MODE = '1';
process.env.SIGNUP_RATE_LIMIT = '1000';

const { createServer } = await import('../server/server.mjs');
const { createUser, hashPassword } = await import('../server/auth.mjs');
const { one } = await import('../server/db.mjs');

let server, base;
const ADMIN = { email: 'admin@ballava.test', password: 'admin-secret-123' };

// A tiny browser: remembers its own cookies.
function client() {
  const jar = new Map();
  const call = async (method, path, body, headers = {}) => {
    const res = await fetch(base + path, {
      method,
      headers: { 'content-type': 'application/json', cookie: [...jar].map(([k, v]) => `${k}=${v}`).join('; '), ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    for (const c of res.headers.getSetCookie()) {
      const [pair] = c.split(';');
      const i = pair.indexOf('=');
      if (/Max-Age=0/.test(c)) jar.delete(pair.slice(0, i)); else jar.set(pair.slice(0, i), pair.slice(i + 1));
    }
    return { status: res.status, data: await res.json().catch(() => null), headers: res.headers };
  };
  return { get: (p, h) => call('GET', p, undefined, h), post: (p, b = {}, h) => call('POST', p, b, h), jar };
}

let n = 0;
async function newUser(extra = {}) {
  const c = client();
  const email = `user${++n}@ballava.test`;
  const r = await c.post('/api/auth/signup', { name: `User ${n}`, email, password: 'password123', consent: true, ...extra });
  assert.equal(r.status, 200, JSON.stringify(r.data));
  return Object.assign(c, { email, id: r.data.user.id });
}

async function adminClient() {
  const c = client();
  assert.equal((await c.post('/api/admin/login', ADMIN)).status, 200);
  return c;
}

before(async () => {
  server = createServer();
  await new Promise(r => server.listen(0, r));
  base = `http://127.0.0.1:${server.address().port}`;
  createUser({ name: 'Admin', email: ADMIN.email, passwordHash: await hashPassword(ADMIN.password), role: 'admin' });
});
after(() => server.close());

// ---------- Sign-in ----------
test('sign up, stay signed in, sign out', async () => {
  const c = await newUser();
  const me = await c.get('/api/me');
  assert.equal(me.data.user.email, c.email);
  assert.ok(me.data.household.inviteCode);
  assert.equal((await c.post('/api/auth/logout')).status, 200);
  assert.equal((await c.get('/api/me')).data.user, null);
});

test('session cookie cannot be read by page scripts', async () => {
  const c = client();
  const res = await fetch(base + '/api/auth/signup', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name: 'C', email: 'cookie@ballava.test', password: 'password123', consent: true }) });
  assert.match(res.headers.get('set-cookie'), /HttpOnly/);
  assert.match(res.headers.get('set-cookie'), /SameSite=Lax/);
  assert.equal(c.jar.size, 0);
});

test('sign up checks its inputs and needs consent', async () => {
  const c = client();
  const good = { name: 'A', email: 'check@ballava.test', password: 'password123', consent: true };
  assert.equal((await c.post('/api/auth/signup', { ...good, email: 'nope' })).status, 400);
  assert.equal((await c.post('/api/auth/signup', { ...good, password: 'short' })).status, 400);
  assert.equal((await c.post('/api/auth/signup', { ...good, consent: false })).status, 400);
  assert.equal((await c.post('/api/auth/signup', good)).status, 200);
  assert.equal((await client().post('/api/auth/signup', good)).status, 409);
});

test('passwords are stored hashed, never as plain text', async () => {
  const c = await newUser();
  const row = one('SELECT password_hash FROM users WHERE email = ?', c.email);
  assert.ok(row.password_hash.startsWith('s1$'));
  assert.ok(!row.password_hash.includes('password123'));
});

test('wrong password fails, and repeated tries get locked out', async () => {
  const c = await newUser();
  const t = client();
  const statuses = [];
  for (let i = 0; i < 8; i++) statuses.push((await t.post('/api/auth/login', { email: c.email, password: 'wrong-password' })).status);
  assert.equal(statuses[0], 401);
  assert.ok(statuses.includes(429), statuses.join(','));
});

test('phone sign-in with a one-time code', async () => {
  const c = client();
  assert.equal((await c.post('/api/auth/otp/request', { phone: '123' })).status, 400);
  const { data } = await c.post('/api/auth/otp/request', { phone: '98765 43210' });
  assert.match(data.devCode, /^\d{6}$/);
  const wrong = String((Number(data.devCode) % 899999) + 100001);
  assert.equal((await c.post('/api/auth/otp/verify', { phone: '9876543210', code: wrong, name: 'Asha', consent: true })).status, 400);
  const ok = await c.post('/api/auth/otp/verify', { phone: '9876543210', code: data.devCode, name: 'Asha', consent: true });
  assert.equal(ok.status, 200, JSON.stringify(ok.data));
  assert.equal(ok.data.user.phone, '+919876543210');
  assert.equal(ok.data.isNew, true);
  assert.equal((await c.post('/api/auth/otp/verify', { phone: '9876543210', code: data.devCode })).status, 400, 'a code only works once');
});

test('too many wrong phone codes kills the code', async () => {
  const c = client();
  const { data } = await c.post('/api/auth/otp/request', { phone: '9000000001' });
  const wrong = String((Number(data.devCode) % 899999) + 100001);
  for (let i = 0; i < 5; i++) await c.post('/api/auth/otp/verify', { phone: '9000000001', code: wrong });
  assert.equal((await c.post('/api/auth/otp/verify', { phone: '9000000001', code: data.devCode, name: 'X', consent: true })).status, 429);
});

test('code is never shown outside dev mode, and phone sign-in says it is off', async () => {
  delete process.env.OTP_DEV_MODE;
  try {
    const c = client();
    assert.deepEqual((await c.get('/api/auth/config')).data, { phone: false, devOtp: false });
    const r = await c.post('/api/auth/otp/request', { phone: '9000000002' });
    assert.equal(r.status, 503);
    assert.equal(r.data.devCode, undefined);
  } finally { process.env.OTP_DEV_MODE = '1'; }
});

test('codes go through the SMS provider when one is set up, and stay out of the response', async () => {
  Object.assign(process.env, { TWILIO_SID: 'sid', TWILIO_TOKEN: 'tok', TWILIO_FROM: '+15550000000' });
  const real = globalThis.fetch;
  const sent = [];
  globalThis.fetch = async (url, opts) => {
    if (String(url).includes('twilio.com')) { sent.push(String(opts.body)); return new Response('{}', { status: 201 }); }
    return real(url, opts);
  };
  try {
    const r = await client().post('/api/auth/otp/request', { phone: '9000000003' });
    assert.equal(r.status, 200);
    assert.equal(r.data.devCode, undefined);
    assert.equal(sent.length, 1);
    assert.match(decodeURIComponent(sent[0].replace(/\+/g, ' ')), /Your Ballava code is \d{6}/);
  } finally {
    globalThis.fetch = real;
    for (const k of ['TWILIO_SID', 'TWILIO_TOKEN', 'TWILIO_FROM']) delete process.env[k];
  }
});

test('other websites cannot post as a signed-in user', async () => {
  const c = await newUser();
  const r = await c.post('/api/state', { key: 'pantry', value: [] }, { origin: 'https://evil.example' });
  assert.equal(r.status, 403);
});

// ---------- Family data ----------
test('family data needs a sign-in', async () => {
  const c = client();
  assert.equal((await c.get('/api/state')).status, 401);
  assert.equal((await c.post('/api/state', { key: 'pantry', value: [] })).status, 401);
  assert.equal((await c.get('/api/account/export')).status, 401);
});

test('saved data comes back on another device', async () => {
  const c = await newUser();
  const pantry = [{ id: 'tomato', addedAt: 1 }];
  assert.deepEqual((await c.post('/api/state', { key: 'pantry', value: pantry, baseVersion: 0 })).data, { version: 1 });
  const other = client();
  await other.post('/api/auth/login', { email: c.email, password: 'password123' });
  assert.deepEqual((await other.get('/api/state')).data.items.pantry, { value: pantry, version: 1 });
});

test('unknown data types are refused', async () => {
  const c = await newUser();
  assert.equal((await c.post('/api/state', { key: 'role', value: 'admin' })).status, 400);
});

test('two people editing at once: the second is told and given the latest', async () => {
  const c = await newUser();
  await c.post('/api/state', { key: 'shopping', value: [{ id: 'a' }], baseVersion: 0 });
  const stale = await c.post('/api/state', { key: 'shopping', value: [{ id: 'b' }], baseVersion: 0 });
  assert.equal(stale.status, 409);
  assert.deepEqual(stale.data.value, [{ id: 'a' }]);
  assert.equal(stale.data.version, 1);
});

test('families cannot see each other', async () => {
  const a = await newUser();
  const b = await newUser();
  await a.post('/api/state', { key: 'members', value: [{ name: 'Secret', diabetic: true }], baseVersion: 0 });
  assert.deepEqual((await b.get('/api/state')).data.items, {});
});

test('a family code shares one kitchen, and a wrong code does not', async () => {
  const a = await newUser();
  const b = await newUser();
  await a.post('/api/state', { key: 'pantry', value: [{ id: 'rice' }], baseVersion: 0 });
  const code = (await a.get('/api/me')).data.household.inviteCode;
  assert.equal((await b.post('/api/household/join', { code: 'WRONG123' })).status, 404);
  assert.equal((await b.post('/api/household/join', { code: code.toLowerCase() })).status, 200);
  assert.deepEqual((await b.get('/api/state')).data.items.pantry.value, [{ id: 'rice' }]);
  assert.equal((await a.get('/api/me')).data.household.people.length, 2);
});

test('you can download your data and delete your account', async () => {
  const c = await newUser();
  await c.post('/api/state', { key: 'pantry', value: [{ id: 'dal' }], baseVersion: 0 });
  const exp = await c.get('/api/account/export');
  assert.deepEqual(exp.data.data.pantry.value, [{ id: 'dal' }]);
  assert.equal((await c.post('/api/account/delete', { confirm: 'no' })).status, 400);
  const hh = one('SELECT household_id AS id FROM users WHERE id = ?', c.id).id;
  assert.equal((await c.post('/api/account/delete', { confirm: 'DELETE' })).status, 200);
  assert.equal(one('SELECT id FROM users WHERE id = ?', c.id), undefined);
  assert.equal(one('SELECT COUNT(*) AS n FROM state WHERE household_id = ?', hh).n, 0, 'family data is deleted too');
  assert.equal((await client().post('/api/auth/login', { email: c.email, password: 'password123' })).status, 401);
});

test('leaving a shared family keeps the data for the others', async () => {
  const a = await newUser();
  const b = await newUser();
  await a.post('/api/state', { key: 'pantry', value: [{ id: 'rice' }], baseVersion: 0 });
  await b.post('/api/household/join', { code: (await a.get('/api/me')).data.household.inviteCode });
  await a.post('/api/account/delete', { confirm: 'DELETE' });
  assert.deepEqual((await b.get('/api/state')).data.items.pantry.value, [{ id: 'rice' }]);
});

// ---------- Family vote ----------
test('family vote: share a link, vote without an account, change your mind', async () => {
  const c = await newUser();
  const options = [{ id: 'rajma_masala', name: 'Rajma' }, { id: 'chole', name: 'Chole' }];
  assert.equal((await client().post('/api/polls', { options })).status, 401);
  assert.equal((await c.post('/api/polls', { options: options.slice(0, 1) })).status, 400);
  const { token } = (await c.post('/api/polls', { title: 'Dinner?', date: '2026-11-08', slot: 'dinner', options })).data;
  const guest = client();
  assert.equal((await guest.post(`/api/polls/${token}/vote`, { voter: 'v1', optionId: 'pizza' })).status, 400);
  await guest.post(`/api/polls/${token}/vote`, { voter: 'v1', optionId: 'chole', name: 'Riya' });
  await guest.post(`/api/polls/${token}/vote`, { voter: 'v2', optionId: 'chole' });
  const changed = await guest.post(`/api/polls/${token}/vote`, { voter: 'v1', optionId: 'rajma_masala' });
  assert.deepEqual(changed.data.options.map(o => o.votes), [1, 1]);
  assert.equal(changed.data.total, 2);
  assert.equal(JSON.stringify(changed.data).includes('household'), false);
});

// ---------- Admin ----------
test('normal users cannot reach anything in admin', async () => {
  const c = await newUser();
  for (const p of ['me', 'stats', 'users', 'recipes', 'audit', 'content/announcement']) assert.equal((await c.get('/api/admin/' + p)).status, 401, p);
  assert.equal((await c.post('/api/admin/recipes', { recipe: { id: 'hack' } })).status, 401);
  assert.equal((await c.post('/api/admin/login', { email: c.email, password: 'password123' })).status, 401);
});

test('an admin login does not work in the user app, and vice versa', async () => {
  assert.equal((await client().post('/api/auth/login', ADMIN)).status, 401);
  const a = await adminClient();
  assert.equal((await a.get('/api/me')).data.user, null);
});

test('forged admin cookie is refused', async () => {
  const c = client();
  c.jar.set('ballava_admin', 'a'.repeat(64));
  assert.equal((await c.get('/api/admin/stats')).status, 401);
});

test('admin stats and user list show no family or health details', async () => {
  const c = await newUser();
  await c.post('/api/state', { key: 'members', value: [{ name: 'PrivateGrandma', diabetic: true, goals: ['pregnancy'] }], baseVersion: 0 });
  await c.post('/api/state', { key: 'history', value: [{ recipeId: 'idli' }, { recipeId: 'sambar' }], baseVersion: 0 });
  const a = await adminClient();
  const stats = await a.get('/api/admin/stats');
  assert.ok(stats.data.users >= 1 && stats.data.mealsLogged >= 2);
  const users = await a.get('/api/admin/users');
  const text = JSON.stringify([users.data, stats.data]);
  assert.ok(!text.includes('PrivateGrandma') && !text.includes('diabetic') && !text.includes('pregnancy'));
  assert.ok(!text.includes(c.email), 'contact details are masked');
  assert.ok(users.data.users.some(u => u.contact?.includes('***@ballava.test')));
});

test('disabling a user signs them out at once', async () => {
  const c = await newUser();
  const a = await adminClient();
  assert.equal((await a.post(`/api/admin/users/${c.id}/disable`, { disabled: true })).status, 200);
  assert.equal((await c.get('/api/me')).data.user, null);
  assert.equal((await client().post('/api/auth/login', { email: c.email, password: 'password123' })).status, 401);
  await a.post(`/api/admin/users/${c.id}/disable`, { disabled: false });
  assert.equal((await client().post('/api/auth/login', { email: c.email, password: 'password123' })).status, 200);
});

const newRecipe = (over = {}) => ({
  id: 'test_khichdi', name: 'Test Khichdi', cuisine: 'Test', meal: ['lunch', 'dinner'], time: 20, serves: 2, spice: 1, tags: ['gluten-free'],
  ing: ['rice:1 cup', 'moong_dal:1/2 cup'], steps: ['Wash the rice and dal.', 'Pressure cook them together. |3w'], ...over,
});

test('recipes go draft, then review, then live, and users only see them when live', async () => {
  const a = await adminClient();
  const visible = async () => (await client().get('/api/catalog')).data.recipes.some(r => r.id === 'test_khichdi');
  assert.deepEqual((await a.post('/api/admin/recipes', { recipe: newRecipe() })).data, { ok: true, errors: [] });
  assert.equal(await visible(), false, 'drafts stay hidden');
  assert.equal((await a.post('/api/admin/recipes/test_khichdi/status', { status: 'published' })).status, 409, 'must be reviewed first');
  await a.post('/api/admin/recipes/test_khichdi/status', { status: 'review' });
  assert.equal((await a.post('/api/admin/recipes/test_khichdi/status', { status: 'published' })).status, 200);
  assert.equal(await visible(), true);
  const r = await client().post('/api/suggest', { pantry: ['rice', 'moong_dal'] });
  assert.ok(r.data.ready.some(d => d.id === 'test_khichdi'), 'the live recipe reaches suggestions');
});

test('editing a live recipe does not change it until it is published again', async () => {
  const a = await adminClient();
  await a.post('/api/admin/recipes', { recipe: newRecipe({ id: 'edit_me', name: 'Version One' }) });
  await a.post('/api/admin/recipes/edit_me/status', { status: 'review' });
  await a.post('/api/admin/recipes/edit_me/status', { status: 'published' });
  await a.post('/api/admin/recipes', { recipe: newRecipe({ id: 'edit_me', name: 'Version Two' }) });
  const live = (await client().get('/api/catalog')).data.recipes.find(r => r.id === 'edit_me');
  assert.equal(live.name, 'Version One');
});

test('a recipe that breaks the rules cannot be published', async () => {
  const a = await adminClient();
  const bad = newRecipe({ id: 'bad_recipe', tags: ['gluten-free'], ing: ['atta:1 cup'] });
  const saved = await a.post('/api/admin/recipes', { recipe: bad });
  assert.match(saved.data.errors.join(), /gluten-free/);
  await a.post('/api/admin/recipes/bad_recipe/status', { status: 'review' });
  const r = await a.post('/api/admin/recipes/bad_recipe/status', { status: 'published' });
  assert.equal(r.status, 422);
  assert.match(r.data.errors.join(), /gluten-free/);
  const meat = await a.post('/api/admin/recipes', { recipe: newRecipe({ id: 'no_safety', tags: [], ing: ['chicken:500 g'] }) });
  assert.match(meat.data.errors.join(), /food-safety/);
});

test('a hidden recipe disappears from suggestions', async () => {
  const a = await adminClient();
  const has = async () => (await client().post('/api/suggest', { pantry: ['leftover_rice', 'curd'] })).data.ready.some(d => d.id === 'curd_rice');
  assert.equal(await has(), true);
  await a.post('/api/admin/recipes/curd_rice/hide', { hidden: true });
  assert.equal(await has(), false);
  await a.post('/api/admin/recipes/curd_rice/hide', { hidden: false });
  assert.equal(await has(), true);
});

test('admin-added ingredients and Bachao fixes work straight away', async () => {
  const a = await adminClient();
  await a.post('/api/admin/content/ingredient', { data: { id: 'gongura', name: 'Gongura', category: 'Vegetables', shelfDays: 3, aliases: 'sorrel leaves, ambadi' } });
  assert.deepEqual((await client().post('/api/parse', { text: 'ambadi' })).data.found, ['gongura']);
  await a.post('/api/admin/content/rescue', { data: { id: 'smoky', title: 'Too smoky', keywords: 'dhuan fumes', fixes: 'Move it to a clean pan.' } });
  const r = await client().post('/api/rescue', { text: 'dhuan' });
  assert.equal(r.data[0].title, 'Too smoky');
  await a.post('/api/admin/content/ingredient/delete', { id: 'gongura' });
  assert.deepEqual((await client().post('/api/parse', { text: 'ambadi' })).data.found, []);
});

test('announcements and the festival calendar reach the app', async () => {
  const a = await adminClient();
  await a.post('/api/admin/content/announcement', { data: { id: 'hello', text: 'New recipes!', active: true } });
  await a.post('/api/admin/content/announcement', { data: { id: 'old', text: 'Old news', active: false } });
  await a.post('/api/admin/content/festival', { data: { id: 'ekadashi-1', name: 'Ekadashi', date: '2026-11-20', fast: true } });
  assert.equal((await a.post('/api/admin/content/festival', { data: { id: 'bad', name: 'X', date: 'soon' } })).status, 400);
  const cat = (await client().get('/api/catalog')).data;
  assert.deepEqual(cat.announcements.map(x => x.id), ['hello']);
  assert.equal(cat.festivals[0].name, 'Ekadashi');
});

test('admin changes are written to the audit log', async () => {
  const a = await adminClient();
  const log = (await a.get('/api/admin/audit')).data.entries.map(e => e.action);
  assert.ok(log.includes('recipe.published') && log.includes('login') && log.includes('recipe.hide'), log.join());
});

test('admin sign-out ends the session', async () => {
  const a = await adminClient();
  await a.post('/api/admin/logout');
  assert.equal((await a.get('/api/admin/stats')).status, 401);
});

test('the admin page is served, and pages set security headers', async () => {
  const res = await fetch(base + '/admin');
  assert.equal(res.status, 200);
  assert.match(await res.text(), /Ballava Admin/);
  assert.match(res.headers.get('content-security-policy'), /frame-ancestors 'none'/);
});
