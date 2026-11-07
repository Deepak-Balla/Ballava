// Tests for the server. Starts it on a random port, calls it, then stops it.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from '../server/server.mjs';

let server, base;
const realFetch = globalThis.fetch;

before(async () => {
  process.env.DB_PATH = ':memory:';
  delete process.env.ANTHROPIC_API_KEY;
  server = createServer();
  await new Promise(r => server.listen(0, r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => { globalThis.fetch = realFetch; server.close(); });

const post = (path, body) => realFetch(base + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });

test('health check', async () => {
  const r = await realFetch(base + '/api/health');
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { ok: true, ai: false, version: '1.0.0' });
});

test('serves the app and falls back to it for page links', async () => {
  const home = await realFetch(base + '/');
  assert.equal(home.status, 200);
  assert.match(await home.text(), /<div id="root">/);
  assert.equal((await realFetch(base + '/app.js')).headers.get('content-type'), 'text/javascript; charset=utf-8');
  assert.equal((await realFetch(base + '/some/page')).status, 200);
  assert.equal((await realFetch(base + '/missing.png')).status, 404);
});

test('cannot read files outside the app folder', async () => {
  for (const p of ['/../package.json', '/%2e%2e/package.json', '/..%2f..%2fpackage.json', '/%2e%2e%2f.env']) {
    const r = await realFetch(base + p);
    assert.notEqual(r.status, 200, p + ' should be blocked');
    assert.doesNotMatch(await r.text(), /"name": "ballava"/);
  }
});

test('parse, suggest, chat and rescue endpoints', async () => {
  const parsed = await (await post('/api/parse', { text: 'aloo, pyaz' })).json();
  assert.deepEqual(parsed.found.sort(), ['onion', 'potato']);
  const sug = await (await post('/api/suggest', { pantry: ['egg', 'onion', 'tomato', 'green_chilli'] })).json();
  assert.ok(sug.ready.some(r => r.id === 'masala_omelette'));
  const chat = await (await post('/api/chat', { text: 'leftover rice and dahi' })).json();
  assert.match(chat.reply, /Curd Rice/);
  const rescue = await (await post('/api/rescue', { text: 'too spicy' })).json();
  assert.equal(rescue[0].id, 'too_spicy');
});

test('bad requests get clear errors, not crashes', async () => {
  const bad = await realFetch(base + '/api/parse', { method: 'POST', body: '{not json' });
  assert.equal(bad.status, 400);
  assert.equal((await post('/api/nope', {})).status, 404);
  assert.equal((await realFetch(base + '/api/parse')).status, 405);
  const huge = await post('/api/parse', { text: 'x'.repeat(300 * 1024) });
  assert.equal(huge.status, 413);
});

test('AI endpoints say clearly when AI is off', async () => {
  const r = await post('/api/ai/invent', { pantry: ['egg'] });
  assert.equal(r.status, 503);
  assert.match((await r.json()).error, /ANTHROPIC_API_KEY/);
});

test('AI invent and scan work with a (simulated) Claude response', async () => {
  process.env.ANTHROPIC_API_KEY = 'test-key';
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url, body: JSON.parse(opts.body), headers: opts.headers });
    const isScan = JSON.parse(opts.body).messages[0].content[0]?.type === 'image';
    const text = isScan
      ? '{"ingredients": ["tomato", "paneer", "dragon fruit"]}'
      : 'Here you go: {"name":"Paneer Pepper Fry","time":20,"spice":2,"ingredients":[{"name":"paneer","quantity":"200 g"}],"steps":[{"text":"Fry it","minutes":3}],"why":"Pepper loves paneer"}';
    return new Response(JSON.stringify({ content: [{ type: 'text', text }] }), { status: 200 });
  };
  try {
    const inv = await (await post('/api/ai/invent', { pantry: ['Paneer'], household: [{ diet: 'veg' }], wish: 'quick' })).json();
    assert.equal(inv.recipe.name, 'Paneer Pepper Fry');
    assert.equal(calls[0].url, 'https://api.anthropic.com/v1/messages');
    assert.equal(calls[0].headers['x-api-key'], 'test-key');
    assert.match(calls[0].body.system, /Food safety/);
    assert.match(calls[0].body.messages[0].content, /Paneer/);

    const scan = await (await post('/api/ai/scan', { image: 'aGVsbG8=', mediaType: 'image/jpeg' })).json();
    assert.deepEqual(scan.found.sort(), ['paneer', 'tomato']);
    assert.deepEqual(scan.unknown, ['dragon fruit']);

    const badType = await post('/api/ai/scan', { image: 'aGVsbG8=', mediaType: 'text/html' });
    assert.equal(badType.status, 400);
  } finally {
    globalThis.fetch = realFetch;
    delete process.env.ANTHROPIC_API_KEY;
  }
});

test('AI errors are reported politely', async () => {
  process.env.ANTHROPIC_API_KEY = 'bad-key';
  globalThis.fetch = async () => new Response(JSON.stringify({ error: { message: 'invalid x-api-key' } }), { status: 401 });
  try {
    const r = await post('/api/ai/invent', { pantry: ['egg'] });
    assert.equal(r.status, 500);
    assert.match((await r.json()).error, /not valid/);
  } finally { globalThis.fetch = realFetch; delete process.env.ANTHROPIC_API_KEY; }
});

test('AI rate limit protects the bill', async () => {
  process.env.ANTHROPIC_API_KEY = 'k'; process.env.AI_RATE_LIMIT = '2';
  globalThis.fetch = async () => new Response(JSON.stringify({ content: [{ type: 'text', text: '{"ingredients": []}' }] }));
  try {
    const statuses = [];
    for (let i = 0; i < 4; i++) statuses.push((await post('/api/ai/scan', { image: 'aGk=', mediaType: 'image/png' })).status);
    assert.ok(statuses.includes(429), statuses.join(','));
  } finally { globalThis.fetch = realFetch; delete process.env.ANTHROPIC_API_KEY; delete process.env.AI_RATE_LIMIT; }
});
