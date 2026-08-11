const BENTO_CHANNEL = 'open-work-hub:bento';
const BENTO_PROTOCOL_VERSION = 1;
const BENTO_DEV_DEFAULT_PORT = '18084';

interface BentoBrowserEnv {
  DEV?: boolean;
  VITE_OPEN_WORK_HUB_BENTO_PORT?: string;
  VITE_OPEN_WORK_HUB_BENTO_URL?: string;
}

export interface BentoEmbedConfig {
  src: string;
  origin: string;
}

export interface BentoBridgeMessage {
  channel: typeof BENTO_CHANNEL;
  version: typeof BENTO_PROTOCOL_VERSION;
  type: 'ready' | 'loaded' | 'document-changed' | 'save-request' | 'error';
  documentJson?: string;
  title?: string;
  message?: string;
}

export class BentoImportError extends Error {
  constructor() {
    super();
    this.name = 'BentoImportError';
  }
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

function devUrl(location: Location, port: string): URL {
  const url = new URL(location.href);
  url.port = port;
  url.pathname = '/';
  url.search = '';
  url.hash = '';
  return url;
}

export function buildBentoEmbedConfig({
  env,
  location,
}: {
  env: BentoBrowserEnv;
  location: Location;
}): BentoEmbedConfig | null {
  let url: URL;
  try {
    if (env.DEV && isDevelopmentHost(location.hostname)) {
      url = devUrl(
        location,
        env.VITE_OPEN_WORK_HUB_BENTO_PORT?.trim() || BENTO_DEV_DEFAULT_PORT,
      );
    } else {
      const configured = env.VITE_OPEN_WORK_HUB_BENTO_URL?.trim();
      if (!configured) return null;
      url = new URL(configured, location.origin);
    }
  } catch {
    return null;
  }

  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.origin === location.origin ||
    Boolean(url.username || url.password) ||
    (location.protocol === 'https:' && url.protocol !== 'https:')
  ) {
    return null;
  }
  url.pathname = '/';
  url.search = 'open-work-hub-embed=1';
  url.hash = '';
  return { src: url.toString(), origin: url.origin };
}

export function currentBentoEmbedConfig(): BentoEmbedConfig | null {
  return buildBentoEmbedConfig({
    env: import.meta.env,
    location: window.location,
  });
}

export function isBentoMessageOriginAllowed(
  origin: string,
  allowedOrigin: string,
): boolean {
  return origin === allowedOrigin;
}

export function parseBentoBridgeMessage(
  data: unknown,
): BentoBridgeMessage | null {
  if (!data || typeof data !== 'object') return null;
  const candidate = data as Record<string, unknown>;
  if (
    candidate.channel !== BENTO_CHANNEL ||
    candidate.version !== BENTO_PROTOCOL_VERSION ||
    !['ready', 'loaded', 'document-changed', 'save-request', 'error'].includes(
      String(candidate.type),
    )
  ) {
    return null;
  }
  return {
    channel: BENTO_CHANNEL,
    version: BENTO_PROTOCOL_VERSION,
    type: candidate.type as BentoBridgeMessage['type'],
    documentJson:
      typeof candidate.documentJson === 'string'
        ? candidate.documentJson
        : undefined,
    title: typeof candidate.title === 'string' ? candidate.title : undefined,
    message:
      typeof candidate.message === 'string' ? candidate.message : undefined,
  };
}

export function buildBentoLoadMessage(documentJson: string) {
  return {
    channel: BENTO_CHANNEL,
    version: BENTO_PROTOCOL_VERSION,
    type: 'load-document' as const,
    documentJson,
  };
}

export function buildBentoExportMessage() {
  return {
    channel: BENTO_CHANNEL,
    version: BENTO_PROTOCOL_VERSION,
    type: 'export-document' as const,
  };
}

export function buildBentoSaveRequestMessage() {
  return {
    channel: BENTO_CHANNEL,
    version: BENTO_PROTOCOL_VERSION,
    type: 'request-document' as const,
  };
}

export function parseBentoHtmlDocument(html: string): {
  documentJson: string;
  title: string;
} {
  const parsed = new DOMParser().parseFromString(html, 'text/html');
  const documentJson = parsed.getElementById('bento-doc')?.textContent?.trim();
  if (!documentJson) {
    throw new BentoImportError();
  }
  let document: Record<string, unknown>;
  try {
    document = JSON.parse(documentJson) as Record<string, unknown>;
  } catch {
    throw new BentoImportError();
  }
  if (
    document.format !== 'bento/slides' ||
    !Array.isArray(document.slides) ||
    document.slides.length === 0
  ) {
    throw new BentoImportError();
  }
  const title =
    typeof document.title === 'string' && document.title.trim()
      ? document.title.trim()
      : 'Untitled';
  return { documentJson: JSON.stringify(document), title };
}
