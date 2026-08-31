#!/usr/bin/env node

import { chromium } from '@playwright/test';

const webBaseUrl = (
  process.env.OPEN_WORK_HUB_DEV_SMOKE_WEB_URL ??
  `http://127.0.0.1:${process.env.OPEN_WORK_HUB_WEB_DEV_PORT ?? '4200'}`
).replace(/\/$/, '');
const loginId = 'administrator';
const password =
  process.env.OPEN_WORK_HUB_API_DEV_LOGIN_PASSWORD ?? 'open-work-hub-dev-only';

let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(`${webBaseUrl}/login`, { waitUntil: 'networkidle' });

  const loginIdInput = page.locator('#auth-login-id');
  const passwordInput = page.locator('#auth-password');
  const submitButton = page.locator('button[type="submit"]');
  const controlCounts = await Promise.all([
    loginIdInput.count(),
    passwordInput.count(),
    submitButton.count(),
  ]);
  if (controlCounts.some((count) => count !== 1)) {
    throw new Error('Expected unique login form controls were not rendered.');
  }

  await loginIdInput.fill(loginId);
  await passwordInput.fill(password);
  await submitButton.click();
  await page.waitForURL((url) => url.pathname === '/', { timeout: 15_000 });

  const applicationRoot = page.locator('#root');
  if ((await applicationRoot.count()) !== 1) {
    throw new Error('Authenticated application root is not visible.');
  }
  await applicationRoot.waitFor({ state: 'visible', timeout: 15_000 });
  if ((await page.locator('#auth-login-id').count()) !== 0) {
    throw new Error('Login form remained visible after authentication.');
  }

  const allAppsButton = page.getByRole('button', {
    name: 'All Apps',
    exact: true,
  });
  await allAppsButton.waitFor({ state: 'visible', timeout: 15_000 });

  const expectedCategoryPaths = await page.evaluate(async () => {
    const token = window.localStorage.getItem('open-work-hub.auth.token');
    if (!token)
      throw new Error('Authenticated browser session token is missing.');

    const headers = { Authorization: `Bearer ${token}` };
    const response = await fetch('/api/v1/apps/bootstrap', { headers });
    if (!response.ok) {
      throw new Error('App bootstrap request failed after browser login.');
    }
    const payload = await response.json();
    return (payload.app_bar_categories ?? [])
      .filter((category) => category.title === 'All Apps')
      .flatMap((category) => category.items)
      .map((item) => item.route_base)
      .filter((path, index, paths) => paths.indexOf(path) === index)
      .sort();
  });
  if (expectedCategoryPaths.length === 0) {
    throw new Error('Seeded All Apps bootstrap category is empty.');
  }

  await allAppsButton.click();
  const categoryPaths = (
    await page.getByRole('menuitem').evaluateAll((nodes) =>
      nodes.flatMap((node) => {
        const href = node.getAttribute('href');
        return href ? [new URL(href, window.location.origin).pathname] : [];
      }),
    )
  ).sort();
  if (JSON.stringify(categoryPaths) !== JSON.stringify(expectedCategoryPaths)) {
    throw new Error(
      `Seeded All Apps launcher mismatch: ${JSON.stringify(categoryPaths)}`,
    );
  }

  console.log(`Browser login passed: ${page.url()}`);
} catch (error) {
  if (
    error instanceof Error &&
    error.message.includes("Executable doesn't exist")
  ) {
    console.error('Browser login smoke requires: pnpm e2e:install');
  }
  throw error;
} finally {
  await browser?.close();
}
