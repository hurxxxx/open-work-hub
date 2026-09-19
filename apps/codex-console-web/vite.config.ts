import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@open-work-hub/ui/styles.css': fileURLToPath(
        new URL('../../packages/ui/styles.css', import.meta.url),
      ),
      '@open-work-hub/ui': fileURLToPath(
        new URL('../../packages/ui/src/index.ts', import.meta.url),
      ),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 19366,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:19365' },
  },
  build: { outDir: 'dist', chunkSizeWarningLimit: 1500 },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.{ts,tsx}'],
    setupFiles: ['src/test-setup.ts'],
  },
});
