// Ballava database: one SQLite file, using the driver built into Node, so nothing to install.
// The file lives at data/ballava.db (change it with DB_PATH). Back this file up.
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

const SCHEMA = `
CREATE TABLE IF NOT EXISTS households (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, invite_code TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE, phone TEXT UNIQUE, password_hash TEXT,
  role TEXT NOT NULL DEFAULT 'user', household_id TEXT REFERENCES households(id),
  consent_at INTEGER, created_at INTEGER NOT NULL, last_seen INTEGER, disabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  scope TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS otps (
  phone TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS state (
  household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE, key TEXT NOT NULL, value TEXT NOT NULL,
  version INTEGER NOT NULL, updated_at INTEGER NOT NULL, PRIMARY KEY (household_id, key));
CREATE TABLE IF NOT EXISTS polls (
  token TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  title TEXT NOT NULL, date TEXT NOT NULL, slot TEXT NOT NULL, options TEXT NOT NULL, created_at INTEGER NOT NULL, closes_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS votes (
  poll_token TEXT NOT NULL REFERENCES polls(token) ON DELETE CASCADE, voter TEXT NOT NULL, option_id TEXT NOT NULL, name TEXT,
  PRIMARY KEY (poll_token, voter));
CREATE TABLE IF NOT EXISTS recipes (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, data TEXT NOT NULL, live TEXT, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS hidden_recipes (id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS content (kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (kind, id));
CREATE TABLE IF NOT EXISTS ai_usage (day TEXT NOT NULL, who TEXT NOT NULL, calls INTEGER NOT NULL, PRIMARY KEY (day, who));
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id TEXT NOT NULL, action TEXT NOT NULL, target TEXT, at INTEGER NOT NULL);
`;

let db;
export function getDb() {
  if (db) return db;
  const path = process.env.DB_PATH || join(ROOT, 'data', 'ballava.db');
  if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
  db = new DatabaseSync(path);
  db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');
  db.exec(SCHEMA);
  return db;
}

export const one = (sql, ...args) => getDb().prepare(sql).get(...args);
export const all = (sql, ...args) => getDb().prepare(sql).all(...args);
export const run = (sql, ...args) => getDb().prepare(sql).run(...args);

export function transaction(fn) {
  const d = getDb();
  d.exec('BEGIN');
  try { const out = fn(); d.exec('COMMIT'); return out; } catch (e) { d.exec('ROLLBACK'); throw e; }
}
