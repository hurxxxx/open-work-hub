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
  it('uses the Open Work Hub Matomo server for production hosts', () => {
    expect(
      resolveMatomoTrackingConfig({}, { hostname: 'open-work-hub.example' }),
    ).toMatchObject({
      siteId: '1',
      trackerBaseUrl: 'https://matomo.open-work-hub.example/',
    });
  });

  it('does not track dev or localhost by default', () => {
    expect(
      resolveMatomoTrackingConfig(
        {},
        { hostname: 'dev.open-work-hub.example' },
      ),
    ).toBeNull();
    expect(
      resolveMatomoTrackingConfig({}, { hostname: 'localhost' }),
    ).toBeNull();
  });

  it('can be disabled explicitly', () => {
    expect(
      resolveMatomoTrackingConfig(
        { VITE_OPEN_WORK_HUB_MATOMO_ENABLED: 'false' },
        { hostname: 'open-work-hub.example' },
      ),
    ).toBeNull();
  });
});

describe('Matomo tracker installation', () => {
  it('installs the Matomo script and queues the base tracker settings', () => {
    window.history.replaceState({}, '', '/apps/home/workspaces/main');
    document.title = 'Open Work Hub Home';

    installedTracking = installMatomoTracking(
      { VITE_OPEN_WORK_HUB_MATOMO_ALLOWED_HOSTS: 'localhost' },
      window,
    );

    expect(installedTracking).not.toBeNull();
    expect(window._paq).toEqual([
      ['setTrackerUrl', 'https://matomo.open-work-hub.example/matomo.php'],
      ['setSiteId', '1'],
      ['enableLinkTracking'],
    ]);
    expect(
      document
        .querySelector('script#open-work-hub-matomo-tracker')
        ?.getAttribute('src'),
    ).toBe('https://matomo.open-work-hub.example/matomo.js');
  });

  it('tracks shell route context once per page key', () => {
    window.history.replaceState({}, '', '/apps/home/workspaces/main');

    installedTracking = installMatomoTracking(
      { VITE_OPEN_WORK_HUB_MATOMO_ALLOWED_HOSTS: 'localhost' },
      window,
    );
    window._paq?.splice(0);

    window.history.pushState({}, '', '/apps/docs/workspaces/main');
    trackMatomoPageView(
      {
        appId: 'collaboration:docs-main',
        appRoute: '/apps/docs/workspaces/:workspace',
      },
      window,
    );
    trackMatomoPageView(
      {
        appId: 'collaboration:docs-main',
        appRoute: '/apps/docs/workspaces/:workspace',
      },
      window,
    );

    expect(window._paq).toEqual([
      ['setCustomUrl', 'http://localhost:3000/apps/docs/workspaces/main'],
      ['setDocumentTitle', document.title],
      ['setCustomDimension', 2, 'collaboration:docs-main'],
      ['setCustomDimension', 3, '/apps/docs/workspaces/:workspace'],
      ['trackPageView'],
    ]);
  });

  it('sets the logged-in user id, login id, and name for later page views', () => {
    installedTracking = installMatomoTracking(
      { VITE_OPEN_WORK_HUB_MATOMO_ALLOWED_HOSTS: 'localhost' },
      window,
    );
    window._paq?.splice(0);

    identifyMatomoUser(
      {
        userId: 'member',
        userLoginId: 'member',
        userName: 'Open Work Hub Member',
      },
      window,
    );
    clearMatomoUser(window);

    expect(window._paq).toEqual([
      ['setUserId', 'member'],
      ['setCustomDimension', 4, 'member'],
      ['setCustomDimension', 1, 'Open Work Hub Member'],
      ['resetUserId'],
      ['deleteCustomDimension', 1],
      ['deleteCustomDimension', 4],
    ]);
  });

  it('does not install twice', () => {
    const env = { VITE_OPEN_WORK_HUB_MATOMO_ALLOWED_HOSTS: 'localhost' };

    installedTracking = installMatomoTracking(env, window);

    expect(installMatomoTracking(env, window)).toBeNull();
    expect(
      document.querySelectorAll('script#open-work-hub-matomo-tracker'),
    ).toHaveLength(1);
  });
});
