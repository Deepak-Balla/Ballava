// Sign-in for users and admins. Passwords are hashed with scrypt, and session tokens are stored
// only as hashes, so a leaked database file does not hand out working logins.
import { scrypt as scryptCb, randomBytes, randomInt, randomUUID, createHash, timingSafeEqual } from 'node:crypto';
import { promisify } from 'node:util';
import { one, run } from './db.mjs';

const scrypt = promisify(scryptCb);
const DAY = 86400000;
export const USER_COOKIE = 'ballava_session';
export const ADMIN_COOKIE = 'ballava_admin';
const SESSION_MS = { user: 30 * DAY, admin: DAY / 2 };

export const fail = (status, message) => Object.assign(new Error(message), { status });
const sha = s => createHash('sha256').update(s).digest('hex');

export async function hashPassword(password) {
  const salt = randomBytes(16);
  const hash = await scrypt(password, salt, 32);
  return `s1$${salt.toString('hex')}$${hash.toString('hex')}`;
}

export async function checkPassword(password, stored) {
  // Still does the work when there is no account, so timing does not reveal which emails exist.
  const [, saltHex, hashHex] = (stored || 's1$00$00').split('$');
  const hash = await scrypt(String(password), Buffer.from(saltHex, 'hex'), 32);
  return !!stored && timingSafeEqual(hash, Buffer.from(hashHex, 'hex'));
}

// -------------------------------------------------------------- simple limits
const buckets = new Map();
export function limited(key, max, windowMs) {
  const now = Date.now();
  const list = (buckets.get(key) || []).filter(t => now - t < windowMs);
  if (list.length >= max) { buckets.set(key, list); return true; }
  list.push(now); buckets.set(key, list);
  return false;
}
export const clearLimit = key => buckets.delete(key);

