import { describe, expect, it } from 'vitest';
import type { AppsBootstrapApp } from '@/src/platform/apps/apps-api';
import { resolveAppLaunchDestination } from './app-launch-destination';
const destination = (appId: string, enabled = true) =>
  resolveAppLaunchDestination({
    app: { app_id: appId, enabled } as AppsBootstrapApp,
    appId,
    launcherGlobalPaths: new Map(),
  });
describe('company app destinations', () => {
  it.each([
    ['docs', 'personal'],
    ['pms', 'company'],
    ['mail', 'personal'],
    ['planner', 'personal'],
  ])('opens %s with its declared scope', (id, scope) => {
    expect(destination(id)).toEqual({
      href: `/apps/${id}`,
      kind: 'app',
      displayScope: scope,
    });
  });
  it('denies disabled and unknown apps', () => {
    expect(destination('docs', false)).toEqual({
      href: '/',
      kind: 'unavailable',
      displayScope: null,
    });
    expect(destination('unknown')).toEqual({
      href: '/',
      kind: 'unavailable',
      displayScope: null,
    });
  });
  it('denies missing bootstrap even for a known app', () => {
    expect(
      resolveAppLaunchDestination({
        app: null,
        appId: 'docs',
        launcherGlobalPaths: new Map(),
      }),
    ).toEqual({ href: '/', kind: 'unavailable', displayScope: null });
  });
});

it('opens configured console destinations and rejects missing or unsafe URLs', () => {
  const resolve = (launch_url: string | null, enabled = true) =>
    resolveAppLaunchDestination({
      app: { app_id: 'codex-console', enabled, launch_url } as AppsBootstrapApp,
      appId: 'codex-console',
      launcherGlobalPaths: new Map(),
    });
  expect(resolve('/codex-console/')).toEqual({
    href: '/codex-console/',
    kind: 'external',
    displayScope: 'personal',
  });
  expect(resolve('https://console.example.test/').kind).toBe('external');
  for (const url of [
    null,
    'javascript:alert(1)',
    '//evil.test/',
    '/\\evil.test/',
    ...Array.from(
      { length: 32 },
      (_, code) => `https://console.example.test/${String.fromCharCode(code)}`,
    ),
  ]) {
    expect(resolve(url).kind).toBe('unavailable');
  }
  expect(resolve('/codex-console/', false).kind).toBe('unavailable');
});
