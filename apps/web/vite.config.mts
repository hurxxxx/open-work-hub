/// <reference types='vitest' />
import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { nxViteTsPaths } from '@nx/vite/plugins/nx-tsconfig-paths.plugin';
import { nxCopyAssetsPlugin } from '@nx/vite/plugins/nx-copy-assets.plugin';

const apiProxyTarget = process.env.DOOWON_WEB_API_PROXY_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/apps/web',
  server: {
    port: 4200,
    host: '0.0.0.0',
    allowedHosts: ['dwdcc.lumejs.com'],
    proxy: {
      '/api': {
        target: apiProxyTarget,
        ws: true,
      },
    },
    fs: {
      // Allow serving files from the repo root so learning/*.md (outside
      // apps/web) can be imported via import.meta.glob.
      allow: ['..', '../..'],
    },
  },
  preview: {
    port: 4200,
    host: '0.0.0.0',
    allowedHosts: ['dwdcc.lumejs.com'],
    proxy: {
      '/api': {
        target: apiProxyTarget,
        ws: true,
      },
    },
  },
  resolve: {
    alias: {
      '@ai-do/ui/styles.css': path.resolve(import.meta.dirname, '../../packages/ui/styles.css'),
      '@/src': path.resolve(import.meta.dirname, 'src'),
    },
  },
  plugins: [react(), tailwindcss(), nxViteTsPaths(), nxCopyAssetsPlugin(['*.md'])],
  // Uncomment this if you are using workers.
  // worker: {
  //   plugins: () => [ nxViteTsPaths() ],
  // },
  build: {
    outDir: '../../dist/apps/web',
    emptyOutDir: true,
    reportCompressedSize: true,
    chunkSizeWarningLimit: 2200,
    commonjsOptions: {
      transformMixedEsModules: true,
    },
  },
  test: {
    name: 'web',
    watch: false,
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['{src,tests}/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
    reporters: ['default'],
    coverage: {
      reportsDirectory: '../../coverage/apps/web',
      provider: 'v8' as const,
    },
  },
}));
