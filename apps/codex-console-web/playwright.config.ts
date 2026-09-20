import { defineConfig, devices } from '@playwright/test';
import { createServer, type AddressInfo } from 'node:net';

const reservation = createServer();
await new Promise<void>((resolve) =>
  reservation.listen(0, '127.0.0.1', resolve),
);
const port = Number(
  process.env.OPEN_WORK_HUB_CODEX_CONSOLE_PORT ??
    (reservation.address() as AddressInfo).port,
);
await new Promise<void>((resolve, reject) =>
  reservation.close((error) => (error ? reject(error) : resolve())),
);
const basePath = process.env.OPEN_WORK_HUB_CODEX_CONSOLE_BASE_PATH ?? '';
const baseURL = `http://127.0.0.1:${port}${basePath}/`;
process.env.OPEN_WORK_HUB_CODEX_CONSOLE_PORT = String(port);

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: { baseURL, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command:
      'uv run --frozen --directory ../codex-console-api --group dev python tests/browser_server.py',
    url: `${baseURL}healthz`,
    reuseExistingServer: false,
    // Let the Python fixture's finally block remove its own temporary database.
    gracefulShutdown: { signal: 'SIGINT', timeout: 10000 },
    timeout: 60000,
  },
});
