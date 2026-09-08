import type { BlockContent } from '@open-work-hub/ui';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { createInstance } from 'i18next';
import { resources } from '@/src/platform/i18n/resources';

import {
  useTaskDetailLinkedDocs,
  resolveTaskDetailDocPath,
  resolveTaskDetailPromotedDocContent,
} from './useTaskDetailLinkedDocs';

describe('task detail linked docs helpers', () => {
  it('prefers unsaved editor blocks when promoting a description', () => {
    const editorBlocks: BlockContent = [
      {
        id: 'draft-1',
        type: 'paragraph',
        props: {
          backgroundColor: 'default',
          textColor: 'default',
          textAlignment: 'left',
        },
        content: [{ type: 'text', text: 'Draft', styles: {} }],
        children: [],
      },
    ];
    const issueBlocks = [{ type: 'paragraph', content: 'Saved' }];

    expect(
      resolveTaskDetailPromotedDocContent({
        descriptionBlocks: editorBlocks,
        issueDescriptionBlocks: issueBlocks,
      }),
    ).toEqual(editorBlocks);
  });

  it('falls back to saved description blocks when the editor has no draft', () => {
    const issueBlocks = [{ type: 'paragraph', content: 'Saved' }];

    expect(
      resolveTaskDetailPromotedDocContent({
        descriptionBlocks: null,
        issueDescriptionBlocks: issueBlocks,
      }),
    ).toEqual(issueBlocks);
  });

  it('builds Docs document paths for linked resources', () => {
    expect(
      resolveTaskDetailDocPath({
        docId: 'doc-1',
      }),
    ).toBe('/apps/docs/documents/doc-1');
  });
});

const publication = vi.hoisted(() => ({
  confirm: vi.fn(),
  createNativeDoc: vi.fn(),
  listDocPages: vi.fn(),
  updateDocPage: vi.fn(),
  attachTaskDoc: vi.fn(),
  detachTaskDoc: vi.fn(),
}));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useConfirm: () => ({ confirm: publication.confirm, confirmDialog: null }),
}));
vi.mock('@/src/app-modules/docs/public-api', () => ({
  createNativeDoc: publication.createNativeDoc,
  listDocPages: publication.listDocPages,
  updateDocPage: publication.updateDocPage,
}));
vi.mock('../api/pms-api', async (original) => ({
  ...(await original<typeof import('../api/pms-api')>()),
  attachTaskDoc: publication.attachTaskDoc,
  detachTaskDoc: publication.detachTaskDoc,
}));

async function renderPublication(
  spaceId: string | null = 'space-1',
  canPublishDoc = true,
) {
  const i18n = createInstance();
  await i18n.init({ lng: 'ko-KR', resources, defaultNS: 'apps' });
  return renderHook(() =>
    useTaskDetailLinkedDocs({
      canEdit: true,
      canPublishDoc,
      descriptionBlocksRef: { current: null },
      issue: { id: 'task-1', title: 'Design', description_blocks: [] },
      setLinkedDocs: vi.fn(),
      setSaveError: vi.fn(),
      token: 'test-session',
      spaceId,
      t: i18n.t,
    }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  publication.confirm.mockResolvedValue(true);
  publication.createNativeDoc.mockResolvedValue({ id: 'doc-1' });
  publication.listDocPages.mockResolvedValue({ items: [] });
  publication.attachTaskDoc.mockResolvedValue({ items: [] });
});

describe('task description company publication', () => {
  it('does not publish project content with only task editing permission', async () => {
    const { result } = await renderPublication('space-1', false);
    await act(async () => {
      await result.current.handlePromoteDescriptionToDoc();
    });
    expect(publication.confirm).not.toHaveBeenCalled();
    expect(publication.createNativeDoc).not.toHaveBeenCalled();
    expect(publication.attachTaskDoc).not.toHaveBeenCalled();
  });
  it('does not create or link a document when the company transition is cancelled', async () => {
    publication.confirm.mockResolvedValue(false);
    const { result } = await renderPublication();
    await act(async () => {
      await result.current.handlePromoteDescriptionToDoc();
    });
    expect(publication.confirm).toHaveBeenCalledOnce();
    expect(publication.createNativeDoc).not.toHaveBeenCalled();
    expect(publication.attachTaskDoc).not.toHaveBeenCalled();
    expect(result.current.promotingDescription).toBe(false);
  });
  it('acknowledges the exact project target after explicit confirmation', async () => {
    const { result } = await renderPublication();
    await act(async () => {
      await result.current.handlePromoteDescriptionToDoc();
    });
    expect(publication.createNativeDoc).toHaveBeenCalledWith(
      'test-session',
      expect.objectContaining({
        primary_target: {
          app: 'pms',
          type: 'space',
          id: 'space-1',
          company_admin_read_acknowledged: true,
        },
      }),
    );
    expect(publication.attachTaskDoc).toHaveBeenCalledWith(
      'test-session',
      'task-1',
      'doc-1',
    );
  });
  it('keeps a promotion without a project personal', async () => {
    const { result } = await renderPublication(null, false);
    await act(async () => {
      await result.current.handlePromoteDescriptionToDoc();
    });
    expect(publication.confirm).not.toHaveBeenCalled();
    expect(publication.createNativeDoc).toHaveBeenCalledWith(
      'test-session',
      expect.objectContaining({ primary_target: null }),
    );
  });
  it('does not continue a confirmed publication after the task closes', async () => {
    let approve!: (value: boolean) => void;
    publication.confirm.mockReturnValue(
      new Promise<boolean>((resolve) => {
        approve = resolve;
      }),
    );
    const view = await renderPublication();
    let pending!: Promise<void>;
    act(() => {
      pending = view.result.current.handlePromoteDescriptionToDoc();
    });
    view.unmount();
    await act(async () => {
      approve(true);
      await pending;
    });
    expect(publication.createNativeDoc).not.toHaveBeenCalled();
  });
});

it.each(['link', 'unlink'] as const)(
  'ignores a late %s response after switching tasks',
  async (operation) => {
    let finish: (value: { items: [] }) => void = () => undefined;
    const pending = new Promise<{ items: [] }>((resolve) => {
      finish = resolve;
    });
    (operation === 'link'
      ? publication.attachTaskDoc
      : publication.detachTaskDoc
    ).mockReturnValueOnce(pending);
    const i18n = createInstance();
    await i18n.init({ lng: 'ko-KR', resources, defaultNS: 'apps' });
    const setLinkedDocs = vi.fn();
    const onUpdate = vi.fn();
    const { result, rerender } = renderHook(
      ({ taskId }) =>
        useTaskDetailLinkedDocs({
          canEdit: true,
          canPublishDoc: true,
          descriptionBlocksRef: { current: null },
          issue: { id: taskId, title: 'Task', description_blocks: [] },
          setLinkedDocs,
          setSaveError: vi.fn(),
          onUpdate,
          token: 'session',
          spaceId: 'space',
          t: i18n.t,
        }),
      { initialProps: { taskId: 'task-a' } },
    );
    let operationPromise: Promise<void>;
    act(() => {
      operationPromise =
        operation === 'link'
          ? result.current.handleLinkDoc('doc')
          : result.current.handleUnlinkDoc('doc');
    });
    rerender({ taskId: 'task-b' });
    await act(async () => {
      finish({ items: [] });
      await operationPromise;
    });
    expect(setLinkedDocs).not.toHaveBeenCalled();
    expect(onUpdate).not.toHaveBeenCalled();
  },
);
