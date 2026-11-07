// End-to-end test of the signed-in app: real Chrome, real server, real database, several family members.
// Run: npm run build && npm run test:e2e
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';

process.env.DB_PATH = ':memory:';
process.env.OTP_DEV_MODE = '1';
delete process.env.ANTHROPIC_API_KEY;

const { createServer } = await import('../server/server.mjs');
const { createUser, hashPassword } = await import('../server/auth.mjs');
const { chromium } = createRequire(import.meta.url)('playwright');

const shots = 'tests/screenshots';
const ADMIN = { email: 'admin@ballava.test', password: 'admin-secret-123' };
const ASHA = { name: 'Asha', email: 'asha@ballava.test', password: 'password123' };
const PHONE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };

let server, browser, base, page;
const errors = [];

async function device(options = PHONE) {
  const ctx = await browser.newContext(options);
  const p = await ctx.newPage();
  p.on('pageerror', e => errors.push(e.message));
  p.on('console', m => {
    // A wrong-password 401 shows up as a browser network message, and is expected.
    if (m.type() === 'error' && !/status of 4\d\d|ERR_FAILED|ERR_INTERNET_DISCONNECTED/.test(m.text())) errors.push(m.text());
  });
  return p;
}

const tab = (p, name) => p.getByRole('navigation', { name: 'Main' }).getByRole('button', { name, exact: true }).click();
const moreLink = async (p, name) => { await tab(p, 'More'); await p.getByRole('button', { name, exact: true }).click(); };
const snap = (p, name) => p.screenshot({ path: `${shots}/${name}.png` });
const dishNames = p => p.locator('.plan-day .plan-dish').allInnerTexts();

async function noSidewaysScroll(p, where) {
  const over = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert.ok(over <= 0, `${where} scrolls sideways by ${over}px`);
}

async function signIn(p, who = ASHA) {
  await p.goto(base);
  await p.getByLabel('Email').fill(who.email);
  await p.getByLabel('Password').fill(who.password);
  await p.getByRole('button', { name: 'Sign in', exact: true }).last().click();
  await p.getByRole('navigation', { name: 'Main' }).waitFor();
}

before(async () => {
  mkdirSync(shots, { recursive: true });
  server = createServer();
  await new Promise(r => server.listen(0, r));
  base = `http://localhost:${server.address().port}/`;
  createUser({ name: 'Admin', email: ADMIN.email, passwordHash: await hashPassword(ADMIN.password), role: 'admin' });
  browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
  page = await device();
});

after(async () => { await browser?.close(); server?.close(); });

