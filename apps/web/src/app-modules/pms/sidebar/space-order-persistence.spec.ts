import { describe, expect, it } from 'vitest';

import type { DocsHubItem } from '@/src/app-modules/docs/public-api';
import type { PmsTaskList } from '../api/pms-api';
import { buildSpaceOrderChanges } from './space-order-persistence';

describe('space order persistence', () => {
  it('builds only changed list placement and document order patches', () => {
    const changes = buildSpaceOrderChanges({
      currentLists: [
        taskList({ id: 'list-1', folder_id: null, sort_order: 1 }),
        taskList({ id: 'list-2', folder_id: 'folder-1', sort_order: 2 }),
        taskList({
          id: 'list-archived',
          archived: true,
          folder_id: null,
          sort_order: 1,
        }),
      ],
      currentDocs: [
        docsHubItem({ id: 'doc-1', sortOrder: 1 }),
        docsHubItem({ id: 'doc-2', sortOrder: 2 }),
      ],
      payload: {
        lists: [
          {
            id: 'list-1',
            name: 'List 1',
            folder_id: 'folder-1',
            sort_order: 3,
            task_count: 0,
          },
          {
            id: 'list-2',
            name: 'List 2',
            folder_id: 'folder-1',
            sort_order: 2,
            task_count: 0,
          },
          {
            id: 'list-archived',
            name: 'Archived list',
            folder_id: null,
            sort_order: 3,
            task_count: 0,
          },
        ],
        docs: [
          { id: 'doc-1', title: 'Doc 1', sort_order: 2 },
          { id: 'doc-2', title: 'Doc 2', sort_order: 2 },
        ],
      },
    });

    expect(changes).toEqual({
      listChanges: [{ id: 'list-1', folder_id: 'folder-1', sort_order: 3 }],
      docChanges: [{ id: 'doc-1', sort_order: 2 }],
    });
  });
});

function taskList(overrides: Partial<PmsTaskList>): PmsTaskList {
  return {
    id: 'list-1',
    name: 'List',
    team_id: 'space-1',
    team_name: 'Space',
    folder_id: null,
    folder_name: null,
    sort_order: 1,
    task_count: 0,
    progress: 0,
    updated_at: '2026-01-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    status_mode: 'inherit',
    ...overrides,
  } as PmsTaskList;
}

function docsHubItem({
  sortOrder,
  ...overrides
}: Partial<DocsHubItem> & { sortOrder: number }): DocsHubItem {
  return {
    id: 'doc-1',
    title: 'Doc',
    updated_at: '2026-01-01T00:00:00Z',
    primary_target: {
      app: 'pms',
      type: 'space',
      id: 'space-1',
      sort_order: sortOrder,
      name: 'Space',
    },
    ...overrides,
  } as DocsHubItem;
}
