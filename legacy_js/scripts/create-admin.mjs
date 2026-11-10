// Creates an admin login, or sets a new password if you forgot it.
//   Run:  npm run create-admin -- you@example.com
// You are asked to type the new password (it shows as * while you type).
// Press Enter without typing anything to get a strong random password instead.
// Admins sign in at /admin.
import { randomBytes } from 'node:crypto';
import { createInterface } from 'node:readline';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { one, run } from '../server/db.mjs';
import { hashPassword, createUser } from '../server/auth.mjs';

try { process.loadEnvFile(join(dirname(fileURLToPath(import.meta.url)), '..', '.env')); } catch { /* no .env file: fine */ }

const email = String(process.argv[2] || '').trim().toLowerCase();
if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
  console.error('\n  Please give an email address:  npm run create-admin -- you@example.com\n');
  process.exit(1);
}
const existing = one('SELECT id, role FROM users WHERE email = ?', email);
if (existing && existing.role !== 'admin') {
  console.error('\n  That email already belongs to a normal user. Please use a separate email for admin.\n');
  process.exit(1);
}

const cancel = () => { console.log('\n\n  Cancelled. Nothing was changed.\n'); process.exit(1); };

async function choosePassword() {
  if (process.env.ADMIN_PASSWORD) return { password: process.env.ADMIN_PASSWORD, typed: true };
  const interactive = process.stdin.isTTY || process.argv.includes('--ask');
  if (!interactive) return { password: randomBytes(12).toString('base64url'), typed: false };

  const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: !!process.stdin.isTTY });
  // While typing a password, each character shows as * instead.
  const write = rl._writeToOutput?.bind(rl);
  if (write) rl._writeToOutput = s => (rl.hide && !/[\r\n]/.test(s) ? rl.output.write('*'.repeat(s.length)) : write(s));
  // Keep every line that arrives, even if it comes before we ask for it (fast typing or pasting).
  const lines = [], waiting = [];
  rl.on('line', l => (waiting.length ? waiting.shift()(l) : lines.push(l)));
  rl.on('SIGINT', cancel);
  rl.on('close', () => { while (waiting.length) waiting.shift()(null); });
  const ask = question => {
    process.stdout.write(question);
    rl.hide = true;
    return new Promise(resolve => {
      const done = answer => { rl.hide = false; if (answer === null) cancel(); else resolve(answer); };
      lines.length ? done(lines.shift()) : waiting.push(done);
    });
  };
  console.log(`\n  Setting the admin password for ${email}`);
  console.log('  Type a new password (at least 12 characters), or just press Enter for a random one.\n');
  try {
    for (;;) {
      const first = await ask('  New password: ');
      if (!first) return { password: randomBytes(12).toString('base64url'), typed: false };
      if (first.length < 12) { console.log('  That is too short. Please use at least 12 characters.\n'); continue; }
      const again = await ask('  Type it again: ');
      if (again === first) return { password: first, typed: true };
      console.log('  The two passwords did not match. Please try again.\n');
    }
  } finally { rl.close(); }
}

const { password, typed } = await choosePassword();
const passwordHash = await hashPassword(password);
if (existing) {
  run('UPDATE users SET password_hash = ?, disabled = 0 WHERE id = ?', passwordHash, existing.id);
  run('DELETE FROM sessions WHERE user_id = ?', existing.id);
} else createUser({ name: 'Admin', email, passwordHash, role: 'admin' });

console.log('\n  ==============================================');
console.log(`  Admin ${existing ? 'password changed' : 'created'}.`);
console.log('  Sign in at  http://localhost:3000/admin');
console.log(`  Email:     ${email}`);
console.log(typed ? '  Password:  the one you just typed' : `  Password:  ${password}`);
console.log('  ==============================================');
if (!typed) console.log('  Save this password now. It is not shown again.');
console.log('');