test('a wrong password shows a clear message', async () => {
  await page.goto(base);
  await page.getByText('Cooks with you today').waitFor();
  await snap(page, '20-login');
  await page.getByLabel('Email').fill('nobody@ballava.test');
  await page.getByLabel('Password').fill('wrong-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).last().click();
  await page.getByRole('alert').getByText(/not right/).waitFor();
});

test('what you add as a guest moves into your new account', async () => {
  await page.getByRole('button', { name: 'Continue without an account' }).click();
  await page.getByRole('button', { name: 'Try with a sample kitchen' }).click();
  await page.getByText('Cook now').waitFor();
  await moreLink(page, 'Account');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('button', { name: 'Create account' }).click();
  await page.getByLabel('Your name').fill(ASHA.name);
  await page.getByLabel('Email').fill(ASHA.email);
  await page.getByLabel('Password').fill(ASHA.password);
  await page.getByRole('button', { name: 'Create account' }).last().click();
  await page.getByRole('alert').getByText(/agree/).waitFor();
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Create account' }).last().click();
  await page.getByRole('navigation', { name: 'Main' }).waitFor();
  await tab(page, 'Kitchen');
  await page.locator('.pantry-list .p-name', { hasText: 'Leftover rice' }).waitFor();
});

test('family profile with age, goals, tiffin and dislikes', async () => {
  await moreLink(page, 'Family');
  await page.getByPlaceholder('e.g. Amma').fill('Dadaji');
  await page.getByLabel('Diabetic').check();
  await page.getByLabel('Age group').selectOption('senior');
  await page.getByRole('button', { name: 'Low salt (BP)' }).click();
  await page.getByRole('button', { name: 'Add member' }).click();
  await page.getByText(/Added Dadaji/).waitFor();

  await page.getByPlaceholder('e.g. Amma').fill('Riya');
  await page.getByLabel('Age group').selectOption('child');
  await page.getByLabel('Spice level').selectOption('1');
  await page.getByLabel(/Takes a tiffin/).check();
  await page.getByLabel("Doesn't like").fill('karela');
  await page.getByRole('button', { name: 'Add member' }).click();
  await page.getByText(/Added Riya/).waitFor();
  await page.getByText('Dislikes Bitter gourd').waitFor();
  await snap(page, '21-family');
  await noSidewaysScroll(page, 'Family');
});

test('plan my week: 21 different meals, a tiffin for Riya', async () => {
  await tab(page, 'Plan');
  await page.getByRole('button', { name: 'Plan my week' }).click();
  await page.locator('.plan-day').nth(6).waitFor();
  const names = (await dishNames(page)).map(n => n.replace(/\s*\d+ min.*/, '').trim());
  const main = await page.locator('.plan-day .plan-row').evaluateAll(rows => rows
    .filter(r => /Breakfast|Lunch|Dinner/.test(r.querySelector('.plan-slot').textContent))
    .map(r => r.querySelector('.plan-dish').textContent));
  assert.equal(main.length, 21);
  assert.equal(new Set(main).size, 21, main.join(' | '));
  assert.ok(names.length > 21);
  assert.ok(await page.getByText('Tiffin · Riya').count() >= 1);
  await snap(page, '22-plan');
  await noSidewaysScroll(page, 'Plan');
});

test('swap a meal, lock it, and refreshing keeps it', async () => {
  const day = page.locator('.plan-day').first();
  const before = await day.locator('.plan-dish').nth(2).innerText();
  await day.getByRole('button', { name: 'Swap Dinner' }).click();
  await assert.doesNotReject(() => page.waitForFunction(old => document.querySelectorAll('.plan-day')[0].querySelectorAll('.plan-dish')[2].innerText !== old, before));
  const swapped = await day.locator('.plan-dish').nth(2).innerText();
  assert.equal(await day.getByRole('button', { name: 'Unlock Dinner' }).count(), 1, 'a swapped meal is locked');
  await page.getByRole('button', { name: 'Refresh unlocked meals' }).click();
  await page.getByText(/Your week is planned/).waitFor();
  assert.equal(await day.locator('.plan-dish').nth(2).innerText(), swapped);
});

test('groceries for the plan go to the shopping list', async () => {
  await page.getByRole('button', { name: /items to shopping list/ }).click();
  await page.getByText(/to your shopping list/).waitFor();
  await tab(page, 'List');
  await page.locator('.shop-list li').first().waitFor({ timeout: 5000 });
});

test('menu for the cook is shared in Hindi', async () => {
  await tab(page, 'Plan');
  const href = await page.getByRole('link', { name: 'Share on WhatsApp' }).getAttribute('href');
  assert.match(decodeURIComponent(href), /आज का मेन्यू/);
});

test('one meal, many plates shows each person what they need', async () => {
  await page.goto(base + '#/recipe/kanda_poha');
  await page.getByText('One meal, many plates').waitFor();
  await page.locator('.plates').getByText('Dadaji:').waitFor();
  await page.locator('.plates').getByText(/smaller portion/).waitFor();
  await snap(page, '23-plates');
});

test('pin a family tradition', async () => {
  await page.getByLabel('Day of the week').selectOption('0');
  await page.getByRole('button', { name: '⭐ Pin' }).click();
  await page.getByText(/your Sun favourite/).waitFor();
  await tab(page, 'Plan');
  await page.getByText('Family traditions').waitFor();
});

test('log a meal, including one from outside, and see the dashboard', async () => {
  await tab(page, 'Track');
  await page.getByRole('button', { name: 'Dinner', exact: true }).click();
  await page.getByLabel('Dish name', { exact: true }).fill('Dal Tadka');
  await page.getByRole('button', { name: 'Log', exact: true }).click();
  await page.getByText('Logged Dal Tadka').waitFor();
  await page.getByRole('button', { name: 'Lunch', exact: true }).click();
  await page.getByLabel('Dish name', { exact: true }).fill('Pizza from outside');
  await page.getByRole('button', { name: 'Log', exact: true }).click();
  await page.locator('.diary-item', { hasText: 'Pizza from outside' }).waitFor();
  await page.getByRole('button', { name: 'Yesterday' }).click();
  await page.getByLabel('Dish name', { exact: true }).fill('Jeera Rice');
  await page.getByRole('button', { name: 'Log', exact: true }).click();
  await page.locator('.diary-item', { hasText: 'Jeera Rice' }).waitFor();
  await page.locator('.bar-row', { hasText: 'Protein' }).locator('.bar-count').getByText('1').waitFor();
  await page.locator('.insights').waitFor();
  await snap(page, '24-dashboard');
  await noSidewaysScroll(page, 'Track');
  await page.getByRole('button', { name: 'Remove Pizza from outside' }).click();
  assert.equal(await page.locator('.diary-item', { hasText: 'Pizza' }).count(), 0);
});

test('logged dishes are flagged as repeats', async () => {
  await page.goto(base + '#/recipe/dal_tadka');
  await page.getByText('You already made this today.').waitFor();
});

test('finishing a cook logs it, and leftovers go to the kitchen', async () => {
  await page.goto(base + '#/recipe/jeera_rice');
  await page.getByRole('button', { name: 'Start cooking' }).click();
  for (let i = 0; i < 12; i++) {
    const done = page.getByRole('button', { name: 'Done cooking ✓' });
    if (await done.count()) { await done.click(); break; }
    await page.getByRole('button', { name: 'Next ›' }).click();
  }
  await page.getByText('Anything left over?').waitFor();
  await page.getByLabel(/Leftover rice becomes/).check();
  await page.getByRole('radio', { name: '4 stars' }).click();
  await page.getByRole('button', { name: 'Save and finish' }).click();
  await page.locator('.stats').getByText('meals cooked').waitFor();
  await tab(page, 'Track');
  await page.locator('.diary-item', { hasText: 'Jeera Rice' }).nth(1).waitFor({ timeout: 5000 });
});

test('Ask Ballava knows the plan', async () => {
  await moreLink(page, 'Ask Ballava');
  await page.getByRole('button', { name: "What's planned for tomorrow?" }).click();
  await page.locator('.bubble.bot', { hasText: "Tomorrow's plan" }).waitFor();
  await page.getByLabel('Your question').fill('I have paneer and spinach');
  await page.getByRole('button', { name: 'Send' }).click();
  await page.locator('.bubble.bot', { hasText: 'Palak Paneer' }).waitFor();
  await snap(page, '25-ask');
  await noSidewaysScroll(page, 'Ask');
});

test('your data follows you to a second phone', async () => {
  const phone2 = await device();
  await page.waitForTimeout(1500); // let the last changes upload
  await signIn(phone2);
  await tab(phone2, 'Plan');
  await phone2.locator('.plan-day').first().waitFor();
  await tab(phone2, 'Track');
  await phone2.locator('.diary-item', { hasText: 'Dal Tadka' }).waitFor();
  await moreLink(phone2, 'Family');
  await phone2.getByText('Dadaji').first().waitFor();
  await phone2.context().close();
});

test('a family member joins by code, and changes reach both phones', async () => {
  await moreLink(page, 'Account');
  const code = await page.getByLabel('Family code', { exact: true }).first().innerText();
  await snap(page, '26-account');
  const husband = await device();
  await husband.goto(base);
  await husband.getByRole('button', { name: 'Create account' }).click();
  await husband.getByLabel('Your name').fill('Ravi');
  await husband.getByLabel('Email').fill('ravi@ballava.test');
  await husband.getByLabel('Password').fill('password123');
  await husband.getByRole('checkbox').check();
  await husband.getByRole('button', { name: 'Create account' }).last().click();
  await husband.getByRole('navigation', { name: 'Main' }).waitFor();
  await moreLink(husband, 'Account');
  await husband.getByRole('textbox', { name: 'Family code' }).fill(code);
  await husband.getByRole('button', { name: 'Join', exact: true }).click();
  await husband.getByText('You joined the family kitchen').waitFor();
  await husband.getByText('Asha, Ravi').waitFor();

  // Ravi buys something. Asha sees it without doing anything except coming back to the app.
  await tab(husband, 'Kitchen');
  await husband.getByLabel('Add ingredients').fill('paneer');
  await husband.getByRole('button', { name: 'Add', exact: true }).click();
  await husband.locator('.pantry-list .p-name', { hasText: 'Paneer' }).waitFor();
  await husband.waitForTimeout(1500);
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await tab(page, 'Kitchen');
  await page.locator('.pantry-list .p-name', { hasText: 'Paneer' }).waitFor({ timeout: 8000 });

  // Both change the kitchen at the same time, with no connection: nobody's item is lost.
  await page.context().setOffline(true);
  await husband.context().setOffline(true);
  await page.getByLabel('Add ingredients').fill('beetroot');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await husband.getByLabel('Add ingredients').fill('radish');
  await husband.getByRole('button', { name: 'Add', exact: true }).click();
  await page.context().setOffline(false);
  await husband.context().setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await husband.evaluate(() => window.dispatchEvent(new Event('online')));
  for (const p of [page, husband]) for (const item of ['Beetroot', 'Radish']) {
    await p.evaluate(() => window.dispatchEvent(new Event('focus')));
    await p.locator('.pantry-list .p-name', { hasText: item }).waitFor({ timeout: 12000 });
  }
  await husband.context().close();
});

test('family vote: anyone with the link can vote, with no account', async () => {
  await tab(page, 'Plan');
  await page.getByRole('button', { name: /Ask the family/ }).first().click();
  const share = page.getByRole('link', { name: 'Share vote' }).first();
  await share.waitFor();
  const link = decodeURIComponent(await share.getAttribute('href')).match(/https?:\/\/\S+\/vote\/\S+/)[0];
  const kid = await device();
  await kid.goto(link);
  await kid.locator('.vote-option').first().waitFor();
  await snap(kid, '27-vote');
  await kid.locator('.vote-option').nth(1).click();
  await kid.getByText('Your vote is in').waitFor();
  assert.equal(await kid.getByRole('navigation', { name: 'Main' }).count(), 0, 'no family data on the public page');
  await kid.context().close();
  await page.reload();
  await tab(page, 'Plan');
  await page.getByRole('button', { name: 'Use the winner' }).first().click();
  await page.getByText(/it is!/).waitFor();
});

test('language switch changes the menus', async () => {
  await tab(page, 'More');
  await page.getByRole('button', { name: 'हिन्दी' }).click();
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'रसोई' }).waitFor();
  await snap(page, '28-hindi');
  await page.getByRole('button', { name: 'English' }).click();
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Kitchen', exact: true }).waitFor();
});

