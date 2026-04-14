import { useCallback, useRef } from 'react';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { linkMedia, uploadMedia, resolveMediaUrls } from './media-api';

const CACHE_TTL_MS = 50 * 60 * 1000; // 50 minutes (presigned URLs expire in 1h)

interface CacheEntry {
  url: string;
  expiresAt: number;
}

export type MediaResourceType = 'issue' | 'space_doc_page' | 'docs_native_page';

export interface MediaLinkTarget {
  resourceType: MediaResourceType;
  resourceId: string;
}

export function useMediaUpload() {
  const { token } = useAuth();
  const cacheRef = useRef(new Map<string, CacheEntry>());
  const pendingRef = useRef(new Map<string, Array<(url: string) => void>>());
  const scheduledRef = useRef(false);

  const uploadFile = useCallback(
    async (file: File): Promise<string> => {
      if (!token) throw new Error('Authentication required.');
      const result = await uploadMedia(token, file);
      return result.url; // "media:{id}"
    },
    [token],
  );

  const createLinkedUploadFile = useCallback(
    (target: MediaLinkTarget | null | undefined) => {
      if (!token) return undefined;
      return async (file: File): Promise<string> => {
        const result = await uploadMedia(token, file);
        if (target?.resourceId) {
          await linkMedia(
            token,
            [result.id],
            target.resourceType,
            target.resourceId,
          ).catch(() => undefined);
        }
        return result.url;
      };
    },
    [token],
  );

  const resolveFileUrl = useCallback(
    (url: string): Promise<string> => {
      if (!url.startsWith('media:')) return Promise.resolve(url);
      if (!token) return Promise.resolve(url);

      // Check cache
      const cached = cacheRef.current.get(url);
      if (cached && cached.expiresAt > Date.now()) {
        return Promise.resolve(cached.url);
      }

      // Batch via microtask
      return new Promise<string>((resolve) => {
        const pending = pendingRef.current;
        if (!pending.has(url)) pending.set(url, []);
        pending.get(url)!.push(resolve);

        if (!scheduledRef.current) {
          scheduledRef.current = true;
          queueMicrotask(async () => {
            scheduledRef.current = false;
            const batch = new Map(pending);
            pending.clear();

            const urls = [...batch.keys()];
            try {
              const resolved = await resolveMediaUrls(token, urls);
              const now = Date.now();
              for (const [mediaUrl, resolvers] of batch) {
                const presigned = resolved[mediaUrl] ?? mediaUrl;
                if (resolved[mediaUrl]) {
                  cacheRef.current.set(mediaUrl, {
                    url: presigned,
                    expiresAt: now + CACHE_TTL_MS,
                  });
                }
                resolvers.forEach((r) => r(presigned));
              }
            } catch {
              for (const [mediaUrl, resolvers] of batch) {
                resolvers.forEach((r) => r(mediaUrl));
              }
            }
          });
        }
      });
    },
    [token],
  );

  return {
    uploadFile: token ? uploadFile : undefined,
    createLinkedUploadFile: token ? createLinkedUploadFile : undefined,
    resolveFileUrl: token ? resolveFileUrl : undefined,
  };
}
