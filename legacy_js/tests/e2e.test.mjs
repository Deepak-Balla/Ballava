// End-to-end test: opens the real app in a (hidden) Chrome browser on a phone-sized
// screen and clicks through it like a person would. Screenshots go to tests/screenshots/.
// Run: npm run build && npm run test:e2e
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
process.env.DB_PATH = ':memory:';
delete process.env.ANTHROPIC_API_KEY;
const { createServer } = await import('../server/server.mjs');

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

let server, browser, page, base;
const errors = [];
const shots = 'tests/screenshots';
const snap = name => page.screenshot({ path: `${shots}/${name}.png`, fullPage: false });

before(async () => {
  mkdirSync(shots, { recursive: true });
  server = createServer();
  await new Promise(r => server.listen(0, r));
  base = `http://localhost:${server.address().port}/`;
  browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  page = await ctx.newPage();
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(base);
});

after(async () => { await browser?.close(); server?.close(); });

test('first visit shows the welcome screen', async () => {
  await page.getByRole('button', { name: 'Continue without an account' }).click();
  await page.getByText('Cooks with you today. For you tomorrow.').waitFor();
  await snap('01-welcome');
});

test('add ingredients by typing in Hindi/English', async () => {
  await page.getByRole('button', { name: 'Add what I have' }).click();
  await page.getByLabel('Add ingredients').fill('2 tamatar, pyaz, anda, hari mirch, dahi, leftover chawal, mysteryfruit');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByText(/Didn't recognise: mysteryfruit/).waitFor();
  for (const name of ['Tomato', 'Onion', 'Eggs', 'Green chilli', 'Curd', 'Leftover rice']) {
    await page.locator('.pantry-list .p-name', { hasText: name }).first().waitFor();
  }
  await page.getByRole('button', { name: '+ Masala box' }).click();
  await page.getByText(/Added 8 items from Masala box/).waitFor();
  await snap('02-kitchen');
});

test('leftover rice shows as "use today" and can be adjusted', async () => {
  const row = page.locator('.pantry-list li', { hasText: 'Leftover rice' });
  await row.getByText('1 day left').waitFor();
  await row.getByRole('button', { name: /One day less/ }).click();
  await row.getByText('Use today').waitFor();
});

test('home suggests dishes, flags leftovers to use up', async () => {
  await page.getByRole('button', { name: 'Cook', exact: true }).click();
  await page.getByText('Cook now').waitFor();
  await page.locator('.soon-banner').waitFor();
  const names = await page.locator('.dish-title').allInnerTexts();
  assert.ok(names.some(n => n.includes('Curd Rice')), names.join('|'));
  assert.ok(names.some(n => n.includes('Masala Omelette')), names.join('|'));
  await snap('03-home');
});

test('filters: veg only hides egg dishes', async () => {
  await page.getByRole('button', { name: 'Veg only' }).click();
  const names = await page.locator('.dish-title').allInnerTexts();
  assert.ok(!names.some(n => /Omelette|Egg/.test(n)), names.join('|'));
  await page.getByRole('button', { name: 'Veg only' }).click();
});

test('recipe page shows what you have and what is missing', async () => {
  await page.locator('.dish-card', { hasText: 'Curd Rice' }).first().click();
  await page.getByRole('heading', { name: /Curd Rice/ }).waitFor();
  await page.getByText(/Food safety/).waitFor();
  assert.ok(await page.locator('.ing-list li.have').count() >= 2);
  await snap('04-recipe');
});

test('missing items go to the shopping list', async () => {
  await page.goto(base + '#/recipe/palak_paneer');
  await page.getByRole('button', { name: /missing to shopping list/ }).click();
  await page.getByText(/to your shopping list/).waitFor();
  await page.getByRole('button', { name: 'List', exact: true }).click();
  await page.getByRole('heading', { name: 'Shopping list' }).waitFor();
  await page.locator('.shop-list li', { hasText: 'Spinach' }).waitFor();
  const wa = await page.getByRole('link', { name: 'Share list on WhatsApp' }).getAttribute('href');
  assert.match(wa, /^https:\/\/wa\.me\/\?text=Ballava%20shopping%20list/);
  // Tick spinach as bought -> moves into the kitchen.
  await page.locator('.shop-list li', { hasText: 'Spinach' }).getByRole('checkbox').check();
  await page.getByRole('button', { name: /I bought the ticked items/ }).click();
  await page.getByText(/Moved 1 item/).waitFor();
  await snap('05-shopping');
});

test('cook mode: steps, timer, whistle counter, Bachao, finish', async () => {
  await page.goto(base + '#/recipe/dal_tadka');
  await page.getByRole('button', { name: 'Start cooking' }).click();
  await page.getByText('Step 1 of 6').waitFor();
  // Step 1 has a 4-whistle pressure cooker counter.
  for (let k = 0; k < 4; k++) await page.getByRole('button', { name: 'I heard a whistle (+1)' }).click();
  await page.getByText(/enough whistles/).waitFor();
  await snap('06-cook-whistle');
  await page.getByRole('button', { name: 'Next ›' }).click();
  await page.getByRole('button', { name: 'Next ›' }).click();
  await page.getByText('Step 3 of 6').waitFor();
  await page.getByRole('button', { name: /Start 1-minute timer/ }).click();
  await page.locator('.timer').getByText(/0:5\d|1:00/).waitFor();
  await snap('07-cook-timer');
  // Bachao from inside cook mode.
  await page.getByRole('button', { name: /Bachao!/ }).click();
  await page.getByPlaceholder(/Search/).fill('salty');
  await page.getByRole('button', { name: 'Too much salt' }).click();
  await page.getByText(/Myth check/).waitFor();
  await snap('08-bachao');
  await page.getByRole('button', { name: 'Close' }).click();
  for (let k = 0; k < 3; k++) await page.getByRole('button', { name: 'Next ›' }).click();
  await page.getByRole('button', { name: 'Done cooking ✓' }).click();
  await page.getByRole('radio', { name: '5 stars' }).click();
  await snap('09-finish');
  await page.getByRole('button', { name: 'Save and finish' }).click();
  await page.locator('.stats').getByText('meals cooked').waitFor();
  assert.equal(await page.locator('.stats b').first().innerText(), '1');
});

test('family: a vegetarian Jain member changes suggestions', async () => {
  await page.getByRole('button', { name: 'More', exact: true }).click();
  await page.getByRole('button', { name: 'Family', exact: true }).click();
  await page.getByPlaceholder('e.g. Amma').fill('Amma');
  await page.locator('select').first().selectOption('veg');
  await page.getByLabel('Jain').check();
  await page.getByRole('button', { name: 'Add member' }).click();
  await page.getByText(/Added Amma/).waitFor();
  await snap('10-family');
  await page.getByRole('button', { name: 'Cook', exact: true }).click();
  await page.getByText(/suit everyone in your family/).waitFor();
  const names = await page.locator('.dish-title').allInnerTexts();
  assert.ok(!names.some(n => /Egg|Omelette|Chicken|Onion/.test(n)), names.join('|'));
});

test('AI Chef explains clearly that it is switched off', async () => {
  await page.getByRole('button', { name: '✨ AI Chef' }).click();
  await page.getByText('AI Chef is switched off').waitFor();
  await page.getByText(/ANTHROPIC_API_KEY/).waitFor();
});

test('data survives a page reload', async () => {
  await page.reload();
  await page.getByRole('button', { name: 'Kitchen', exact: true }).click();
  await page.locator('.pantry-list .p-name', { hasText: 'Tomato' }).waitFor();
});

test('no JavaScript errors happened anywhere', () => {
  assert.deepEqual(errors, []);
});
