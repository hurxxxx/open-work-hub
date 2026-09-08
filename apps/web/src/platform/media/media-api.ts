import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { authenticatedContentObjectUrl } from '@/src/platform/browser/browser-download';

export type MediaUploadResponse = ApiSchema<'MediaUploadResponse'>;

export async function uploadMedia(
  token: string,
  file: File,
): Promise<MediaUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetchJson<MediaUploadResponse>('/api/v1/media/upload', token, {
    method: 'POST',
    body: formData,
  });
}

export type MediaResolveResponse = ApiSchema<'MediaResolveResponse'>;

export async function resolveMediaUrls(
  token: string,
  urls: string[],
): Promise<Record<string, string>> {
  if (urls.length === 0) return {};
  try {
    const data = await apiFetchJson<MediaResolveResponse>(
      '/api/v1/media/resolve',
      token,
      {
        method: 'POST',
        body: JSON.stringify({ urls }),
      },
    );
    const resolvedEntries = await Promise.all(
      Object.entries(data.resolved).map(async ([mediaUrl, contentUrl]) => {
        try {
          return [
            mediaUrl,
            await authenticatedContentObjectUrl(token, contentUrl),
          ] as const;
        } catch {
          return null;
        }
      }),
    );
    return Object.fromEntries(
      resolvedEntries.filter(
        (entry): entry is readonly [string, string] => entry !== null,
      ),
    );
  } catch (error) {
    if (error instanceof ApiRequestError) {
      return {};
    }
    throw error;
  }
}

export async function linkMedia(
  token: string,
  mediaIds: string[],
  resourceType: string,
  resourceId: string,
): Promise<boolean> {
  if (mediaIds.length === 0) return true;
  try {
    await apiFetchJson<void>('/api/v1/media/link', token, {
      method: 'POST',
      body: JSON.stringify({
        media_ids: mediaIds,
        resource_type: resourceType,
        resource_id: resourceId,
      }),
    });
    return true;
  } catch (error) {
    if (error instanceof ApiRequestError) {
      return false;
    }
    throw error;
  }
}

export function extractMediaIds(blocks: unknown): string[] {
  const raw = JSON.stringify(blocks);
  const ids = new Set<string>();
  for (const match of raw.matchAll(/media:([0-9a-f-]{36})/g)) {
    ids.add(match[1]);
  }
  return [...ids];
}
