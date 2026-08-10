const DRAWIO_EMBED_QUERY =
  'embed=1&proto=json&spin=1&offline=1&libraries=1&noSaveBtn=1&saveAndExit=1';
const DRAWIO_DEV_DEFAULT_PORT = '18082';
const DRAWIO_FALLBACK_PATH = '/drawio/';

interface DrawioBrowserEnv {
  DEV?: boolean;
  VITE_OPEN_WORK_HUB_DRAWIO_PORT?: string;
  VITE_OPEN_WORK_HUB_DRAWIO_URL?: string;
}

export interface DrawioEmbedConfig {
  src: string;
  origin: string;
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function appendDrawioEmbedQuery(serverUrl: string): string {
  const url = new URL(serverUrl);
  url.search = url.search
    ? `${url.search.slice(1)}&${DRAWIO_EMBED_QUERY}`
    : DRAWIO_EMBED_QUERY;
  return url.toString();
}

function absoluteUrl(value: string, baseUrl: string): URL | null {
  try {
    return new URL(value, baseUrl);
  } catch {
    return null;
  }
}

function drawioDevUrlFromLocation(location: Location, port: string): string {
  const url = new URL(location.href);
  url.port = port;
  url.pathname = '/';
  url.search = '';
  url.hash = '';
  return url.toString();
}

function isPrivateIpv4(hostname: string): boolean {
  const octets = hostname.split('.').map((part) => Number(part));
  if (
    octets.length !== 4 ||
    octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)
  ) {
    return false;
  }

  const [first, second] = octets;
  return (
    first === 10 ||
    first === 127 ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168) ||
    (first === 100 && second >= 64 && second <= 127)
  );
}

function isDevelopmentHost(hostname: string): boolean {
  const normalized = hostname.toLowerCase();
  return (
    normalized === 'localhost' ||
    normalized === '::1' ||
    normalized === '[::1]' ||
    normalized.endsWith('.local') ||
    isPrivateIpv4(normalized)
  );
}

export function resolveDrawioServerUrl({
  env,
  location,
}: {
  env: DrawioBrowserEnv;
  location: Location;
}): string {
  const configuredUrl = env.VITE_OPEN_WORK_HUB_DRAWIO_URL?.trim() ?? '';
  const configuredIsAbsolute = /^https?:\/\//i.test(configuredUrl);
  if (configuredIsAbsolute) return configuredUrl;

  if (!isDevelopmentHost(location.hostname)) {
    return configuredUrl || DRAWIO_FALLBACK_PATH;
  }

  if (env.DEV || (!configuredUrl && isDevelopmentHost(location.hostname))) {
    return drawioDevUrlFromLocation(
      location,
      env.VITE_OPEN_WORK_HUB_DRAWIO_PORT?.trim() || DRAWIO_DEV_DEFAULT_PORT,
    );
  }

  return configuredUrl || DRAWIO_FALLBACK_PATH;
}

export function buildDrawioEmbedConfig({
  env,
  location,
}: {
  env: DrawioBrowserEnv;
  location: Location;
}): DrawioEmbedConfig {
  const serverUrl = resolveDrawioServerUrl({ env, location });
  const absolute = absoluteUrl(serverUrl, location.origin);
  if (!absolute) {
    return {
      src: `${DRAWIO_FALLBACK_PATH}?${DRAWIO_EMBED_QUERY}`,
      origin: location.origin,
    };
  }
  absolute.pathname = absolute.pathname || '/';
  return {
    src: appendDrawioEmbedQuery(absolute.toString()),
    origin: trimTrailingSlash(absolute.origin),
  };
}

export function currentDrawioEmbedConfig(): DrawioEmbedConfig {
  return buildDrawioEmbedConfig({
    env: import.meta.env,
    location: window.location,
  });
}

export interface DrawioEmbedMessage {
  event?: string;
  format?: string;
  xml?: string;
  data?: string;
  message?: string;
}

export function isDrawioMessageOriginAllowed(
  origin: string,
  allowedOrigin: string,
): boolean {
  return origin === allowedOrigin;
}

export function parseDrawioEmbedMessage(
  data: unknown,
): DrawioEmbedMessage | null {
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data) as unknown;
      return parseDrawioEmbedMessage(parsed);
    } catch {
      return null;
    }
  }
  if (!data || typeof data !== 'object') {
    return null;
  }
  const candidate = data as Record<string, unknown>;
  return {
    event: typeof candidate.event === 'string' ? candidate.event : undefined,
    format: typeof candidate.format === 'string' ? candidate.format : undefined,
    xml: typeof candidate.xml === 'string' ? candidate.xml : undefined,
    data: typeof candidate.data === 'string' ? candidate.data : undefined,
    message:
      typeof candidate.message === 'string' ? candidate.message : undefined,
  };
}

export function buildDrawioLoadMessage(xml: string): string {
  return JSON.stringify({
    action: 'load',
    autosave: 1,
    xml,
  });
}

export function buildDrawioExportMessage(xml: string): string {
  return JSON.stringify({
    action: 'export',
    format: 'png',
    xml,
    border: 8,
    spinKey: 'diagram-save',
  });
}
