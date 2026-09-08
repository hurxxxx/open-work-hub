import { downloadAuthenticatedContent } from '@/src/platform/browser/browser-download';
import type {
  DmAttachmentUrlResponse,
  DmMessageAttachment,
} from '../api/dm-api';
import {
  downloadSpecForAttachment,
  type DmAttachmentDownloadSpec,
  type DmImageViewerState,
} from './dm-attachment-url';
import type { DmComposerAttachmentAction } from './dm-composer-attachments';

export interface DmAttachmentActionApi {
  getDownloadUrl(attachmentId: string): Promise<DmAttachmentUrlResponse>;
}

export interface DmAttachmentBrowserAdapter {
  download(spec: DmAttachmentDownloadSpec): Promise<void>;
}

export interface DmAttachmentActionMessages {
  downloadFailed: string;
  previewFailed: string;
}

export interface DmAttachmentActionWorkflow {
  downloadAttachment(attachment: DmMessageAttachment): Promise<void>;
  openImageAttachment(attachment: DmMessageAttachment): Promise<void>;
}

export interface DmAttachmentActionWorkflowOptions {
  api: DmAttachmentActionApi | null;
  isCurrent: () => boolean;
  browser: DmAttachmentBrowserAdapter;
  busyAttachmentId: string | null;
  dispatchAttachmentAction: (action: DmComposerAttachmentAction) => void;
  messages: DmAttachmentActionMessages;
  setError(message: string | null): void;
  setImageViewer(viewer: DmImageViewerState): void;
}

function errorMessage(caughtError: unknown, fallback: string): string {
  return caughtError instanceof Error ? caughtError.message : fallback;
}

export async function triggerDmAttachmentBrowserDownload(
  token: string,
  spec: DmAttachmentDownloadSpec,
): Promise<void> {
  await downloadAuthenticatedContent(token, spec.href, spec.filename);
}

export function createDmAttachmentActionWorkflow({
  api,
  isCurrent,
  browser,
  busyAttachmentId,
  dispatchAttachmentAction,
  messages,
  setError,
  setImageViewer,
}: DmAttachmentActionWorkflowOptions): DmAttachmentActionWorkflow {
  const withAttachmentAction = async (
    attachment: DmMessageAttachment,
    fallbackMessage: string,
    action: () => Promise<void>,
  ) => {
    if (!api || busyAttachmentId || !isCurrent()) return;
    dispatchAttachmentAction({ type: 'action', attachmentId: attachment.id });
    setError(null);
    try {
      await action();
    } catch (caughtError) {
      if (isCurrent()) setError(errorMessage(caughtError, fallbackMessage));
    } finally {
      if (isCurrent())
        dispatchAttachmentAction({ type: 'action', attachmentId: null });
    }
  };

  return {
    async openImageAttachment(attachment) {
      await withAttachmentAction(
        attachment,
        messages.previewFailed,
        async () => {
          if (!api) return;
          if (isCurrent())
            setImageViewer({
              filename: attachment.filename,
              attachmentId: attachment.id,
            });
        },
      );
    },

    async downloadAttachment(attachment) {
      await withAttachmentAction(
        attachment,
        messages.downloadFailed,
        async () => {
          if (!api) return;
          const response = await api.getDownloadUrl(attachment.id);
          if (!isCurrent()) return;
          const spec = downloadSpecForAttachment(attachment, response.url);
          if (!spec) {
            throw new Error(messages.downloadFailed);
          }
          await browser.download(spec);
        },
      );
    },
  };
}
