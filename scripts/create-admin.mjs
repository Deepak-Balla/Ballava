// Creates (or resets) an admin login.   Run:  npm run create-admin -- you@example.com
// A strong password is generated and shown once. Admins sign in at /admin.
import { randomBytes } from 'node:crypto';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { one, run } from '../server/db.mjs';
import { hashPassword, createUser } from '../server/auth.mjs';

try { process.loadEnvFile(join(dirname(fileURLToPath(import.meta.url)), '..', '.env')); } catch { /* no .env file: fine */ }

const email = String(process.argv[2] || '').trim().toLowerCase();
if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
  console.error('Please give an email address:  npm run create-admin -- you@example.com');
  process.exit(1);
}
const password = process.env.ADMIN_PASSWORD || randomBytes(12).toString('base64url');
const passwordHash = await hashPassword(password);
const existing = one('SELECT id, role FROM users WHERE email = ?', email);
if (existing && existing.role !== 'admin') {
  console.error('That email already belongs to a normal user. Please use a separate email for admin.');
  process.exit(1);
}
if (existing) {
  run('UPDATE users SET password_hash = ?, disabled = 0 WHERE id = ?', passwordHash, existing.id);
  run('DELETE FROM sessions WHERE user_id = ?', existing.id);
} else createUser({ name: 'Admin', email, passwordHash, role: 'admin' });
console.log(`\n  Admin ready.\n  Sign in at /admin\n  Email:    ${email}\n  Password: ${password}\n\n  Save this password now. It is not shown again.\n`);
