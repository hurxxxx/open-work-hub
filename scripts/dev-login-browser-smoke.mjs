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

  const bootstrapProjection = await page.evaluate(async () => {
    const token = window.localStorage.getItem('open-work-hub.auth.token');
    if (!token)
      throw new Error('Authenticated browser session token is missing.');

    const headers = { Authorization: `Bearer ${token}` };
    const response = await fetch('/api/v1/apps/bootstrap', { headers });
    if (!response.ok) {
      throw new Error('App bootstrap request failed after browser login.');
    }
    const payload = await response.json();
    return {
      appRoutes: (payload.apps ?? [])
        .map((app) => ({ appId: app.app_id, routeBase: app.route_base }))
        .filter(
          (app, index, apps) =>
            apps.findIndex((candidate) => candidate.appId === app.appId) ===
            index,
        )
        .sort((left, right) => left.appId.localeCompare(right.appId)),
      categoryPaths: (payload.app_bar_categories ?? [])
        .filter((category) => category.title === 'All Apps')
        .flatMap((category) => category.items)
        .map((item) => item.route_base)
        .filter((path, index, paths) => paths.indexOf(path) === index)
        .sort(),
    };
  });
  const expectedCategoryPaths = bootstrapProjection.categoryPaths;
  if (expectedCategoryPaths.length === 0) {
    throw new Error('Seeded All Apps bootstrap category is empty.');
  }
  if (bootstrapProjection.appRoutes.length === 0) {
    throw new Error('Authenticated app bootstrap is empty.');
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

  for (const { appId, routeBase } of bootstrapProjection.appRoutes) {
    await page.goto(`${webBaseUrl}${routeBase}`, {
      waitUntil: 'domcontentloaded',
    });
    await page.locator('#root').waitFor({ state: 'visible', timeout: 15_000 });
    await page.locator('h1, h2').first().waitFor({
      state: 'visible',
      timeout: 15_000,
    });

    if ((await page.locator('#auth-login-id').count()) !== 0) {
      throw new Error(`Authentication was lost while opening ${appId}.`);
    }
    if (
      (await page
        .getByRole('heading', {
          name: /페이지를 찾을 수 없습니다|Page not found/,
        })
        .count()) !== 0
    ) {
      throw new Error(`App entry route rendered NotFoundView: ${appId}.`);
    }

    const pathname = new URL(page.url()).pathname;
    if (pathname !== routeBase && !pathname.startsWith(`${routeBase}/`)) {
      throw new Error(
        `App entry route escaped its contract: ${appId} -> ${pathname}`,
      );
    }
  }

  const logoutStatus = await page.evaluate(async () => {
    const key = 'open-work-hub.auth.token';
    const token = window.localStorage.getItem(key);
    if (!token) return 0;
    const response = await fetch('/api/v1/auth/logout', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    window.localStorage.removeItem(key);
    return response.status;
  });
  if (logoutStatus !== 204) {
    throw new Error(`Browser smoke logout returned HTTP ${logoutStatus}.`);
  }

  console.log(
    `Browser login and app route smoke passed: ${bootstrapProjection.appRoutes.length} apps`,
  );
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
