import { parseAuthenticatedContentUrl } from '@/src/platform/browser/browser-download';
import type { DmMessageAttachment } from '../api/dm-api';

export interface DmImageViewerState {
  filename: string;
  attachmentId: string;
}
export interface DmAttachmentDownloadSpec {
  href: string;
  filename: string;
}

export function downloadSpecForAttachment(
  attachment: Pick<DmMessageAttachment, 'filename'>,
  responseUrl: string | null | undefined,
): DmAttachmentDownloadSpec | null {
  if (!responseUrl) return null;
  try {
    parseAuthenticatedContentUrl(responseUrl);
    return { href: responseUrl, filename: attachment.filename };
  } catch {
    return null;
  }
}
