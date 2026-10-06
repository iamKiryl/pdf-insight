// Copies the pinned Tesseract.js worker, WASM cores and Polish/English language data from
// node_modules into public/ocr/ (git-ignored), so OCR assets are served from this site (GitHub
// Pages) and never from a third-party CDN. Versions are pinned in package.json.
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const modules = join(root, 'node_modules');
const target = join(root, 'public', 'ocr');
const files = [
  ['tesseract.js/dist/worker.min.js', 'worker.min.js'],
  // LSTM-only cores (the variant is chosen in the worker by WASM feature detection).
  [
    'tesseract.js-core/tesseract-core-relaxedsimd-lstm.wasm.js',
    'core/tesseract-core-relaxedsimd-lstm.wasm.js',
  ],
  ['tesseract.js-core/tesseract-core-simd-lstm.wasm.js', 'core/tesseract-core-simd-lstm.wasm.js'],
  ['tesseract.js-core/tesseract-core-lstm.wasm.js', 'core/tesseract-core-lstm.wasm.js'],
  ['@tesseract.js-data/pol/4.0.0_best_int/pol.traineddata.gz', 'lang/pol.traineddata.gz'],
  ['@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz', 'lang/eng.traineddata.gz'],
];
for (const [from, to] of files) {
  mkdirSync(dirname(join(target, to)), { recursive: true });
  copyFileSync(join(modules, from), join(target, to));
}
