import type {
  DmAttachmentUrlResponse,
  DmMessageAttachment,
} from '../api/dm-api';
import {
  defaultBrowserDownloadAdapter,
  type BrowserDownloadAdapter,
  type BrowserDownloadAnchor,
} from '@/src/platform/browser/browser-download';
import {
  downloadSpecForAttachment,
  imageViewerForAttachment,
  type DmAttachmentDownloadSpec,
  type DmImageViewerState,
} from './dm-attachment-url';
import type { DmComposerAttachmentAction } from './dm-composer-attachments';

export interface DmAttachmentActionApi {
  getDownloadUrl(attachmentId: string): Promise<DmAttachmentUrlResponse>;
  getPreviewUrl(attachmentId: string): Promise<DmAttachmentUrlResponse>;
}

export interface DmAttachmentBrowserAdapter {
  download(spec: DmAttachmentDownloadSpec): void;
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

export function triggerDmAttachmentBrowserDownload(
  spec: DmAttachmentDownloadSpec,
  adapter: BrowserDownloadAdapter = defaultBrowserDownloadAdapter,
): void {
  const anchor = adapter.createAnchor() as BrowserDownloadAnchor & {
    rel?: string;
  };
  anchor.href = spec.href;
  anchor.download = spec.filename;
  anchor.rel = spec.rel;
  adapter.appendAnchor(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
  }
}

export function createDmAttachmentActionWorkflow({
  api,
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
    if (!api || busyAttachmentId) return;
    dispatchAttachmentAction({ type: 'action', attachmentId: attachment.id });
    setError(null);
    try {
      await action();
    } catch (caughtError) {
      setError(errorMessage(caughtError, fallbackMessage));
    } finally {
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
          const response = await api.getPreviewUrl(attachment.id);
          const viewer = imageViewerForAttachment(attachment, response.url);
          if (!viewer) {
            throw new Error(messages.previewFailed);
          }
          setImageViewer(viewer);
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
          const spec = downloadSpecForAttachment(attachment, response.url);
          if (!spec) {
            throw new Error(messages.downloadFailed);
          }
          browser.download(spec);
        },
      );
    },
  };
}
