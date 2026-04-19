import { defineConfig, devices } from '@playwright/test';

// E2E suite for the web app. Runs against the Vite dev server on port 4200.
// First-time setup: `pnpm exec playwright install chromium`.
// Run:            `pnpm e2e` (or `pnpm e2e -- --ui` for the Playwright UI).
//
// Tests stub the auth and workspace bootstrap endpoints via page.route so they
// don't require a live API. Only chromium runs by default — extend projects
// below if we ever need cross-browser coverage.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  forbidOnly: Boolean(process.env.CI),
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4200',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: devices['Desktop Chrome'],
    },
  ],
  webServer: {
    // Boot the vite dev server only if nothing is already listening on 4200.
    // Locally this lets you keep `./dev.sh` running in another terminal.
    command: 'pnpm nx dev web',
    url: 'http://127.0.0.1:4200',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