test('the app keeps working offline, and catches up later', async () => {
  await page.context().setOffline(true);
  await tab(page, 'Kitchen');
  await page.getByLabel('Add ingredients').fill('mushroom');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.locator('.pantry-list .p-name', { hasText: 'Mushroom' }).waitFor();
  await page.context().setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await page.waitForTimeout(1500);
  const phone2 = await device();
  await signIn(phone2);
  await tab(phone2, 'Kitchen');
  await phone2.locator('.pantry-list .p-name', { hasText: 'Mushroom' }).waitFor();
  await phone2.context().close();
});

test('a signed-in phone that opens with no internet still saves, and uploads later', async () => {
  const p = await device();
  await signIn(p);
  await p.context().route('**/api/**', r => r.abort());
  await p.reload();
  await tab(p, 'Kitchen');
  await p.getByLabel('Add ingredients').fill('cabbage');
  await p.getByRole('button', { name: 'Add', exact: true }).click();
  await p.locator('.pantry-list .p-name', { hasText: 'Cabbage' }).waitFor();
  await p.context().unroute('**/api/**');
  await p.evaluate(() => window.dispatchEvent(new Event('online')));
  await p.waitForTimeout(1500);
  await p.context().close();
  const other = await device();
  await signIn(other);
  await tab(other, 'Kitchen');
  await other.locator('.pantry-list .p-name', { hasText: 'Cabbage' }).waitFor();
  await other.context().close();
});

