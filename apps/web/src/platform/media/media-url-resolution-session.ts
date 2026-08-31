export const MEDIA_URL_CACHE_TTL_MS = 50 * 60 * 1000;

export type ResolveMediaUrlsAdapter = (
  token: string,
  urls: string[],
) => Promise<Record<string, string>>;

export type MediaUrlResolutionScheduler = (
  task: () => void | Promise<void>,
) => void;

export interface CreateMediaUrlResolutionSessionOptions {
  resolveMediaUrls: ResolveMediaUrlsAdapter;
  now?: () => number;
  schedule?: MediaUrlResolutionScheduler;
  cacheTtlMs?: number;
}

export interface ResolveMediaUrlInput {
  token?: string | null;
  url: string;
}

export interface MediaUrlResolutionSession {
  resolveFileUrl(input: ResolveMediaUrlInput): Promise<string>;
  dispose(): void;
}

interface CacheEntry {
  url: string;
  expiresAt: number;
}

type PendingResolver = (url: string) => void;
type PendingTokenBatch = Map<string, PendingResolver[]>;

const defaultSchedule: MediaUrlResolutionScheduler = (task) => {
  queueMicrotask(() => {
    void task();
  });
};

function addPendingResolver(
  pendingByToken: Map<string, PendingTokenBatch>,
  token: string,
  url: string,
  resolve: PendingResolver,
) {
  let tokenBatch = pendingByToken.get(token);
  if (!tokenBatch) {
    tokenBatch = new Map();
    pendingByToken.set(token, tokenBatch);
  }

  const resolvers = tokenBatch.get(url) ?? [];
  resolvers.push(resolve);
  tokenBatch.set(url, resolvers);
}

export function createMediaUrlResolutionSession({
  resolveMediaUrls,
  now = () => Date.now(),
  schedule = defaultSchedule,
  cacheTtlMs = MEDIA_URL_CACHE_TTL_MS,
}: CreateMediaUrlResolutionSessionOptions): MediaUrlResolutionSession {
  const cache = new Map<string, CacheEntry>();
  const pendingByToken = new Map<string, PendingTokenBatch>();
  let scheduled = false;
  let disposed = false;

  function cacheKey(token: string, url: string): string {
    return `${token}\u0000${url}`;
  }

  function revokeCachedUrl(url: string): void {
    if (url.startsWith('blob:')) URL.revokeObjectURL(url);
  }

  async function flushPending() {
    scheduled = false;
    const batches = Array.from(pendingByToken.entries()).map(
      ([token, batch]) => [token, new Map(batch)] as const,
    );
    pendingByToken.clear();

    for (const [token, batch] of batches) {
      const urls = Array.from(batch.keys());
      try {
        const resolved = await resolveMediaUrls(token, urls);
        if (disposed) {
          Object.values(resolved).forEach(revokeCachedUrl);
          for (const [mediaUrl, resolvers] of batch) {
            resolvers.forEach((resolve) => resolve(mediaUrl));
          }
          continue;
        }
        const resolvedAt = now();
        for (const [mediaUrl, resolvers] of batch) {
          const resolvedUrl = resolved[mediaUrl];
          const renderUrl = resolvedUrl ?? mediaUrl;
          if (resolvedUrl) {
            const key = cacheKey(token, mediaUrl);
            const previous = cache.get(key);
            if (previous && previous.url !== renderUrl) {
              revokeCachedUrl(previous.url);
            }
            cache.set(key, {
              url: renderUrl,
              expiresAt: resolvedAt + cacheTtlMs,
            });
          }
          resolvers.forEach((resolve) => resolve(renderUrl));
        }
      } catch {
        for (const [mediaUrl, resolvers] of batch) {
          resolvers.forEach((resolve) => resolve(mediaUrl));
        }
      }
    }
  }

  return {
    dispose() {
      disposed = true;
      for (const entry of cache.values()) revokeCachedUrl(entry.url);
      cache.clear();
      for (const batch of pendingByToken.values()) {
        for (const [url, resolvers] of batch) {
          resolvers.forEach((resolve) => resolve(url));
        }
      }
      pendingByToken.clear();
    },
    resolveFileUrl({ token, url }) {
      if (disposed) return Promise.resolve(url);
      if (!url.startsWith('media:')) return Promise.resolve(url);
      if (!token) return Promise.resolve(url);

      const key = cacheKey(token, url);
      const cached = cache.get(key);
      if (cached && cached.expiresAt > now()) {
        return Promise.resolve(cached.url);
      }
      if (cached) {
        revokeCachedUrl(cached.url);
        cache.delete(key);
      }

      return new Promise<string>((resolve) => {
        addPendingResolver(pendingByToken, token, url, resolve);

        if (!scheduled) {
          scheduled = true;
          schedule(flushPending);
        }
      });
    },
  };
}
