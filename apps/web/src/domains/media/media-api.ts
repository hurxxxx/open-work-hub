export interface MediaUploadResponse {
  id: string;
  url: string;
}

export async function uploadMedia(token: string, file: File): Promise<MediaUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch('/api/v1/media/upload', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail ?? `Upload failed with ${response.status}.`);
  }
  return payload as MediaUploadResponse;
}

export interface MediaResolveResponse {
  resolved: Record<string, string>;
}

export async function resolveMediaUrls(
  token: string,
  urls: string[],
): Promise<Record<string, string>> {
  if (urls.length === 0) return {};
  const response = await fetch('/api/v1/media/resolve', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ urls }),
  });
  if (!response.ok) return {};
  const data = (await response.json()) as MediaResolveResponse;
  return data.resolved;
}

export async function linkMedia(
  token: string,
  mediaIds: string[],
  resourceType: string,
  resourceId: string,
): Promise<boolean> {
  if (mediaIds.length === 0) return true;
  const response = await fetch('/api/v1/media/link', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      media_ids: mediaIds,
      resource_type: resourceType,
      resource_id: resourceId,
    }),
  });
  return response.ok;
}

export function extractMediaIds(blocks: unknown): string[] {
  const raw = JSON.stringify(blocks);
  const ids = new Set<string>();
  for (const match of raw.matchAll(/media:([0-9a-f-]{36})/g)) {
    ids.add(match[1]);
  }
  return [...ids];
}
