const STALE_ASSET_RELOAD_STORAGE_KEY = 'ai-do:stale-asset-reload-at';
const DEFAULT_STALE_ASSET_RELOAD_COOLDOWN_MS = 60_000;
export const STALE_ASSET_RELOAD_QUERY_PARAM = '__reload';

type ReloadStorage = Pick<Storage, 'getItem' | 'setItem'>;

export interface StaleAssetReloadRuntime {
  addEventListener(type: string, listener: EventListener): void;
  removeEventListener(type: string, listener: EventListener): void;
  location: Pick<Location, 'href' | 'replace'>;
  history: Pick<History, 'state' | 'replaceState'>;
  sessionStorage?: ReloadStorage;
}

export interface StaleAssetReloadOptions {
  cooldownMs?: number;
  nowMs?: () => number;
}

const STALE_ASSET_ERROR_PATTERNS = [
  /Failed to fetch dynamically imported module/i,
  /Importing a module script failed/i,
  /error loading dynamically imported module/i,
  /Loading chunk [\w-]+ failed/i,
  /ChunkLoadError/i,
  /Unable to preload CSS/i,
];

let fallbackLastReloadAt = 0;

export function isStaleAssetLoadError(error: unknown): boolean {
  const message =
    error instanceof Error
      ? `${error.name}: ${error.message}`
      : String(error ?? '');
  return STALE_ASSET_ERROR_PATTERNS.some((pattern) => pattern.test(message));
}

function readLastReloadAt(runtime: StaleAssetReloadRuntime): number {
  try {
    const value = runtime.sessionStorage?.getItem(STALE_ASSET_RELOAD_STORAGE_KEY);
    if (value !== undefined && value !== null) {
      const timestamp = Number(value);
      if (Number.isFinite(timestamp)) {
        return timestamp;
      }
    }
  } catch {
    // Fall through to the URL marker or the in-memory guard.
  }

  const marker = new URL(runtime.location.href).searchParams.get(
    STALE_ASSET_RELOAD_QUERY_PARAM,
  );
  if (marker !== null) {
    const markerTimestamp = Number(marker);
    if (Number.isFinite(markerTimestamp)) {
      return markerTimestamp;
    }
  }
  return fallbackLastReloadAt;
}

function writeLastReloadAt(
  runtime: Pick<StaleAssetReloadRuntime, 'sessionStorage'>,
  timestamp: number,
) {
  try {
    if (runtime.sessionStorage) {
      runtime.sessionStorage.setItem(
        STALE_ASSET_RELOAD_STORAGE_KEY,
        String(timestamp),
      );
      return;
    }
  } catch {
    // Fall through to the module-level fallback.
  }
  fallbackLastReloadAt = timestamp;
}

export function requestCacheBustingReloadOnce(
  runtime: StaleAssetReloadRuntime,
  options: StaleAssetReloadOptions,
): boolean {
  const cooldownMs =
    options.cooldownMs ?? DEFAULT_STALE_ASSET_RELOAD_COOLDOWN_MS;
  const now = options.nowMs?.() ?? Date.now();
  const lastReloadAt = readLastReloadAt(runtime);
  if (lastReloadAt > 0 && now - lastReloadAt < cooldownMs) {
    return false;
  }

  writeLastReloadAt(runtime, now);
  const url = new URL(runtime.location.href);
  url.searchParams.set(STALE_ASSET_RELOAD_QUERY_PARAM, String(now));
  runtime.location.replace(url.toString());
  return true;
}

export function clearStaleAssetReloadMarker(
  runtime: Pick<
    StaleAssetReloadRuntime,
    'history' | 'location' | 'sessionStorage'
  > = window,
): boolean {
  const url = new URL(runtime.location.href);
  const marker = url.searchParams.get(STALE_ASSET_RELOAD_QUERY_PARAM);
  if (marker === null) {
    return false;
  }
  const markerTimestamp = Number(marker);
  if (Number.isFinite(markerTimestamp)) {
    writeLastReloadAt(runtime, markerTimestamp);
  }
  url.searchParams.delete(STALE_ASSET_RELOAD_QUERY_PARAM);
  runtime.history.replaceState(
    runtime.history.state,
    '',
    `${url.pathname}${url.search}${url.hash}`,
  );
  return true;
}

export function maybeReloadForStaleAssetLoadError(
  error: unknown,
  runtime: StaleAssetReloadRuntime = window,
  options: StaleAssetReloadOptions = {},
): boolean {
  if (!isStaleAssetLoadError(error)) {
    return false;
  }
  return requestCacheBustingReloadOnce(runtime, options);
}

export function installStaleAssetReloadHandler(
  runtime: StaleAssetReloadRuntime = window,
  options: StaleAssetReloadOptions = {},
): () => void {
  const handleVitePreloadError = (event: Event) => {
    const error = (event as Event & { payload?: unknown }).payload ?? event;
    if (maybeReloadForStaleAssetLoadError(error, runtime, options)) {
      event.preventDefault();
    }
  };
  const handleUnhandledRejection = (event: Event) => {
    const error = (event as PromiseRejectionEvent).reason;
    if (maybeReloadForStaleAssetLoadError(error, runtime, options)) {
      event.preventDefault();
    }
  };

  runtime.addEventListener('vite:preloadError', handleVitePreloadError);
  runtime.addEventListener('unhandledrejection', handleUnhandledRejection);

  return () => {
    runtime.removeEventListener('vite:preloadError', handleVitePreloadError);
    runtime.removeEventListener('unhandledrejection', handleUnhandledRejection);
  };
}
