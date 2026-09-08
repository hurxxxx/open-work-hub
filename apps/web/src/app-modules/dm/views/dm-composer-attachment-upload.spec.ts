import { describe, expect, it, vi } from 'vitest';

import type { DmMessageAttachment } from '../api/dm-api';
import type { DmComposerAttachmentAction } from './dm-composer-attachments';
import { uploadDmComposerAttachments } from './dm-composer-attachment-upload';

function file(name = 'screen.png', type = 'image/png'): File {
  return new File(['content'], name, { type });
}

function attachment(id: string): DmMessageAttachment {
  return {
    id,
    filename: `${id}.png`,
    is_image: true,

    size_bytes: 1024,
  } as DmMessageAttachment;
}

describe('dm composer attachment upload', () => {
  it('does nothing without token, conversation, or files', async () => {
    const dispatch = vi.fn<(action: DmComposerAttachmentAction) => void>();
    const uploadAttachment = vi.fn();

    await uploadDmComposerAttachments({
      files: [file()],
      token: null,
      conversationId: 'thread-1',
      uploadAttachment,
      dispatch,
      createLocalId: () => 'local-1',
      onError: vi.fn(),
      fallbackErrorMessage: 'Upload failed',
    });
    await uploadDmComposerAttachments({
      files: [file()],
      token: 'token',
      conversationId: null,
      uploadAttachment,
      dispatch,
      createLocalId: () => 'local-1',
      onError: vi.fn(),
      fallbackErrorMessage: 'Upload failed',
    });
    await uploadDmComposerAttachments({
      files: [],
      token: 'token',
      conversationId: 'thread-1',
      uploadAttachment,
      dispatch,
      createLocalId: () => 'local-1',
      onError: vi.fn(),
      fallbackErrorMessage: 'Upload failed',
    });

    expect(dispatch).not.toHaveBeenCalled();
    expect(uploadAttachment).not.toHaveBeenCalled();
  });

  it('dispatches add then uploaded with the generated local id', async () => {
    const dispatch = vi.fn<(action: DmComposerAttachmentAction) => void>();
    const uploaded = attachment('attachment-1');
    const uploadAttachment = vi.fn().mockResolvedValue(uploaded);

    await uploadDmComposerAttachments({
      files: [file()],
      token: 'token',
      conversationId: 'thread-1',
      uploadAttachment,
      dispatch,
      createLocalId: () => 'local-1',
      onError: vi.fn(),
      fallbackErrorMessage: 'Upload failed',
    });

    expect(uploadAttachment).toHaveBeenCalledWith(
      'token',
      'thread-1',
      expect.any(File),
    );
    expect(dispatch.mock.calls.map(([action]) => action)).toEqual([
      {
        type: 'add',
        attachment: {
          localId: 'local-1',
          file: expect.any(File),
          status: 'uploading',
          attachment: null,
          error: null,
        },
      },
      { type: 'uploaded', localId: 'local-1', attachment: uploaded },
    ]);
  });

  it('dispatches failure and reports upload errors', async () => {
    const dispatch = vi.fn<(action: DmComposerAttachmentAction) => void>();
    const onError = vi.fn();
    const uploadAttachment = vi.fn().mockRejectedValue(new Error('Too large'));

    await uploadDmComposerAttachments({
      files: [file()],
      token: 'token',
      conversationId: 'thread-1',
      uploadAttachment,
      dispatch,
      createLocalId: () => 'local-1',
      onError,
      fallbackErrorMessage: 'Upload failed',
    });

    expect(dispatch.mock.calls.map(([action]) => action.type)).toEqual([
      'add',
      'failed',
    ]);
    expect(dispatch.mock.calls[1][0]).toEqual({
      type: 'failed',
      localId: 'local-1',
      error: 'Too large',
    });
    expect(onError).toHaveBeenCalledWith('Too large');
  });

  it('uses the fallback message for non-error rejections', async () => {
    const dispatch = vi.fn<(action: DmComposerAttachmentAction) => void>();
    const onError = vi.fn();
    const uploadAttachment = vi.fn().mockRejectedValue('bad');

    await uploadDmComposerAttachments({
      files: [file()],
      token: 'token',
      conversationId: 'thread-1',
      uploadAttachment,
      dispatch,
      createLocalId: () => 'local-1',
      onError,
      fallbackErrorMessage: 'Upload failed',
    });

    expect(dispatch.mock.calls[1][0]).toEqual({
      type: 'failed',
      localId: 'local-1',
      error: 'Upload failed',
    });
    expect(onError).toHaveBeenCalledWith('Upload failed');
  });

  it('uploads multiple files with independent local ids', async () => {
    const dispatch = vi.fn<(action: DmComposerAttachmentAction) => void>();
    const uploadAttachment = vi
      .fn()
      .mockResolvedValueOnce(attachment('attachment-1'))
      .mockResolvedValueOnce(attachment('attachment-2'));
    const createLocalId = vi
      .fn()
      .mockReturnValueOnce('local-1')
      .mockReturnValueOnce('local-2');

    await uploadDmComposerAttachments({
      files: [file('first.png'), file('second.png')],
      token: 'token',
      conversationId: 'thread-1',
      uploadAttachment,
      dispatch,
      createLocalId,
      onError: vi.fn(),
      fallbackErrorMessage: 'Upload failed',
    });

    const actions = dispatch.mock.calls.map(([action]) => action);
    expect(actions.filter((action) => action.type === 'add')).toMatchObject([
      { type: 'add', attachment: { localId: 'local-1' } },
      { type: 'add', attachment: { localId: 'local-2' } },
    ]);
    expect(actions.filter((action) => action.type === 'uploaded')).toEqual([
      {
        type: 'uploaded',
        localId: 'local-1',
        attachment: attachment('attachment-1'),
      },
      {
        type: 'uploaded',
        localId: 'local-2',
        attachment: attachment('attachment-2'),
      },
    ]);
  });
});
