import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearMatomoUser,
  identifyMatomoUser,
  installMatomoTracking,
  resolveMatomoTrackingConfig,
  trackMatomoPageView,
  type InstalledMatomoTracking,
} from './matomo';

let installedTracking: InstalledMatomoTracking | null = null;

afterEach(() => {
  installedTracking?.cleanup();
  installedTracking = null;
  vi.useRealTimers();
  document.head.innerHTML = '';
  document.body.innerHTML = '';
  delete (window as typeof window & { _paq?: unknown })._paq;
  window.history.replaceState({}, '', '/');
});

describe('Matomo tracking configuration', () => {
  it('uses the AI-DO Matomo server for production hosts', () => {
    expect(
      resolveMatomoTrackingConfig({}, { hostname: 'dwdcc.kr' }),
    ).toMatchObject({
      siteId: '1',
      trackerBaseUrl: 'https://matomo.dwdcc.kr/',
    });
  });

  it('does not track dev or localhost by default', () => {
    expect(
      resolveMatomoTrackingConfig({}, { hostname: 'dev.dwdcc.kr' }),
    ).toBeNull();
    expect(
      resolveMatomoTrackingConfig({}, { hostname: 'localhost' }),
    ).toBeNull();
  });

  it('can be disabled explicitly', () => {
    expect(
      resolveMatomoTrackingConfig(
        { VITE_AI_DO_MATOMO_ENABLED: 'false' },
        { hostname: 'dwdcc.kr' },
      ),
    ).toBeNull();
  });
});

describe('Matomo tracker installation', () => {
  it('installs the Matomo script and queues the base tracker settings', () => {
    window.history.replaceState({}, '', '/w/main/home');
    document.title = 'AI-DO Home';

    installedTracking = installMatomoTracking(
      { VITE_AI_DO_MATOMO_ALLOWED_HOSTS: 'localhost' },
      window,
    );

    expect(installedTracking).not.toBeNull();
    expect(window._paq).toEqual([
      ['setTrackerUrl', 'https://matomo.dwdcc.kr/matomo.php'],
      ['setSiteId', '1'],
      ['enableLinkTracking'],
    ]);
    expect(
      document
        .querySelector('script#ai-do-matomo-tracker')
        ?.getAttribute('src'),
    ).toBe('https://matomo.dwdcc.kr/matomo.js');
  });

  it('tracks shell route context once per page key', () => {
    window.history.replaceState({}, '', '/w/main/home');

    installedTracking = installMatomoTracking(
      { VITE_AI_DO_MATOMO_ALLOWED_HOSTS: 'localhost' },
      window,
    );
    window._paq?.splice(0);

    window.history.pushState({}, '', '/w/main/docs');
    trackMatomoPageView(
      {
        appId: 'collaboration:docs-main',
        appRoute: '/w/:workspace/docs',
      },
      window,
    );
    trackMatomoPageView(
      {
        appId: 'collaboration:docs-main',
        appRoute: '/w/:workspace/docs',
      },
      window,
    );

    expect(window._paq).toEqual([
      ['setCustomUrl', 'http://localhost:3000/w/main/docs'],
      ['setDocumentTitle', document.title],
      ['setCustomDimension', 2, 'collaboration:docs-main'],
      ['setCustomDimension', 3, '/w/:workspace/docs'],
      ['trackPageView'],
    ]);
  });

  it('sets the logged-in user id, login id, and name for later page views', () => {
    installedTracking = installMatomoTracking(
      { VITE_AI_DO_MATOMO_ALLOWED_HOSTS: 'localhost' },
      window,
    );
    window._paq?.splice(0);

    identifyMatomoUser(
      {
        userId: 'member',
        userLoginId: 'member',
        userName: 'AI-DO Member',
      },
      window,
    );
    clearMatomoUser(window);

    expect(window._paq).toEqual([
      ['setUserId', 'member'],
      ['setCustomDimension', 4, 'member'],
      ['setCustomDimension', 1, 'AI-DO Member'],
      ['resetUserId'],
      ['deleteCustomDimension', 1],
      ['deleteCustomDimension', 4],
    ]);
  });

  it('does not install twice', () => {
    const env = { VITE_AI_DO_MATOMO_ALLOWED_HOSTS: 'localhost' };

    installedTracking = installMatomoTracking(env, window);

    expect(installMatomoTracking(env, window)).toBeNull();
    expect(
      document.querySelectorAll('script#ai-do-matomo-tracker'),
    ).toHaveLength(1);
  });
});
