import { describe, expect, it, vi } from 'vitest';

import type { DmMessageAttachment } from '../api/dm-api';
import {
  DM_COMPOSER_ATTACHMENT_INITIAL_STATE,
  applyDmComposerFileDragOver,
  appendPendingAttachment,
  createUploadingPendingAttachment,
  dataTransferHasFiles,
  dmComposerAttachmentReducer,
  filesFromClipboardData,
  formatAttachmentSize,
  isImageFile,
  markPendingAttachmentFailed,
  markPendingAttachmentReady,
  readyDmAttachmentIds,
  readyPendingAttachmentIds,
  removePendingAttachment,
  uploadingDmAttachmentCount,
  uploadingPendingAttachmentCount,
  type PendingAttachment,
} from './dm-composer-attachments';

function file(name = 'screen.png', type = 'image/png'): File {
  return new File(['content'], name, { type });
}

function attachment(id: string): DmMessageAttachment {
  return {
    id,
    filename: `${id}.png`,
    is_image: true,
    preview_url: `/api/v1/dm/attachments/${id}/preview`,
    size_bytes: 1024,
  } as DmMessageAttachment;
}

function pending(
  overrides: Partial<PendingAttachment> = {},
): PendingAttachment {
  return {
    ...createUploadingPendingAttachment({
      localId: 'local-1',
      file: file(),
    }),
    ...overrides,
  };
}

describe('dm composer attachment model', () => {
  it('builds and transitions pending attachment queue items', () => {
    const initial = createUploadingPendingAttachment({
      localId: 'local-1',
      file: file('screen.png'),
    });
    const appended = appendPendingAttachment([], initial);
    const ready = markPendingAttachmentReady(
      appended,
      'local-1',
      attachment('attachment-1'),
    );
    const failed = markPendingAttachmentFailed(ready, 'local-1', 'Upload failed');

    expect(initial).toMatchObject({
      localId: 'local-1',
      status: 'uploading',
      attachment: null,
      error: null,
    });
    expect(ready[0]).toMatchObject({
      status: 'ready',
      attachment: { id: 'attachment-1' },
      error: null,
    });
    expect(failed[0]).toMatchObject({
      status: 'failed',
      attachment: { id: 'attachment-1' },
      error: 'Upload failed',
    });
    expect(removePendingAttachment(failed, 'local-1')).toEqual([]);
  });

  it('moves pending attachments through upload success and failure states', () => {
    const added = dmComposerAttachmentReducer(
      DM_COMPOSER_ATTACHMENT_INITIAL_STATE,
      { type: 'add', attachment: pending() },
    );
    const uploaded = dmComposerAttachmentReducer(added, {
      type: 'uploaded',
      localId: 'local-1',
      attachment: attachment('attachment-1'),
    });
    const failed = dmComposerAttachmentReducer(uploaded, {
      type: 'failed',
      localId: 'local-1',
      error: 'Upload failed',
    });

    expect(added.pendingAttachments).toHaveLength(1);
    expect(uploaded.pendingAttachments[0]).toMatchObject({
      status: 'ready',
      attachment: { id: 'attachment-1' },
      error: null,
    });
    expect(failed.pendingAttachments[0]).toMatchObject({
      status: 'failed',
      error: 'Upload failed',
    });
  });

  it('removes, clears, and resets composer attachment state', () => {
    const state = {
      pendingAttachments: [
        pending({ localId: 'local-1' }),
        pending({ localId: 'local-2' }),
      ],
      attachmentActionId: 'attachment-1',
      draggingFiles: true,
    };

    expect(
      dmComposerAttachmentReducer(state, {
        type: 'remove',
        localId: 'local-1',
      }).pendingAttachments.map((item) => item.localId),
    ).toEqual(['local-2']);
    expect(
      dmComposerAttachmentReducer(state, { type: 'clearPending' }),
    ).toMatchObject({ pendingAttachments: [], attachmentActionId: 'attachment-1' });
    expect(dmComposerAttachmentReducer(state, { type: 'reset' })).toEqual(
      DM_COMPOSER_ATTACHMENT_INITIAL_STATE,
    );
  });

  it('derives ready ids and uploading count from pending attachments', () => {
    const attachments = [
      pending({ localId: 'uploading' }),
      pending({
        localId: 'ready',
        status: 'ready',
        attachment: attachment('attachment-1'),
      }),
      pending({ localId: 'failed', status: 'failed', error: 'failed' }),
    ];

    expect(readyDmAttachmentIds(attachments)).toEqual(['attachment-1']);
    expect(readyPendingAttachmentIds(attachments)).toEqual(['attachment-1']);
    expect(uploadingDmAttachmentCount(attachments)).toBe(1);
    expect(uploadingPendingAttachmentCount(attachments)).toBe(1);
  });

  it('normalizes browser file inputs for images, clipboard fallback, and drag state', () => {
    const image = file('screen.png', 'image/png; charset=binary');
    const pdf = file('report.pdf', 'application/pdf');

    expect(isImageFile(image)).toBe(true);
    expect(isImageFile(pdf)).toBe(false);
    expect(dataTransferHasFiles({ types: ['Files'] } as DataTransfer)).toBe(true);
    expect(dataTransferHasFiles({ types: ['text/plain'] } as DataTransfer)).toBe(false);
    expect(
      filesFromClipboardData({
        files: [] as unknown as FileList,
        items: [
          { kind: 'string', getAsFile: () => null },
          { kind: 'file', getAsFile: () => pdf },
        ] as unknown as DataTransferItemList,
      }),
    ).toEqual([pdf]);
  });

  it('applies file drag-over browser policy only for file transfers', () => {
    const fileDragEvent = {
      dataTransfer: {
        dropEffect: 'none',
        types: ['Files'],
      },
      preventDefault: vi.fn(),
    };
    const textDragEvent = {
      dataTransfer: {
        dropEffect: 'none',
        types: ['text/plain'],
      },
      preventDefault: vi.fn(),
    };

    expect(applyDmComposerFileDragOver(fileDragEvent)).toBe(true);
    expect(fileDragEvent.preventDefault).toHaveBeenCalledTimes(1);
    expect(fileDragEvent.dataTransfer.dropEffect).toBe('copy');
    expect(applyDmComposerFileDragOver(textDragEvent)).toBe(false);
    expect(textDragEvent.preventDefault).not.toHaveBeenCalled();
    expect(textDragEvent.dataTransfer.dropEffect).toBe('none');
  });

  it('formats attachment sizes with compact units', () => {
    expect(formatAttachmentSize(512, 'en-US')).toBe('512 B');
    expect(formatAttachmentSize(1024, 'en-US')).toBe('1 KB');
    expect(formatAttachmentSize(1536, 'en-US')).toBe('1.5 KB');
    expect(formatAttachmentSize(1536, 'de-DE')).toBe('1,5 KB');
    expect(formatAttachmentSize(1024 * 1024, 'en-US')).toBe('1 MB');
    expect(formatAttachmentSize(1024 * 1024 * 12, 'en-US')).toBe('12 MB');
  });
});
