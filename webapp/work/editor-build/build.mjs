// Reproducible build of the editor bundle: pinned inputs (package-lock.json),
// one esbuild call, deterministic output (no source map, no minification —
// the bundle is readable and diffable), and the SHA-256 written beside it
// so the suite can assert the runtime asset is the one this recipe makes.
import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, '../vendor/prosemirror.js');
mkdirSync(path.dirname(out), { recursive: true });
await build({
  entryPoints: [path.join(here, 'src/entry.js')],
  bundle: true, format: 'esm', platform: 'browser', target: ['es2020'],
  outfile: out, minify: false, sourcemap: false, legalComments: 'inline', logLevel: 'info',
  banner: { js: '// Built from webapp/work/editor-build (npm ci && npm run build). Pinned versions are in package-lock.json. Do not edit by hand.' },
});
const bytes = readFileSync(out);
const sha = createHash('sha256').update(bytes).digest('hex');
const versions = JSON.parse(readFileSync(path.join(here, 'package.json'), 'utf8')).devDependencies;
const record = [
  `# The editor bundle, as built. Regenerate with: cd webapp/work/editor-build && npm ci && npm run build`,
  `sha256 ${sha}  webapp/work/vendor/prosemirror.js`,
  `bytes ${bytes.length}`,
  ...Object.entries(versions).map(([k, v]) => `${k} ${v}`),
  '',
].join('\n');
writeFileSync(path.resolve(here, '../../../docs/editor-bundle.sha256'), record);
console.log('bundle', bytes.length, 'bytes, sha256', sha.slice(0, 16) + '…');
