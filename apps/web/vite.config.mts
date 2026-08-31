/// <reference types='vitest' />
import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { nxViteTsPaths } from '@nx/vite/plugins/nx-tsconfig-paths.plugin';
import { nxCopyAssetsPlugin } from '@nx/vite/plugins/nx-copy-assets.plugin';

const apiProxyTarget = process.env.OPEN_WORK_HUB_WEB_API_PROXY_TARGET ?? 'http://127.0.0.1:8001';
const drawioProxyTarget =
  process.env.OPEN_WORK_HUB_WEB_DRAWIO_PROXY_TARGET ??
  `http://127.0.0.1:${process.env.OPEN_WORK_HUB_DRAWIO_PORT ?? 18082}`;
const webDevPort = Number(process.env.OPEN_WORK_HUB_WEB_DEV_PORT ?? 4200);
const webDevAllowedHosts = (process.env.OPEN_WORK_HUB_WEB_DEV_ALLOWED_HOSTS ?? '')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean);
const webBuildOutDir = '../../dist/apps/web';
const drawioBrowserUrl =
  process.env.VITE_OPEN_WORK_HUB_DRAWIO_URL ?? process.env.OPEN_WORK_HUB_DRAWIO_SERVER_URL ?? '';
const drawioBrowserPort = String(process.env.OPEN_WORK_HUB_DRAWIO_PORT ?? 18082);
const bentoBrowserUrl =
  process.env.VITE_OPEN_WORK_HUB_BENTO_URL ?? process.env.OPEN_WORK_HUB_BENTO_SERVER_URL ?? '';
const bentoBrowserPort = String(process.env.OPEN_WORK_HUB_BENTO_PORT ?? 18084);
const apiProxyTimeoutMs = 0;
const drawioProxyTimeoutMs = 0;
const drawioProxyHeaders = {
  'X-Forwarded-Prefix': '/drawio',
};
const rewriteDrawioProxyPath = (requestPath: string) =>
  requestPath.replace(/^\/drawio(?=\/|$)/, '') || '/';

export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/apps/web',
  define: {
    __VUE_OPTIONS_API__: true,
    __VUE_PROD_DEVTOOLS__: false,
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false,
    'import.meta.env.VITE_OPEN_WORK_HUB_DRAWIO_PORT': JSON.stringify(drawioBrowserPort),
    'import.meta.env.VITE_OPEN_WORK_HUB_DRAWIO_URL': JSON.stringify(drawioBrowserUrl),
    'import.meta.env.VITE_OPEN_WORK_HUB_BENTO_PORT': JSON.stringify(bentoBrowserPort),
    'import.meta.env.VITE_OPEN_WORK_HUB_BENTO_URL': JSON.stringify(bentoBrowserUrl),
  },
  server: {
    port: webDevPort,
    host: process.env.OPEN_WORK_HUB_WEB_DEV_HOST ?? '127.0.0.1',
    allowedHosts: webDevAllowedHosts,
    proxy: {
      '/healthz': {
        target: apiProxyTarget,
        timeout: apiProxyTimeoutMs,
        proxyTimeout: apiProxyTimeoutMs,
      },
      '/readyz': {
        target: apiProxyTarget,
        timeout: apiProxyTimeoutMs,
        proxyTimeout: apiProxyTimeoutMs,
      },
      '/api': {
        target: apiProxyTarget,
        timeout: apiProxyTimeoutMs,
        proxyTimeout: apiProxyTimeoutMs,
        ws: true,
      },
      '/drawio': {
        target: drawioProxyTarget,
        changeOrigin: true,
        headers: drawioProxyHeaders,
        timeout: drawioProxyTimeoutMs,
        proxyTimeout: drawioProxyTimeoutMs,
        rewrite: rewriteDrawioProxyPath,
      },
    },
  },
  preview: {
    port: webDevPort,
    host: process.env.OPEN_WORK_HUB_WEB_DEV_HOST ?? '127.0.0.1',
    allowedHosts: webDevAllowedHosts,
    proxy: {
      '/healthz': {
        target: apiProxyTarget,
        timeout: apiProxyTimeoutMs,
        proxyTimeout: apiProxyTimeoutMs,
      },
      '/readyz': {
        target: apiProxyTarget,
        timeout: apiProxyTimeoutMs,
        proxyTimeout: apiProxyTimeoutMs,
      },
      '/api': {
        target: apiProxyTarget,
        timeout: apiProxyTimeoutMs,
        proxyTimeout: apiProxyTimeoutMs,
        ws: true,
      },
      '/drawio': {
        target: drawioProxyTarget,
        changeOrigin: true,
        headers: drawioProxyHeaders,
        timeout: drawioProxyTimeoutMs,
        proxyTimeout: drawioProxyTimeoutMs,
        rewrite: rewriteDrawioProxyPath,
      },
    },
  },
  resolve: {
    alias: {
      '@open-work-hub/ui/styles.css': path.resolve(import.meta.dirname, '../../packages/ui/styles.css'),
      '@/src': path.resolve(import.meta.dirname, 'src'),
    },
  },
  plugins: [react(), tailwindcss(), nxViteTsPaths(), nxCopyAssetsPlugin(['*.md'])],
  optimizeDeps: {
    include: ['@hyunbinseo/holidays-kr/all'],
  },
  // Uncomment this if you are using workers.
  // worker: {
  //   plugins: () => [ nxViteTsPaths() ],
  // },
  build: {
    outDir: webBuildOutDir,
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
