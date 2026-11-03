// Developer mode: rebuilds the app whenever you save a file, and restarts the server.
// Run with:  npm run dev     then open http://localhost:3000 (refresh after each change)
import { spawn } from 'node:child_process';

const run = (args) => spawn(process.execPath, args, { stdio: 'inherit' });
const procs = [run(['build.mjs', '--watch']), run(['--watch', 'server/server.mjs'])];
const stop = () => { procs.forEach(p => p.kill()); process.exit(0); };
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
