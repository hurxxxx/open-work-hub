import { formatByteSize } from '@/src/platform/format/byte-size';
import {
  isDmImageMimeType,
  readyDmPendingAttachmentIds,
  uploadingDmPendingAttachmentCount,
} from '@open-alm/contracts/dm';

import type { DmMessageAttachment } from '../api/dm-api';

export type PendingAttachmentStatus = 'uploading' | 'ready' | 'failed';

export interface PendingAttachment {
  localId: string;
  file: File;
  status: PendingAttachmentStatus;
  attachment: DmMessageAttachment | null;
  error: string | null;
}

export interface CreateUploadingPendingAttachmentInput {
  localId: string;
  file: File;
}

export interface DmComposerAttachmentState {
  pendingAttachments: PendingAttachment[];
  attachmentActionId: string | null;
  draggingFiles: boolean;
}

export type DmComposerAttachmentAction =
  | { type: 'reset' }
  | { type: 'add'; attachment: PendingAttachment }
  | { type: 'uploaded'; localId: string; attachment: DmMessageAttachment }
  | { type: 'failed'; localId: string; error: string }
  | { type: 'remove'; localId: string }
  | { type: 'dragging'; dragging: boolean }
  | { type: 'action'; attachmentId: string | null }
  | { type: 'clearPending' };

export const DM_COMPOSER_ATTACHMENT_INITIAL_STATE: DmComposerAttachmentState = {
  pendingAttachments: [],
  attachmentActionId: null,
  draggingFiles: false,
};

export function dmComposerAttachmentReducer(
  state: DmComposerAttachmentState,
  action: DmComposerAttachmentAction,
): DmComposerAttachmentState {
  if (action.type === 'reset') {
    return DM_COMPOSER_ATTACHMENT_INITIAL_STATE;
  }
  if (action.type === 'add') {
    return {
      ...state,
      pendingAttachments: appendPendingAttachment(
        state.pendingAttachments,
        action.attachment,
      ),
    };
  }
  if (action.type === 'uploaded') {
    return {
      ...state,
      pendingAttachments: markPendingAttachmentReady(
        state.pendingAttachments,
        action.localId,
        action.attachment,
      ),
    };
  }
  if (action.type === 'failed') {
    return {
      ...state,
      pendingAttachments: markPendingAttachmentFailed(
        state.pendingAttachments,
        action.localId,
        action.error,
      ),
    };
  }
  if (action.type === 'remove') {
    return {
      ...state,
      pendingAttachments: removePendingAttachment(
        state.pendingAttachments,
        action.localId,
      ),
    };
  }
  if (action.type === 'dragging') return { ...state, draggingFiles: action.dragging };
  if (action.type === 'action') {
    return { ...state, attachmentActionId: action.attachmentId };
  }
  return { ...state, pendingAttachments: [] };
}

export function createUploadingPendingAttachment({
  localId,
  file,
}: CreateUploadingPendingAttachmentInput): PendingAttachment {
  return {
    localId,
    file,
    status: 'uploading',
    attachment: null,
    error: null,
  };
}

export function appendPendingAttachment(
  pendingAttachments: PendingAttachment[],
  attachment: PendingAttachment,
): PendingAttachment[] {
  return [...pendingAttachments, attachment];
}

export function markPendingAttachmentReady(
  pendingAttachments: PendingAttachment[],
  localId: string,
  attachment: DmMessageAttachment,
): PendingAttachment[] {
  return pendingAttachments.map((item) =>
    item.localId === localId
      ? {
          ...item,
          status: 'ready',
          attachment,
          error: null,
        }
      : item,
  );
}

export function markPendingAttachmentFailed(
  pendingAttachments: PendingAttachment[],
  localId: string,
  error: string,
): PendingAttachment[] {
  return pendingAttachments.map((item) =>
    item.localId === localId ? { ...item, status: 'failed', error } : item,
  );
}

export function removePendingAttachment(
  pendingAttachments: PendingAttachment[],
  localId: string,
): PendingAttachment[] {
  return pendingAttachments.filter((item) => item.localId !== localId);
}

export function createLocalAttachmentId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

export function isImageFile(file: File): boolean {
  return isDmImageMimeType(file);
}

export function dataTransferHasFiles(
  dataTransfer: Pick<DataTransfer, 'types'>,
): boolean {
  return Array.from(dataTransfer.types).includes('Files');
}

export interface DmComposerFileDragOverEvent {
  dataTransfer: Pick<DataTransfer, 'dropEffect' | 'types'>;
  preventDefault: () => void;
}

export function applyDmComposerFileDragOver(
  event: DmComposerFileDragOverEvent,
): boolean {
  if (!dataTransferHasFiles(event.dataTransfer)) {
    return false;
  }
  event.preventDefault();
  event.dataTransfer.dropEffect = 'copy';
  return true;
}

export function filesFromClipboardData(
  clipboard: Pick<DataTransfer, 'files' | 'items'>,
): File[] {
  const files = Array.from(clipboard.files);
  if (files.length) return files;
  return Array.from(clipboard.items).flatMap((item) => {
    if (item.kind !== 'file') return [];
    const file = item.getAsFile();
    return file ? [file] : [];
  });
}

export function readyDmAttachmentIds(
  pendingAttachments: PendingAttachment[],
): string[] {
  return readyPendingAttachmentIds(pendingAttachments);
}

export function readyPendingAttachmentIds(
  pendingAttachments: PendingAttachment[],
): string[] {
  return readyDmPendingAttachmentIds(pendingAttachments);
}

export function uploadingDmAttachmentCount(
  pendingAttachments: PendingAttachment[],
): number {
  return uploadingPendingAttachmentCount(pendingAttachments);
}

export function uploadingPendingAttachmentCount(
  pendingAttachments: PendingAttachment[],
): number {
  return uploadingDmPendingAttachmentCount(pendingAttachments);
}

export function formatAttachmentSize(
  sizeBytes: number,
  locale: string,
): string {
  return formatByteSize(sizeBytes, {
    fractionDigits: 'compact',
    locale,
    trailingZeros: 'trim',
    units: ['KB', 'MB', 'GB'],
  });
}
