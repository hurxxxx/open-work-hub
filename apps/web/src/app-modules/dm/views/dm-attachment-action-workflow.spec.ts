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
    download_url: '/api/v1/dm/attachments/attachment-1/download',
    filename: 'screen.png',
    id: 'attachment-1',
    is_image: true,
    preview_url: '/api/v1/dm/attachments/attachment-1/preview',
    size_bytes: 1024,
    ...overrides,
  };
}

function harness({
  api,
  busyAttachmentId = null,
}: {
  api?: Partial<DmAttachmentActionApi> | null;
  busyAttachmentId?: string | null;
} = {}) {
  const actions: DmComposerAttachmentAction[] = [];
  const errors: Array<string | null> = [];
  const viewers: unknown[] = [];
  const browser: DmAttachmentBrowserAdapter = { download: vi.fn() };
  const resolvedApi: DmAttachmentActionApi | null =
    api === null
      ? null
      : {
          getDownloadUrl: vi.fn(async () => ({
            url: '/api/v1/dm/attachments/attachment-1/download',
          })),
          getPreviewUrl: vi.fn(async () => ({
            url: '/api/v1/dm/attachments/attachment-1/preview',
          })),
          ...api,
        };
  const workflow = createDmAttachmentActionWorkflow({
    api: resolvedApi,
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
  it('opens image attachments through a preview URL', async () => {
    const context = harness();

    await context.workflow.openImageAttachment(attachment());

    expect(context.actions).toEqual([
      { type: 'action', attachmentId: 'attachment-1' },
      { type: 'action', attachmentId: null },
    ]);
    expect(context.errors).toEqual([null]);
    expect(context.api?.getPreviewUrl).toHaveBeenCalledWith('attachment-1');
    expect(context.viewers).toEqual([
      {
        filename: 'screen.png',
        url: 'http://localhost:3000/api/v1/dm/attachments/attachment-1/preview',
      },
    ]);
  });

  it('reports preview fallback errors when the returned URL is unsafe', async () => {
    const context = harness({
      api: {
        getPreviewUrl: vi.fn(async () => ({
          url: 'https://cdn.example.test/screen.png',
        })),
      },
    });

    await context.workflow.openImageAttachment(attachment());

    expect(context.viewers).toEqual([]);
    expect(context.errors).toEqual([null, 'Preview failed']);
    expect(context.actions.at(-1)).toEqual({ type: 'action', attachmentId: null });
  });

  it('downloads attachments through the browser adapter', async () => {
    const context = harness();

    await context.workflow.downloadAttachment(
      attachment({ filename: 'report.pdf', is_image: false }),
    );

    expect(context.api?.getDownloadUrl).toHaveBeenCalledWith('attachment-1');
    expect(context.browser.download).toHaveBeenCalledWith({
      filename: 'report.pdf',
      href: 'http://localhost:3000/api/v1/dm/attachments/attachment-1/download',
      rel: 'noreferrer',
    });
    expect(context.errors).toEqual([null]);
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
    expect(busy.api?.getPreviewUrl).not.toHaveBeenCalled();
  });
});
