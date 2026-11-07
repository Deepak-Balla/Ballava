// Build script: turns the source code in src/ into a ready-to-serve website in dist/.
// Run with:  npm run build      (or  npm run build -- --watch  while editing)
import { build, context } from 'esbuild';
import { cpSync, mkdirSync, readFileSync, writeFileSync, readdirSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';

const watch = process.argv.includes('--watch');
const out = 'dist';
const stamp = Date.now().toString(36);

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

function copyPublic() {
  for (const f of readdirSync('public')) {
    const src = join('public', f), dst = join(out, f);
    if (/\.(html|js|webmanifest)$/.test(f)) writeFileSync(dst, readFileSync(src, 'utf8').replaceAll('__BUILD__', stamp));
    else cpSync(src, dst);
  }
}

const options = {
  entryPoints: { app: 'src/main.jsx', admin: 'src/admin/main.jsx' },
  bundle: true,
  outdir: out,
  minify: !watch,
  sourcemap: watch,
  jsx: 'automatic',
  target: ['es2020', 'chrome90', 'safari15'],
  define: { 'process.env.NODE_ENV': watch ? '"development"' : '"production"' },
  logLevel: 'info',
};

copyPublic();
if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log('Watching for changes… (Ctrl+C to stop)');
} else {
  await build(options);
  if (!existsSync(join(out, 'icon-192.png'))) console.warn('Note: PNG icons missing; run `node scripts/make-icons.mjs` once.');
  console.log(`Built into ${out}/ (version ${stamp})`);
}
