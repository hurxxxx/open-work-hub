import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppsBootstrapApp } from '@/src/platform/apps/apps-api';
import { createCodexConsoleSessionLink } from '@/src/platform/auth/auth-api';
import {
  appLaunchLinkProps,
  resolveAppLaunchDestination,
} from './app-launch-destination';

vi.mock('@/src/platform/auth/auth-api', () => ({
  createCodexConsoleSessionLink: vi.fn(),
}));

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});
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

it('opens Codex Console with a one-time handoff in the fragment', async () => {
  localStorage.setItem('open-work-hub.auth.token', 'owh-token');
  vi.mocked(createCodexConsoleSessionLink).mockResolvedValue({
    code: `cc1_${'a'.repeat(32)}`,
    expires_at: '2026-09-20T00:00:00Z',
  });
  const replace = vi.fn();
  vi.spyOn(window, 'open').mockReturnValue({
    closed: false,
    location: { replace },
    opener: window,
  } as unknown as Window);
  const preventDefault = vi.fn();
  const props = appLaunchLinkProps(
    'codex-console',
    'https://console.example.test/',
  );
  if (!('onClick' in props) || typeof props.onClick !== 'function')
    throw new Error('Missing console launch handler');

  props.onClick({ preventDefault });

  await vi.waitFor(() => expect(replace).toHaveBeenCalledOnce());
  expect(preventDefault).toHaveBeenCalledOnce();
  expect(createCodexConsoleSessionLink).toHaveBeenCalledWith('owh-token');
  const destination = new URL(replace.mock.calls[0][0]);
  expect(destination.origin).toBe('https://console.example.test');
  expect(new URLSearchParams(destination.hash.slice(1))).toEqual(
    new URLSearchParams({
      owh_issuer: window.location.origin,
      owh_code: `cc1_${'a'.repeat(32)}`,
    }),
  );
});

it('keeps the launcher close callback on internal app links', () => {
  const onClose = vi.fn();
  const props = appLaunchLinkProps('docs', '/apps/docs', onClose);
  if (!('onClick' in props) || typeof props.onClick !== 'function')
    throw new Error('Missing internal launch handler');

  props.onClick({ preventDefault: vi.fn() });

  expect(onClose).toHaveBeenCalledOnce();
});