// -------------------------------------------------------------- sessions
function parseCookies(req) {
  const out = {};
  for (const part of (req.headers.cookie || '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  return out;
}

const isSecure = req => req.socket.encrypted || req.headers['x-forwarded-proto'] === 'https';

function cookie(req, name, value, maxAgeMs, path, sameSite) {
  return `${name}=${value}; Path=${path}; HttpOnly; SameSite=${sameSite}; Max-Age=${Math.floor(maxAgeMs / 1000)}${isSecure(req) ? '; Secure' : ''}`;
}

export function startSession(req, res, userId, scope = 'user') {
  const token = randomBytes(32).toString('hex');
  const ms = SESSION_MS[scope];
  run('INSERT INTO sessions (token_hash, user_id, scope, expires_at) VALUES (?, ?, ?, ?)', sha(token), userId, scope, Date.now() + ms);
  res.setHeader('set-cookie', scope === 'admin' ? cookie(req, ADMIN_COOKIE, token, ms, '/api/admin', 'Strict') : cookie(req, USER_COOKIE, token, ms, '/', 'Lax'));
}

export function endSession(req, res, scope = 'user') {
  const name = scope === 'admin' ? ADMIN_COOKIE : USER_COOKIE;
  const token = parseCookies(req)[name];
  if (token) run('DELETE FROM sessions WHERE token_hash = ?', sha(token));
  res.setHeader('set-cookie', scope === 'admin' ? cookie(req, name, '', 0, '/api/admin', 'Strict') : cookie(req, name, '', 0, '/', 'Lax'));
}

// After a password change: sign out everywhere else, but keep this browser signed in.
export function endOtherSessions(req, userId, scope = 'user') {
  const token = parseCookies(req)[scope === 'admin' ? ADMIN_COOKIE : USER_COOKIE] || '';
  run('DELETE FROM sessions WHERE user_id = ? AND scope = ? AND token_hash != ?', userId, scope, sha(token));
}

function sessionUser(req, name, scope) {
  const token = parseCookies(req)[name];
  if (!token) return null;
  return one(`SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
    WHERE s.token_hash = ? AND s.scope = ? AND s.expires_at > ? AND u.disabled = 0`, sha(token), scope, Date.now()) || null;
}

export const currentUser = req => sessionUser(req, USER_COOKIE, 'user');

export function requireUser(req) {
  const user = currentUser(req);
  if (!user) throw fail(401, 'Please sign in first.');
  return user;
}

// Admin pages use their own cookie and session type, and the role is checked on every call.
export function requireAdmin(req) {
  const user = sessionUser(req, ADMIN_COOKIE, 'admin');
  if (!user || user.role !== 'admin') throw fail(401, 'Admin sign-in required.');
  return user;
}

// -------------------------------------------------------------- phone codes
export function normalizePhone(raw) {
  const s = String(raw || '').replace(/[\s()-]/g, '');
  if (/^[6-9]\d{9}$/.test(s)) return '+91' + s;
  if (/^\+[1-9]\d{7,14}$/.test(s)) return s;
  return null;
}

const devOtp = () => process.env.OTP_DEV_MODE === '1' && process.env.NODE_ENV !== 'production';
const twilioReady = () => !!(process.env.TWILIO_SID && process.env.TWILIO_TOKEN && process.env.TWILIO_FROM);
export const authConfig = () => ({ phone: twilioReady() || devOtp(), devOtp: devOtp() && !twilioReady() });

async function sendSms(phone, text) {
  const { TWILIO_SID: sid, TWILIO_TOKEN: token, TWILIO_FROM: from } = process.env;
  const res = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`, {
    method: 'POST',
    headers: { authorization: 'Basic ' + Buffer.from(`${sid}:${token}`).toString('base64'), 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ To: phone, From: from, Body: text }),
  });
  if (!res.ok) throw fail(502, 'We could not send the code. Please try again.');
}

export async function requestOtp(rawPhone, ip) {
  const phone = normalizePhone(rawPhone);
  if (!phone) throw fail(400, 'Please enter a valid mobile number.');
  if (!authConfig().phone) throw fail(503, 'Phone sign-in is not set up on this server yet. Please use email.');
  if (limited('otp:' + phone, 5, 3600000) || limited('otpip:' + ip, 20, 3600000)) throw fail(429, 'Too many codes requested. Please try again later.');
  const code = String(randomInt(100000, 1000000));
  run(`INSERT INTO otps (phone, code_hash, expires_at, attempts) VALUES (?, ?, ?, 0)
    ON CONFLICT(phone) DO UPDATE SET code_hash = excluded.code_hash, expires_at = excluded.expires_at, attempts = 0`,
  phone, sha(phone + code), Date.now() + 600000);
  if (twilioReady()) { await sendSms(phone, `Your Ballava code is ${code}. It expires in 10 minutes.`); return { sent: true }; }
  console.log(`[ballava] Dev sign-in code for ${phone}: ${code}`);
  return { sent: true, devCode: code };
}

export function checkOtp(rawPhone, code) {
  const phone = normalizePhone(rawPhone);
  const row = phone && one('SELECT * FROM otps WHERE phone = ?', phone);
  if (!row || row.expires_at < Date.now()) throw fail(400, 'That code has expired. Please ask for a new one.');
  if (row.attempts >= 5) { run('DELETE FROM otps WHERE phone = ?', phone); throw fail(429, 'Too many wrong tries. Please ask for a new code.'); }
  if (!timingSafeEqual(Buffer.from(sha(phone + String(code || ''))), Buffer.from(row.code_hash))) {
    run('UPDATE otps SET attempts = attempts + 1 WHERE phone = ?', phone);
    throw fail(400, 'That code is not right. Please check and try again.');
  }
  return phone;
}

export const clearOtp = phone => run('DELETE FROM otps WHERE phone = ?', phone);

// -------------------------------------------------------------- households
const CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
const makeInviteCode = () => Array.from({ length: 8 }, () => CODE_ALPHABET[randomInt(CODE_ALPHABET.length)]).join('');

function createHousehold(name) {
  const id = randomUUID();
  run('INSERT INTO households (id, name, invite_code, created_at) VALUES (?, ?, ?, ?)', id, name, makeInviteCode(), Date.now());
  return id;
}

export function createUser({ name, email = null, phone = null, passwordHash = null, role = 'user', consent = false }) {
  const id = randomUUID();
  const householdId = role === 'admin' ? null : createHousehold(`${name}'s family`);
  run(`INSERT INTO users (id, name, email, phone, password_hash, role, household_id, consent_at, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`, id, name, email, phone, passwordHash, role, householdId, consent ? Date.now() : null, Date.now());
  return id;
}
