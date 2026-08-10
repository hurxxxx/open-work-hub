import type { DmMessageAttachment } from '../api/dm-api';
import {
  createUploadingPendingAttachment,
  type DmComposerAttachmentAction,
  type PendingAttachment,
} from './dm-composer-attachments';

export interface UploadDmComposerAttachmentsOptions {
  files: File[];
  token: string | null | undefined;
  conversationId: string | null | undefined;
  uploadAttachment: (
    token: string,
    conversationId: string,
    file: File,
  ) => Promise<DmMessageAttachment>;
  dispatch: (action: DmComposerAttachmentAction) => void;
  createLocalId: () => string;
  onError: (message: string) => void;
  fallbackErrorMessage: string;
}

export function uploadDmComposerAttachments({
  files,
  token,
  conversationId,
  uploadAttachment,
  dispatch,
  createLocalId,
  onError,
  fallbackErrorMessage,
}: UploadDmComposerAttachmentsOptions): Promise<void[]> {
  if (!token || !conversationId || files.length === 0) {
    return Promise.resolve([]);
  }

  return Promise.all(
    files.map(async (file) => {
      const localId = createLocalId();
      const pendingAttachment: PendingAttachment = createUploadingPendingAttachment({
        localId,
        file,
      });
      dispatch({ type: 'add', attachment: pendingAttachment });

      try {
        const attachment = await uploadAttachment(token, conversationId, file);
        dispatch({ type: 'uploaded', localId, attachment });
      } catch (caughtError) {
        const message =
          caughtError instanceof Error ? caughtError.message : fallbackErrorMessage;
        dispatch({ type: 'failed', localId, error: message });
        onError(message);
      }
    }),
  );
}
