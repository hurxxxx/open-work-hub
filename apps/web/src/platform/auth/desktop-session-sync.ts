import { createDesktopSessionLink } from './auth-api';

const DESKTOP_PROTOCOL_URL = 'open-alm-desktop://auth';
const LOCAL_DESKTOP_SESSION_HOSTS = new Set([
  'localhost',
  '127.0.0.1',
  '0.0.0.0',
  '::1',
]);

export type DesktopSessionSyncEnvironment = Partial<
  Pick<ImportMetaEnv, 'DEV' | 'MODE'>
>;

export type DesktopSessionSyncLocation = Pick<
  Location,
  'hostname' | 'origin'
>;

export interface DesktopSessionSyncSignal {
  env?: DesktopSessionSyncEnvironment | null;
  location?: DesktopSessionSyncLocation | null;
}

export interface DesktopSessionSyncOptions {
  documentRef?: Document;
  signal?: DesktopSessionSyncSignal;
}

function browserDesktopSessionSyncSignal(): DesktopSessionSyncSignal {
  if (typeof window === 'undefined') {
    return {
      env: import.meta.env,
      location: null,
    };
  }

  return {
    env: import.meta.env,
    location: window.location,
  };
}

function normalizeHostname(hostname: string | null | undefined): string {
  return (hostname ?? '')
    .trim()
    .toLowerCase()
    .replace(/^\[(.*)\]$/, '$1');
}

export function isLocalDesktopSessionHost(
  hostname: string | null | undefined,
): boolean {
  const normalized = normalizeHostname(hostname);
  return (
    LOCAL_DESKTOP_SESSION_HOSTS.has(normalized) ||
    normalized.endsWith('.localhost') ||
    normalized.endsWith('.local')
  );
}

export function shouldSuppressDesktopSessionSync(
  signal: DesktopSessionSyncSignal = browserDesktopSessionSyncSignal(),
): boolean {
  return (
    signal.env?.DEV === true ||
    signal.env?.MODE === 'development' ||
    isLocalDesktopSessionHost(signal.location?.hostname)
  );
}

function currentServerUrl(signal: DesktopSessionSyncSignal): string | null {
  const origin = signal.location?.origin;
  if (!origin || origin === 'null') {
    return null;
  }
  return origin;
}

function openDesktopProtocolUrl(url: string, documentRef?: Document): void {
  const targetDocument =
    documentRef ?? (typeof document === 'undefined' ? null : document);
  if (!targetDocument?.body) {
    return;
  }

  const iframe = targetDocument.createElement('iframe');
  iframe.hidden = true;
  iframe.tabIndex = -1;
  iframe.src = url;
  targetDocument.body.append(iframe);

  const targetWindow =
    targetDocument.defaultView ??
    (typeof window === 'undefined' ? null : window);
  if (targetWindow) {
    targetWindow.setTimeout(() => iframe.remove(), 1200);
  } else {
    iframe.remove();
  }
}

export async function syncDesktopLoginSession(
  token: string,
  options: DesktopSessionSyncOptions = {},
): Promise<void> {
  const signal = options.signal ?? browserDesktopSessionSyncSignal();
  if (shouldSuppressDesktopSessionSync(signal)) {
    return;
  }

  const serverUrl = currentServerUrl(signal);
  if (!serverUrl) {
    return;
  }

  const link = await createDesktopSessionLink(token);
  const params = new URLSearchParams({
    server_url: serverUrl,
    code: link.code,
  });
  openDesktopProtocolUrl(
    `${DESKTOP_PROTOCOL_URL}/sync?${params.toString()}`,
    options.documentRef,
  );
}

export function syncDesktopLogoutSession(
  options: DesktopSessionSyncOptions = {},
): void {
  const signal = options.signal ?? browserDesktopSessionSyncSignal();
  if (shouldSuppressDesktopSessionSync(signal)) {
    return;
  }

  const serverUrl = currentServerUrl(signal);
  if (!serverUrl) {
    return;
  }

  const params = new URLSearchParams({ server_url: serverUrl });
  openDesktopProtocolUrl(
    `${DESKTOP_PROTOCOL_URL}/logout?${params.toString()}`,
    options.documentRef,
  );
}
