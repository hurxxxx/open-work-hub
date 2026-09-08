import { describe, expect, it, vi } from 'vitest';

import type { DmMessageAttachment } from '../api/dm-api';
import {
  createDmAttachmentActionWorkflow,
  type DmAttachmentActionApi,
  type DmAttachmentBrowserAdapter,
} from './dm-attachment-action-workflow';
import type { DmComposerAttachmentAction } from './dm-composer-attachments';

function attachment(
  overrides: Partial<DmMessageAttachment> = {},
): DmMessageAttachment {
  return {
    content_type: 'image/png',

    filename: 'screen.png',
    id: 'attachment-1',
    is_image: true,

    size_bytes: 1024,
    ...overrides,
  };
}

function harness({
  api,
  busyAttachmentId = null,
  isCurrent = () => true,
}: {
  api?: Partial<DmAttachmentActionApi> | null;
  busyAttachmentId?: string | null;
  isCurrent?: () => boolean;
} = {}) {
  const actions: DmComposerAttachmentAction[] = [];
  const errors: Array<string | null> = [];
  const viewers: unknown[] = [];
  const browser: DmAttachmentBrowserAdapter = {
    download: vi.fn().mockResolvedValue(undefined),
  };
  const resolvedApi: DmAttachmentActionApi | null =
    api === null
      ? null
      : {
          getDownloadUrl: vi.fn(async () => ({
            url: '/api/v1/content#grant=example',
          })),
          ...api,
        };
  const workflow = createDmAttachmentActionWorkflow({
    api: resolvedApi,
    isCurrent,
    browser,
    busyAttachmentId,
    dispatchAttachmentAction: (action) => actions.push(action),
    messages: {
      downloadFailed: 'Download failed',
      previewFailed: 'Preview failed',
    },
    setError: (message) => errors.push(message),
    setImageViewer: (viewer) => viewers.push(viewer),
  });

  return { actions, api: resolvedApi, browser, errors, viewers, workflow };
}

describe('dm attachment action workflow', () => {
  it('opens the image viewer by identity so its component requests fresh access', async () => {
    const context = harness();

    await context.workflow.openImageAttachment(attachment());

    expect(context.actions).toEqual([
      { type: 'action', attachmentId: 'attachment-1' },
      { type: 'action', attachmentId: null },
    ]);
    expect(context.errors).toEqual([null]);
    expect(context.viewers).toEqual([
      {
        filename: 'screen.png',
        attachmentId: 'attachment-1',
      },
    ]);
  });

  it('downloads attachments through the browser adapter', async () => {
    const context = harness();

    await context.workflow.downloadAttachment(
      attachment({ filename: 'report.pdf', is_image: false }),
    );

    expect(context.api?.getDownloadUrl).toHaveBeenCalledWith('attachment-1');
    expect(context.browser.download).toHaveBeenCalledWith({
      filename: 'report.pdf',
      href: '/api/v1/content#grant=example',
    });
    expect(context.errors).toEqual([null]);
  });

  it('discards late grant responses after the account or conversation changes', async () => {
    let current = true;
    let resolve!: (value: { url: string }) => void;
    const context = harness({
      isCurrent: () => current,
      api: {
        getDownloadUrl: vi.fn(
          () =>
            new Promise((done) => {
              resolve = done;
            }),
        ),
      },
    });
    const pending = context.workflow.downloadAttachment(attachment());
    current = false;
    resolve({ url: '/api/v1/content#grant=old' });
    await pending;
    expect(context.browser.download).not.toHaveBeenCalled();
  });

  it('reports API errors and always clears the active action', async () => {
    const context = harness({
      api: {
        getDownloadUrl: vi.fn(async () => {
          throw new Error('No access');
        }),
      },
    });

    await context.workflow.downloadAttachment(attachment());

    expect(context.errors).toEqual([null, 'No access']);
    expect(context.actions).toEqual([
      { type: 'action', attachmentId: 'attachment-1' },
      { type: 'action', attachmentId: null },
    ]);
  });

  it('no-ops when unauthenticated or another attachment action is active', async () => {
    const noApi = harness({ api: null });
    await noApi.workflow.downloadAttachment(attachment());
    expect(noApi.actions).toEqual([]);

    const busy = harness({ busyAttachmentId: 'other-attachment' });
    await busy.workflow.openImageAttachment(attachment());
    expect(busy.actions).toEqual([]);
  });
});
