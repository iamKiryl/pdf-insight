/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// GitHub Pages serves the app from /<repo>/. CI sets VITE_BASE_PATH; local dev uses "/".
const base = process.env.VITE_BASE_PATH ?? '/';
const contractsDir = fileURLToPath(new URL('../contracts', import.meta.url));

export default defineConfig({
  base,
  plugins: [react()],
  build: { sourcemap: false, target: 'es2022' },
  server: { fs: { allow: ['.', contractsDir] } },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
});
