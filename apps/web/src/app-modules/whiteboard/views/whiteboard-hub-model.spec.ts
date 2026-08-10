import { describe, expect, it } from 'vitest';

import type {
  WhiteboardDetail,
  WhiteboardHubItem,
} from '../api/whiteboard-api';
import {
  VIEW_MODE_STORAGE_KEY,
  WHITEBOARD_HUB_PAGE_SIZE,
  WHITEBOARD_VIEW_INITIAL_STATE,
  buildWhiteboardCreatePayload,
  buildWhiteboardHubItemPath,
  buildWhiteboardHubListParams,
  buildWhiteboardHubRootPath,
  readStoredLayoutMode,
  readWhiteboardTargetFilter,
  viewFromSearch,
  whiteboardViewReducer,
  writeStoredLayoutMode,
  type WhiteboardHubPathUser,
} from './whiteboard-hub-model';

function hubItem(
  overrides: Partial<WhiteboardHubItem> = {},
): WhiteboardHubItem {
  return {
    id: 'board-1',
    title: 'Board',
    ...overrides,
  } as WhiteboardHubItem;
}

function detail(overrides: Partial<WhiteboardDetail> = {}): WhiteboardDetail {
  return {
    ...hubItem(overrides),
    scene: { elements: [], appState: {}, files: {} },
    ...overrides,
  } as WhiteboardDetail;
}

function pathUser(): WhiteboardHubPathUser {
  return {
    default_workspace_id: 'workspace-default',
    workspaces: [
      { id: 'workspace-default', slug: 'default' },
      { id: 'workspace-side', slug: 'side' },
    ],
  } as WhiteboardHubPathUser;
}

function memoryStorage(
  initial: Record<string, string> = {},
): Pick<Storage, 'getItem' | 'setItem'> {
  const values = { ...initial };
  return {
    getItem(key: string) {
      return values[key] ?? null;
    },
    setItem(key: string, value: string) {
      values[key] = value;
    },
  };
}

