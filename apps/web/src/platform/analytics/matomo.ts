const DEFAULT_MATOMO_URL = 'https://matomo.dwdcc.kr/';
const DEFAULT_MATOMO_SITE_ID = '1';
const DEFAULT_ALLOWED_HOSTS = ['dwdcc.kr', 'www.dwdcc.kr', 'ext.dwdcc.kr'];
const MATOMO_SCRIPT_ID = 'ai-do-matomo-tracker';
const USER_NAME_DIMENSION_ID = 1;
const APP_ID_DIMENSION_ID = 2;
const APP_ROUTE_DIMENSION_ID = 3;
const USER_LOGIN_ID_DIMENSION_ID = 4;
const MAX_DIMENSION_VALUE_LENGTH = 255;

type MatomoCommandValue = string | number | boolean;
type MatomoCommand = [string, ...MatomoCommandValue[]];

declare global {
  interface Window {
    __aiDoMatomoLastTrackedUrl?: string;
    __aiDoMatomoLastTrackedPageKey?: string;
    __aiDoMatomoTrackingInstalled?: boolean;
    __aiDoMatomoUserId?: string;
    __aiDoMatomoUserLoginId?: string;
    __aiDoMatomoUserName?: string;
    _paq?: MatomoCommand[];
  }
}

export type MatomoEnv = {
  readonly VITE_AI_DO_MATOMO_ALLOWED_HOSTS?: string;
  readonly VITE_AI_DO_MATOMO_ENABLED?: string;
  readonly VITE_AI_DO_MATOMO_SITE_ID?: string;
  readonly VITE_AI_DO_MATOMO_URL?: string;
};

type MatomoWindow = Window &
  typeof globalThis & {
    _paq?: MatomoCommand[];
  };

export type MatomoTrackingConfig = {
  readonly allowedHosts: readonly string[];
  readonly siteId: string;
  readonly trackerBaseUrl: string;
};

export type InstalledMatomoTracking = {
  cleanup: () => void;
};

export type MatomoUserIdentity = {
  readonly userId: string;
  readonly userLoginId?: string;
  readonly userName: string;
};

export type MatomoPageContext = {
  readonly appId?: string | null;
  readonly appRoute?: string | null;
};

export function resolveMatomoTrackingConfig(
  env: MatomoEnv,
  location: Pick<Location, 'hostname'>,
): MatomoTrackingConfig | null {
  if (!isEnabled(env.VITE_AI_DO_MATOMO_ENABLED)) {
    return null;
  }

  const trackerBaseUrl = normalizeMatomoUrl(
    env.VITE_AI_DO_MATOMO_URL ?? DEFAULT_MATOMO_URL,
  );
  const siteId = normalizeSiteId(
    env.VITE_AI_DO_MATOMO_SITE_ID ?? DEFAULT_MATOMO_SITE_ID,
  );
  const allowedHosts = parseAllowedHosts(env.VITE_AI_DO_MATOMO_ALLOWED_HOSTS);

  if (
    !trackerBaseUrl ||
    !siteId ||
    !isAllowedHost(location.hostname, allowedHosts)
  ) {
    return null;
  }

  return {
    allowedHosts,
    siteId,
    trackerBaseUrl,
  };
}

export function installMatomoTracking(
  env: MatomoEnv = import.meta.env as MatomoEnv,
  win: MatomoWindow = window as MatomoWindow,
): InstalledMatomoTracking | null {
  if (win.__aiDoMatomoTrackingInstalled) {
    return null;
  }

  const config = resolveMatomoTrackingConfig(env, win.location);
  if (!config) {
    return null;
  }

  const queue = getMatomoQueue(win);
  win.__aiDoMatomoTrackingInstalled = true;

  queue.push(['setTrackerUrl', `${config.trackerBaseUrl}matomo.php`]);
  queue.push(['setSiteId', config.siteId]);
  queue.push(['enableLinkTracking']);

  appendMatomoScript(win.document, `${config.trackerBaseUrl}matomo.js`);

  return {
    cleanup: () => {
      delete win.__aiDoMatomoTrackingInstalled;
      delete win.__aiDoMatomoLastTrackedUrl;
      delete win.__aiDoMatomoLastTrackedPageKey;
      delete win.__aiDoMatomoUserId;
      delete win.__aiDoMatomoUserLoginId;
      delete win.__aiDoMatomoUserName;
    },
  };
}

