import { describe, expect, it } from 'vitest';

import type { WorkspaceItem } from './admin-api';
import {
  filterAdminWorkspaces,
  replaceAdminWorkspace,
  selectWorkspaceIdAfterLoad,
} from './admin-workspaces-model';

function workspace(overrides: Partial<WorkspaceItem> = {}): WorkspaceItem {
  return {
    active: true,
    created_at: null,
    description: 'Delivery operations',
    doc_count: 0,
    id: 'workspace-a',
    key: 'alpha',
    meeting_count: 0,
    member_count: 0,
    name: 'Alpha',
    team_count: 0,
    updated_at: null,
    ...overrides,
  };
}

describe('admin workspaces model', () => {
  it('selects preserved, current, then active fallback workspace after load', () => {
    const workspaces = [
      workspace({ id: 'archived', active: false, name: 'Archived' }),
      workspace({ id: 'active', key: 'active', name: 'Active' }),
    ];

    expect(
      selectWorkspaceIdAfterLoad({
        currentWorkspaceId: 'active',
        preserveWorkspaceId: 'archived',
        workspaces,
      }),
    ).toBe('archived');
    expect(
      selectWorkspaceIdAfterLoad({
        currentWorkspaceId: 'active',
        preserveWorkspaceId: 'missing',
        workspaces,
      }),
    ).toBe('active');
    expect(selectWorkspaceIdAfterLoad({ workspaces })).toBe('active');
  });

  it('filters by active state and text fields, then sorts active first by name', () => {
    const workspaces = [
      workspace({
        id: 'zeta',
        key: 'zeta',
        name: 'Zeta',
      }),
      workspace({
        active: false,
        description: 'Legacy archive',
        id: 'archive',
        key: 'archive',
        name: 'Archive',
      }),
      workspace({
        id: 'alpha',
        key: 'alpha',
        name: 'Alpha',
      }),
    ];

    expect(
      filterAdminWorkspaces({
        filter: 'all',
        locale: 'en',
        searchQuery: '',
        workspaces,
      }).map((item) => item.id),
    ).toEqual(['alpha', 'zeta', 'archive']);
    expect(
      filterAdminWorkspaces({
        filter: 'archived',
        locale: 'en',
        searchQuery: 'legacy',
        workspaces,
      }).map((item) => item.id),
    ).toEqual(['archive']);
  });

  it('replaces workspace items without changing other rows', () => {
    const current = [
      workspace({ id: 'a', name: 'Alpha' }),
      workspace({ id: 'b', name: 'Beta' }),
    ];

    expect(
      replaceAdminWorkspace(current, workspace({ id: 'b', name: 'Beta 2' })),
    ).toEqual([
      workspace({ id: 'a', name: 'Alpha' }),
      workspace({ id: 'b', name: 'Beta 2' }),
    ]);
  });
});
