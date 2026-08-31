import { accessSync, constants } from 'node:fs';
import { delimiter, join } from 'node:path';
import { chromium, defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:4200';
const webServerCommand = process.env.PLAYWRIGHT_WEB_SERVER_COMMAND ?? 'pnpm nx dev web';
const isCi = Boolean(process.env.CI);
const workers = process.env.PLAYWRIGHT_WORKERS
  ? Number(process.env.PLAYWRIGHT_WORKERS)
  : isCi
    ? 1
    : undefined;
const chromiumExecutablePath = resolveChromiumExecutablePath();
const videoMode =
  process.env.PLAYWRIGHT_DISABLE_VIDEO === '1' ||
  (chromiumExecutablePath && !resolveExecutableFromPath(['ffmpeg']))
    ? 'off'
    : 'retain-on-failure';

function isExecutable(filePath: string | undefined): filePath is string {
  if (!filePath) {
    return false;
  }

  try {
    accessSync(filePath, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function resolveExecutableFromPath(commands: readonly string[]): string | undefined {
  const pathEntries = (process.env.PATH ?? '').split(delimiter).filter(Boolean);

  for (const command of commands) {
    for (const pathEntry of pathEntries) {
      const candidate = join(pathEntry, command);
      if (isExecutable(candidate)) {
        return candidate;
      }
    }
  }

  return undefined;
}

function resolveChromiumExecutablePath(): string | undefined {
  const configuredExecutablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  if (configuredExecutablePath) {
    return configuredExecutablePath;
  }

  if (isExecutable(chromium.executablePath())) {
    return undefined;
  }

  return resolveExecutableFromPath([
    'google-chrome-stable',
    'google-chrome',
    'chromium',
    'chromium-browser',
  ]);
}

// E2E suite for the web app. Runs against the Vite dev server on port 4200.
// First-time setup: `pnpm exec playwright install chromium`.
// Run:            `pnpm e2e` (or `pnpm e2e -- --ui` for the Playwright UI).
//
// Tests stub the auth and workspace bootstrap endpoints via page.route so they
// don't require a live API. Only chromium runs by default — extend projects
// below if we ever need cross-browser coverage.
export default defineConfig({
  testDir: './e2e',
  timeout: isCi ? 60_000 : 30_000,
  expect: { timeout: isCi ? 10_000 : 5_000 },
  forbidOnly: isCi,
  fullyParallel: true,
  ...(workers && Number.isFinite(workers) && workers > 0 ? { workers } : {}),
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    video: videoMode,
    ...(chromiumExecutablePath ? { launchOptions: { executablePath: chromiumExecutablePath } } : {}),
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
    command: webServerCommand,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