describe('whiteboard hub model', () => {
  it('normalizes hub view query values', () => {
    expect(viewFromSearch('mine')).toBe('mine');
    expect(viewFromSearch('recent')).toBe('recent');
    expect(viewFromSearch('favorites')).toBe('favorites');
    expect(viewFromSearch('archived')).toBe('archived');
    expect(viewFromSearch('trash')).toBe('archived');
    expect(viewFromSearch('unknown')).toBe('all');
    expect(viewFromSearch(null)).toBe('all');
  });

  it('reads a complete target filter from search params', () => {
    expect(
      readWhiteboardTargetFilter(
        new URLSearchParams(
          'target_app=pms&target_type=issue&target_id=issue-1',
        ),
      ),
    ).toEqual({
      app: 'pms',
      type: 'issue',
      id: 'issue-1',
    });

    expect(
      readWhiteboardTargetFilter(new URLSearchParams('space_id=space-1')),
    ).toEqual({
      app: 'pms',
      type: 'space',
      id: 'space-1',
    });

    expect(
      readWhiteboardTargetFilter(
        new URLSearchParams('target_app=pms&target_type=issue'),
      ),
    ).toBeNull();
  });

  it('builds list params from view, query, sort, and target filter state', () => {
    expect(
      buildWhiteboardHubListParams({
        view: 'recent',
        query: 'planning',
        sortValue: 'viewed_desc',
        targetFilter: { app: 'pms', type: 'issue', id: 'issue-1' },
      }),
    ).toEqual({
      view: 'recent',
      q: 'planning',
      sort_by: 'last_viewed_at',
      sort_dir: 'desc',
      page_size: WHITEBOARD_HUB_PAGE_SIZE,
      space_id: undefined,
      target_app: 'pms',
      target_type: 'issue',
      target_id: 'issue-1',
    });

    expect(
      buildWhiteboardHubListParams({
        view: 'all',
        query: '',
        sortValue: 'updated_desc',
        targetFilter: { app: 'pms', type: 'space', id: 'space-1' },
      }),
    ).toMatchObject({
      space_id: 'space-1',
      target_app: undefined,
      target_type: undefined,
      target_id: undefined,
    });

    expect(
      buildWhiteboardHubListParams({
        view: 'all',
        query: '',
        sortValue: 'title_asc',
        targetFilter: null,
      }),
    ).toMatchObject({
      view: 'all',
      q: '',
      sort_by: 'title',
      sort_dir: 'asc',
      page_size: WHITEBOARD_HUB_PAGE_SIZE,
    });
  });

  it('builds create payloads for contextual and workspace-created boards', () => {
    expect(
      buildWhiteboardCreatePayload({
        title: 'Untitled',
        targetFilter: { app: 'pms', type: 'issue', id: 'issue-1' },
        currentWorkspaceId: 'workspace-1',
        itemCount: 4,
      }),
    ).toEqual({
      title: 'Untitled',
      source_app: 'pms',
      source_kind: 'manual',
      primary_target: {
        app: 'pms',
        type: 'issue',
        id: 'issue-1',
        sort_order: 4,
      },
    });

    expect(
      buildWhiteboardCreatePayload({
        title: 'Untitled',
        targetFilter: null,
        currentWorkspaceId: 'workspace-1',
        itemCount: 4,
      }),
    ).toEqual({
      title: 'Untitled',
      source_app: 'whiteboard',
      source_kind: 'manual',
      primary_target: null,
    });

    expect(
      buildWhiteboardCreatePayload({
        title: 'Untitled',
        targetFilter: null,
        currentWorkspaceId: 'workspace-1',
        itemCount: 4,
        visibility: 'workspace',
      }),
    ).toEqual({
      title: 'Untitled',
      source_app: 'whiteboard',
      source_kind: 'manual',
      primary_target: {
        app: 'whiteboard',
        type: 'workspace_sidebar',
        id: 'workspace-1',
        sort_order: 0,
      },
    });

    expect(
      buildWhiteboardCreatePayload({
        title: 'Untitled',
        targetFilter: null,
        currentWorkspaceId: null,
        itemCount: 4,
        visibility: 'workspace',
      }),
    ).toMatchObject({
      source_app: 'whiteboard',
      source_kind: 'manual',
      primary_target: null,
    });
  });

  it('builds item and hub root paths while preserving search params', () => {
    const searchParams = new URLSearchParams('view=recent&target_id=target-1');

    expect(
      buildWhiteboardHubItemPath({
        itemId: 'board-1',
        searchParams,
        user: pathUser(),
        workspaceSlug: 'team space',
      }),
    ).toBe(
      '/w/team%20space/whiteboard/board-1?view=recent&target_id=target-1',
    );

    expect(
      buildWhiteboardHubRootPath({
        searchParams,
        user: pathUser(),
        workspaceSlug: null,
      }),
    ).toBe(
      '/w/default/whiteboard?view=recent&target_id=target-1',
    );
  });

  it('reads and writes the stored layout mode', () => {
    const storage = memoryStorage();

    expect(readStoredLayoutMode(storage)).toBe('cards');
    writeStoredLayoutMode('list', storage);
    expect(readStoredLayoutMode(storage)).toBe('list');
    writeStoredLayoutMode('cards', storage);
    expect(storage.getItem(VIEW_MODE_STORAGE_KEY)).toBe('cards');
    expect(readStoredLayoutMode(null)).toBe('cards');
  });

  it('keeps list state updates deterministic', () => {
    const first = detail({ id: 'board-1', title: 'First' });
    const second = detail({ id: 'board-2', title: 'Second' });
    const withFirst = whiteboardViewReducer(WHITEBOARD_VIEW_INITIAL_STATE, {
      type: 'upsertItem',
      item: first,
    });
    const withSecond = whiteboardViewReducer(withFirst, {
      type: 'upsertItem',
      item: second,
    });
    const updated = whiteboardViewReducer(withSecond, {
      type: 'upsertItem',
      item: detail({ id: 'board-1', title: 'First renamed' }),
    });

    expect(withFirst.items.map((item) => item.id)).toEqual(['board-1']);
    expect(withSecond.items.map((item) => item.id)).toEqual([
      'board-2',
      'board-1',
    ]);
    expect(updated.items.map((item) => item.id)).toEqual([
      'board-2',
      'board-1',
    ]);
    expect(updated.items[1]?.title).toBe('First renamed');
  });

  it('removes restored boards in archived view and patches them elsewhere', () => {
    const state = {
      ...WHITEBOARD_VIEW_INITIAL_STATE,
      items: [hubItem({ id: 'board-1', title: 'Archived' })],
    };
    const restored = detail({ id: 'board-1', title: 'Restored' });

    expect(
      whiteboardViewReducer(state, {
        type: 'restoreItem',
        item: restored,
        archivedView: true,
      }).items,
    ).toEqual([]);

    expect(
      whiteboardViewReducer(state, {
        type: 'restoreItem',
        item: restored,
        archivedView: false,
      }).items[0]?.title,
    ).toBe('Restored');
  });
});