export function identifyMatomoUser(
  identity: MatomoUserIdentity,
  win: MatomoWindow = window as MatomoWindow,
): void {
  const queue = getActiveMatomoQueue(win);
  if (!queue) {
    return;
  }

  const userId = normalizeDimensionValue(identity.userId);
  const userLoginId = normalizeDimensionValue(
    identity.userLoginId ?? identity.userId,
  );
  const userName = normalizeDimensionValue(identity.userName);
  if (!userId) {
    clearMatomoUser(win);
    return;
  }

  if (win.__aiDoMatomoUserId !== userId) {
    queue.push(['setUserId', userId]);
    win.__aiDoMatomoUserId = userId;
  }
  if (userLoginId && win.__aiDoMatomoUserLoginId !== userLoginId) {
    queue.push(['setCustomDimension', USER_LOGIN_ID_DIMENSION_ID, userLoginId]);
    win.__aiDoMatomoUserLoginId = userLoginId;
  }
  if (userName && win.__aiDoMatomoUserName !== userName) {
    queue.push(['setCustomDimension', USER_NAME_DIMENSION_ID, userName]);
    win.__aiDoMatomoUserName = userName;
  }
}

export function clearMatomoUser(
  win: MatomoWindow = window as MatomoWindow,
): void {
  const queue = getActiveMatomoQueue(win);
  if (!queue) {
    return;
  }

  queue.push(['resetUserId']);
  queue.push(['deleteCustomDimension', USER_NAME_DIMENSION_ID]);
  queue.push(['deleteCustomDimension', USER_LOGIN_ID_DIMENSION_ID]);
  delete win.__aiDoMatomoUserId;
  delete win.__aiDoMatomoUserLoginId;
  delete win.__aiDoMatomoUserName;
}

export function trackMatomoPageView(
  context: MatomoPageContext = {},
  win: MatomoWindow = window as MatomoWindow,
): void {
  const queue = getActiveMatomoQueue(win);
  if (!queue) {
    return;
  }

  const currentUrl = win.location.href;
  const appId = normalizeDimensionValue(context.appId ?? '');
  const appRoute = normalizeDimensionValue(context.appRoute ?? '');
  const pageKey = [currentUrl, win.document.title, appId, appRoute].join('|');
  if (win.__aiDoMatomoLastTrackedPageKey === pageKey) {
    return;
  }

  win.__aiDoMatomoLastTrackedUrl = currentUrl;
  win.__aiDoMatomoLastTrackedPageKey = pageKey;
  queue.push(['setCustomUrl', currentUrl]);
  queue.push(['setDocumentTitle', win.document.title]);

  if (appId) {
    queue.push(['setCustomDimension', APP_ID_DIMENSION_ID, appId]);
  } else {
    queue.push(['deleteCustomDimension', APP_ID_DIMENSION_ID]);
  }
  if (appRoute) {
    queue.push(['setCustomDimension', APP_ROUTE_DIMENSION_ID, appRoute]);
  } else {
    queue.push(['deleteCustomDimension', APP_ROUTE_DIMENSION_ID]);
  }

  queue.push(['trackPageView']);
}

function isEnabled(value: string | undefined): boolean {
  if (!value) {
    return true;
  }
  return !['0', 'false', 'no', 'off'].includes(value.trim().toLowerCase());
}

function normalizeMatomoUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  try {
    const url = new URL(trimmed);
    if (!['http:', 'https:'].includes(url.protocol)) {
      return null;
    }
    url.hash = '';
    url.search = '';
    if (!url.pathname.endsWith('/')) {
      url.pathname = `${url.pathname}/`;
    }
    return url.toString();
  } catch {
    return null;
  }
}

function normalizeSiteId(value: string): string | null {
  const siteId = value.trim();
  if (!/^[1-9]\d*$/.test(siteId)) {
    return null;
  }
  return siteId;
}

function parseAllowedHosts(value: string | undefined): readonly string[] {
  const rawHosts = value?.trim() ? value.split(',') : DEFAULT_ALLOWED_HOSTS;
  return rawHosts.map((item) => item.trim().toLowerCase()).filter(Boolean);
}

function isAllowedHost(
  hostname: string,
  allowedHosts: readonly string[],
): boolean {
  const normalizedHostname = hostname.trim().toLowerCase();
  return allowedHosts.some((allowedHost) => {
    if (allowedHost === '*') {
      return true;
    }
    if (allowedHost.startsWith('.')) {
      return normalizedHostname.endsWith(allowedHost);
    }
    return normalizedHostname === allowedHost;
  });
}

function getMatomoQueue(win: MatomoWindow): MatomoCommand[] {
  win._paq = win._paq ?? [];
  return win._paq;
}

function getActiveMatomoQueue(win: MatomoWindow): MatomoCommand[] | null {
  if (!win.__aiDoMatomoTrackingInstalled) {
    return null;
  }
  return getMatomoQueue(win);
}

function normalizeDimensionValue(value: string): string {
  return value.trim().slice(0, MAX_DIMENSION_VALUE_LENGTH);
}

function appendMatomoScript(document: Document, scriptUrl: string) {
  if (document.getElementById(MATOMO_SCRIPT_ID)) {
    return;
  }

  const script = document.createElement('script');
  script.id = MATOMO_SCRIPT_ID;
  script.async = true;
  script.defer = true;
  script.src = scriptUrl;

  const target = document.head ?? document.body ?? document.documentElement;
  target.append(script);
}
