import { resolveDmAttachmentUrl } from '@ai-do/contracts/dm';

import type { DmMessageAttachment } from '../api/dm-api';

export interface DmImageViewerState {
  filename: string;
  url: string;
}

export interface DmAttachmentDownloadSpec {
  href: string;
  filename: string;
  rel: 'noreferrer';
}

export function resolveWebDmAttachmentUrl(
  value: string | null | undefined,
  baseUrl = window.location.origin,
): string | null {
  return resolveDmAttachmentUrl(value, baseUrl);
}

export function imagePreviewUrlForAttachment(
  attachment: Pick<DmMessageAttachment, 'is_image' | 'preview_url'>,
  baseUrl?: string,
): string | null {
  if (!attachment.is_image) {
    return null;
  }
  return resolveWebDmAttachmentUrl(attachment.preview_url, baseUrl);
}

export function imageViewerForAttachment(
  attachment: Pick<DmMessageAttachment, 'filename'>,
  responseUrl: string | null | undefined,
  baseUrl?: string,
): DmImageViewerState | null {
  const url = resolveWebDmAttachmentUrl(responseUrl, baseUrl);
  return url ? { filename: attachment.filename, url } : null;
}

export function downloadSpecForAttachment(
  attachment: Pick<DmMessageAttachment, 'filename'>,
  responseUrl: string | null | undefined,
  baseUrl?: string,
): DmAttachmentDownloadSpec | null {
  const href = resolveWebDmAttachmentUrl(responseUrl, baseUrl);
  return href ? { href, filename: attachment.filename, rel: 'noreferrer' } : null;
}
