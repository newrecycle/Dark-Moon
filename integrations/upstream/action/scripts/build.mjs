import { build } from 'esbuild';
import { readFileSync } from 'node:fs';

const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));

await build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  platform: 'node',
  target: 'node20',
  format: 'cjs',
  outfile: 'dist/index.js',
  sourcemap: false,
  minify: false,
  banner: {
    js: `// Darkmoon Action v${pkg.version} — bundled, do not edit by hand.`,
  },
  logLevel: 'info',
});

console.log('Bundled dist/index.js');
