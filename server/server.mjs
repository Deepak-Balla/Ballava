// Ballava server: serves the app (dist/) and a small API.
// Uses only Node's built-in modules, so it needs no installation.
// Start with:  npm start      then open http://localhost:3000
import { createServer as httpServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { join, normalize, extname, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { suggest, parseIngredients, chatReply, findRescue } from '../shared/engine.mjs';
import { inventRecipe, scanPhoto, aiConfig } from './ai.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist');

// Load settings from the .env file if there is one (Node 20.12+ / 21.7+).
try { process.loadEnvFile(join(ROOT, '.env')); } catch { /* no .env file: fine */ }

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.ico': 'image/x-icon', '.map': 'application/json',
};

const send = (res, status, data, headers = {}) => {
  const body = typeof data === 'string' ? data : JSON.stringify(data);
  res.writeHead(status, { 'content-type': typeof data === 'string' ? 'text/plain; charset=utf-8' : 'application/json', ...headers });
  res.end(body);
};

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    let size = 0, tooBig = false; const chunks = [];
    req.on('data', c => {
      size += c.length;
      if (size > limit) { tooBig = true; chunks.length = 0; if (size > limit * 8) req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      if (tooBig) return reject(Object.assign(new Error('Request too large'), { status: 413 }));
      if (!chunks.length) return resolve({});
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); } catch { reject(Object.assign(new Error('Invalid JSON'), { status: 400 })); }
    });
    req.on('error', reject);
  });
}

// Simple protection so nobody can run up the AI bill: max N AI calls per minute per visitor.
const hits = new Map();
function rateLimited(ip, max = Number(process.env.AI_RATE_LIMIT || 10)) {
  const now = Date.now();
  const list = (hits.get(ip) || []).filter(t => now - t < 60000);
  list.push(now); hits.set(ip, list);
  return list.length > max;
}

async function handleApi(req, res, path) {
  const ip = req.socket.remoteAddress || 'x';
  if (req.method === 'GET' && path === '/api/health') {
    return send(res, 200, { ok: true, ai: !!aiConfig().key, version: '1.0.0' });
  }
  if (req.method !== 'POST') return send(res, 405, { error: 'Use POST' });
  const body = await readBody(req, path === '/api/ai/scan' ? 8 * 1024 * 1024 : 200 * 1024);

  switch (path) {
    case '/api/parse':
      return send(res, 200, parseIngredients(String(body.text || '')));
    case '/api/suggest': {
      const pantry = Array.isArray(body.pantry) ? body.pantry.map(p => (typeof p === 'string' ? { id: p } : p)) : [];
      const { ready, almost } = suggest({ pantry, members: body.members || [], filters: body.filters || {} });
      const slim = r => ({ id: r.recipe.id, name: r.recipe.name, time: r.recipe.time, missing: r.missing, usesSoon: r.usesSoon, notes: r.notes });
      return send(res, 200, { ready: ready.map(slim), almost: almost.map(slim) });
    }
    case '/api/chat':
      // The same brain a WhatsApp bot would use: text in, short reply out.
      return send(res, 200, chatReply(String(body.text || '').slice(0, 1000)));
    case '/api/rescue':
      return send(res, 200, findRescue(String(body.text || '')));
    case '/api/ai/invent':
      if (rateLimited(ip)) return send(res, 429, { error: 'Too many AI requests. Please wait a minute.' });
      return send(res, 200, { recipe: await inventRecipe(body) });
    case '/api/ai/scan': {
      if (rateLimited(ip)) return send(res, 429, { error: 'Too many AI requests. Please wait a minute.' });
      const names = await scanPhoto(body);
      const parsed = parseIngredients(names.join(', '));
      return send(res, 200, { names, found: parsed.found, unknown: parsed.unknown });
    }
    default:
      return send(res, 404, { error: 'Unknown API route' });
  }
}

async function serveFile(res, urlPath) {
  let rel = decodeURIComponent(urlPath.split('?')[0]);
  if (rel.endsWith('/')) rel += 'index.html';
  const file = normalize(join(DIST, rel));
  if (file !== DIST && !file.startsWith(DIST + sep)) return send(res, 403, 'Forbidden'); // blocks ../../ tricks
  try {
    const s = await stat(file);
    if (!s.isFile()) throw new Error('not file');
    const data = await readFile(file);
    const long = /\.(js|css|png|svg)$/.test(file) && !file.endsWith('sw.js');
    res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream', 'cache-control': long ? 'public, max-age=86400' : 'no-cache' });
    return res.end(data);
  } catch {
    if (extname(file)) return send(res, 404, 'Not found');
    try {
      const html = await readFile(join(DIST, 'index.html'));
      res.writeHead(200, { 'content-type': TYPES['.html'], 'cache-control': 'no-cache' });
      return res.end(html);
    } catch {
      return send(res, 500, 'The app is not built yet. Run: npm run build');
    }
  }
}

export function createServer() {
  return httpServer(async (req, res) => {
    const url = new URL(req.url, 'http://x');
    res.setHeader('x-content-type-options', 'nosniff');
    res.setHeader('referrer-policy', 'same-origin');
    try {
      if (url.pathname.startsWith('/api/')) return await handleApi(req, res, url.pathname);
      if (req.method !== 'GET' && req.method !== 'HEAD') return send(res, 405, 'Method not allowed');
      return await serveFile(res, url.pathname);
    } catch (err) {
      const status = err.status || 500;
      if (status >= 500) console.error('[ballava]', err.message);
      if (!res.headersSent) send(res, status, { error: status >= 500 && !err.status ? 'Something went wrong on the server.' : err.message });
    }
  });
}

// Start only when run directly (tests import createServer instead).
if (process.argv[1] && fileURLToPath(import.meta.url) === normalize(process.argv[1])) {
  const port = Number(process.env.PORT || 3000);
  createServer().listen(port, () => {
    console.log(`\n  Ballava is running!  Open  http://localhost:${port}  in your browser.`);
    console.log(`  AI Chef: ${aiConfig().key ? 'ON' : 'off (add ANTHROPIC_API_KEY to .env to switch it on)'}`);
    console.log('  Press Ctrl+C to stop.\n');
  });
}