test('phone sign-in works from the screen', async () => {
  const p = await device();
  await p.goto(base);
  await p.getByRole('button', { name: 'Phone', exact: true }).click();
  await p.getByLabel('Mobile number').fill('9876543210');
  await p.getByRole('button', { name: 'Send code' }).click();
  const code = (await p.locator('.note.info b').innerText()).trim();
  await p.getByLabel('Your name').fill('Meena');
  await p.getByLabel('6-digit code').fill(code);
  await p.getByRole('checkbox').check();
  await p.getByRole('button', { name: 'Verify and continue' }).click();
  await p.getByRole('navigation', { name: 'Main' }).waitFor();
  await p.context().close();
});

test('admin: a user cannot get in, a wrong password fails', async () => {
  const p = await device({ viewport: { width: 1200, height: 800 } });
  await p.goto(base + 'admin');
  await p.getByLabel('Email').fill(ASHA.email);
  await p.getByLabel('Password').fill(ASHA.password);
  await p.getByRole('button', { name: 'Sign in' }).click();
  await p.getByRole('alert').getByText(/not right/).waitFor();
  await p.context().close();
});

test('admin: publish a recipe and it reaches users; bad recipes are stopped', async () => {
  const p = await device({ viewport: { width: 1200, height: 800 } });
  await p.goto(base + 'admin');
  await p.getByLabel('Email').fill(ADMIN.email);
  await p.getByLabel('Password').fill(ADMIN.password);
  await p.getByRole('button', { name: 'Sign in' }).click();
  await p.getByText('Meals logged').waitFor();
  await snap(p, '30-admin-overview');

  await p.getByRole('button', { name: 'Recipes', exact: true }).click();
  await p.getByRole('button', { name: '+ New recipe' }).click();
  await p.getByLabel(/^Id/).fill('gongura_pappu');
  await p.getByLabel('Name', { exact: true }).fill('Admin Test Pappu');
  await p.getByLabel('Cuisine').fill('Andhra');
  await p.getByLabel('Ingredients', { exact: true }).fill('toor_dal:1 cup\nmysteryleaf:1 bunch');
  await p.getByLabel('Steps', { exact: true }).fill('Pressure cook the dal well. |3w\nAdd the tadka and serve hot.');
  await p.getByRole('button', { name: 'Save draft' }).click();
  await p.getByRole('alert').getByText(/Unknown ingredient "mysteryleaf"/).waitFor();
  await p.getByLabel('Ingredients', { exact: true }).fill('toor_dal:1 cup\nspinach:1 bunch\nturmeric:1/2 tsp');
  await p.getByRole('button', { name: 'Save draft' }).click();
  await p.getByRole('button', { name: 'Send to review' }).click();
  await p.getByRole('button', { name: 'Publish' }).click();
  await p.getByText('Published. Users see it now.').waitFor();
  await snap(p, '31-admin-recipe');

  await page.goto(base + '#/recipe/gongura_pappu');
  await page.reload();
  await page.getByRole('heading', { name: /Admin Test Pappu/ }).waitFor();

  await p.getByRole('button', { name: 'Close' }).click();
  await p.getByRole('button', { name: 'Announcements' }).click();
  await p.getByLabel('Id').fill('welcome');
  await p.getByLabel('Message').fill('Navratri recipes are here!');
  await p.getByLabel('Show to users').check();
  await p.getByRole('button', { name: 'Save', exact: true }).click();
  await p.getByRole('cell', { name: 'Navratri recipes are here!' }).waitFor();
  await page.goto(base + '#/home');
  await page.reload();
  await page.getByText('Navratri recipes are here!').waitFor();

  await p.getByRole('button', { name: 'Users' }).click();
  await p.getByRole('cell', { name: 'Asha' }).waitFor();
  const text = await p.locator('body').innerText();
  assert.ok(!text.includes('Dadaji') && !text.includes(ASHA.email), 'admin sees no family details');
  await snap(p, '32-admin-users');
  await p.getByRole('button', { name: 'Audit log' }).click();
  await p.getByRole('cell', { name: 'recipe.published' }).waitFor();
  await p.context().close();
});

test('every screen fits a phone', async () => {
  for (const r of ['home', 'plan', 'track', 'pantry', 'list', 'more', 'family', 'bachao', 'ask', 'account', 'ai', 'recipe/dal_tadka']) {
    await page.goto(`${base}#/${r}`);
    await page.waitForTimeout(120);
    await noSidewaysScroll(page, r);
  }
});

test('signing out removes family data from this phone', async () => {
  await moreLink(page, 'Account');
  await page.getByRole('button', { name: 'Sign out' }).click();
  await page.getByText('Continue without an account').waitFor();
  const left = await page.evaluate(() => ['members', 'pantry', 'history', 'plan'].map(k => localStorage.getItem('ballava.' + k)));
  assert.ok(left.every(v => v === null || v === '[]' || v === '{}'), left.join());
  await page.getByRole('button', { name: 'Continue without an account' }).click();
  await page.getByRole('button', { name: 'Try with a sample kitchen' }).waitFor();
});

test('no JavaScript errors happened anywhere', () => {
  assert.deepEqual(errors, []);
});
