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
        const resolvedAt = now();
        for (const [mediaUrl, resolvers] of batch) {
          const resolvedUrl = resolved[mediaUrl];
          const renderUrl = resolvedUrl ?? mediaUrl;
          if (resolvedUrl) {
            cache.set(mediaUrl, {
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
    resolveFileUrl({ token, url }) {
      if (!url.startsWith('media:')) return Promise.resolve(url);
      if (!token) return Promise.resolve(url);

      const cached = cache.get(url);
      if (cached && cached.expiresAt > now()) {
        return Promise.resolve(cached.url);
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
