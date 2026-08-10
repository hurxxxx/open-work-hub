import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type {
  WorkspaceBindingItem,
  WorkspaceItem,
  WorkspaceMemberBulkResponse,
  WorkspaceMemberItem,
  WorkspaceMembersResponse,
} from './admin-api';
import {
  useWorkspaceMembersDrawerController,
  type WorkspaceMembersDrawerMessages,
} from './useWorkspaceMembersDrawerController';
import type { WorkspaceMembersWorkflowPorts } from './workspace-members-workflow';

function workspace(overrides: Partial<WorkspaceItem> = {}): WorkspaceItem {
  return {
    id: 'workspace-1',
    key: 'workspace-1',
    name: 'Workspace 1',
    description: '',
    active: true,
    member_count: 2,
    ...overrides,
  } as WorkspaceItem;
}

function member(overrides: Partial<WorkspaceMemberItem> = {}): WorkspaceMemberItem {
  return {
    subject_type: 'user',
    subject_id: 'user-1',
    subject_label: 'Alice',
    subject_secondary: 'alice@example.com',
    role: 'member',
    user_status: 'active',
    last_login_at: null,
    ...overrides,
  } as WorkspaceMemberItem;
}

function binding(overrides: Partial<WorkspaceBindingItem> = {}): WorkspaceBindingItem {
  return {
    subject_type: 'user',
    subject_id: 'user-1',
    subject_label: 'Alice',
    subject_secondary: 'alice@example.com',
    role: 'member',
    ...overrides,
  } as WorkspaceBindingItem;
}

function membersResponse(
  overrides: Partial<WorkspaceMembersResponse> = {},
): WorkspaceMembersResponse {
  return {
    items: [
      member({ subject_id: 'current-user' }),
      member({ subject_id: 'user-2', subject_label: 'Bob' }),
    ],
    total: 2,
    page: 1,
    page_size: 25,
    role_counts: { admin: 1, member: 1 },
    user_count: 2,
    pending_count: 0,
    ...overrides,
  } as WorkspaceMembersResponse;
}

function bulkResponse(
  overrides: Partial<WorkspaceMemberBulkResponse> = {},
): WorkspaceMemberBulkResponse {
  return {
    succeeded: 1,
    failed: [],
    ...overrides,
  };
}

function ports(
  overrides: Partial<WorkspaceMembersWorkflowPorts> = {},
): WorkspaceMembersWorkflowPorts {
  return {
    listBindings: vi.fn().mockResolvedValue([]),
    listMembers: vi.fn().mockResolvedValue(membersResponse()),
    listCandidates: vi.fn().mockResolvedValue([]),
    bulkMembers: vi.fn().mockResolvedValue(bulkResponse()),
    updateMemberRole: vi.fn().mockResolvedValue(binding({ role: 'admin' })),
    removeMember: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

function messages(): WorkspaceMembersDrawerMessages {
  return {
    loadFailed: 'load failed',
    roleChanged: 'role changed',
    roleChangeFailed: 'role failed',
    removed: 'removed',
    removeFailed: 'remove failed',
    bulkRemovePartial: (succeeded, failed) =>
      `bulk remove partial ${succeeded}/${failed}`,
    bulkRemoved: (count) => `bulk removed ${count}`,
    bulkRemoveFailed: 'bulk remove failed',
    bulkRolePartial: (succeeded, failed) =>
      `bulk role partial ${succeeded}/${failed}`,
    bulkRoleChanged: (count) => `bulk role ${count}`,
    bulkRoleFailed: 'bulk role failed',
  };
}

function renderController(options: {
  open?: boolean;
  testPorts?: WorkspaceMembersWorkflowPorts;
  onChanged?: () => void;
  onError?: (message: string) => void;
  onSuccess?: (message: string) => void;
} = {}) {
  const testPorts = options.testPorts ?? ports();
  const rendered = renderHook(() =>
    useWorkspaceMembersDrawerController({
      open: options.open ?? true,
      workspace: workspace(),
      currentUserId: 'current-user',
      ports: testPorts,
      messages: messages(),
      onChanged: options.onChanged ?? vi.fn(),
      onError: options.onError ?? vi.fn(),
      onSuccess: options.onSuccess ?? vi.fn(),
      debounceMs: 0,
    }),
  );
  return { ...rendered, ports: testPorts };
}

describe('useWorkspaceMembersDrawerController', () => {
  it('loads a member page when opened', async () => {
    const testPorts = ports();
    const { result } = renderController({ testPorts });

    await waitFor(() => expect(result.current.state.data?.total).toBe(2));

    expect(testPorts.listMembers).toHaveBeenCalledWith('workspace-1', {
      q: undefined,
      role: undefined,
      page: 1,
      pageSize: 25,
      pendingOnly: false,
    });
    expect(result.current.derived.totalPages).toBe(1);
  });

  it('resets page when query and filters change', async () => {
    const testPorts = ports();
    const { result } = renderController({ testPorts });

    await waitFor(() => expect(result.current.state.data?.total).toBe(2));
    vi.mocked(testPorts.listMembers).mockClear();

    act(() => {
      result.current.actions.setPage(3);
    });
    await waitFor(() => {
      expect(testPorts.listMembers).toHaveBeenCalledWith(
        'workspace-1',
        expect.objectContaining({ page: 3 }),
      );
    });

    vi.mocked(testPorts.listMembers).mockClear();
    act(() => {
      result.current.actions.setQuery(' alice ');
    });
    await waitFor(() => {
      expect(testPorts.listMembers).toHaveBeenCalledWith('workspace-1', {
        q: 'alice',
        role: undefined,
        page: 1,
        pageSize: 25,
        pendingOnly: false,
      });
    });

    vi.mocked(testPorts.listMembers).mockClear();
    act(() => {
      result.current.actions.setRoleFilter('admin');
    });
    await waitFor(() => {
      expect(testPorts.listMembers).toHaveBeenCalledWith(
        'workspace-1',
        expect.objectContaining({
          role: ['admin'],
          page: 1,
          pendingOnly: false,
        }),
      );
    });

    vi.mocked(testPorts.listMembers).mockClear();
    act(() => {
      result.current.actions.setPendingOnly(true);
    });
    await waitFor(() => {
      expect(testPorts.listMembers).toHaveBeenCalledWith(
        'workspace-1',
        expect.objectContaining({
          role: undefined,
          page: 1,
          pendingOnly: true,
        }),
      );
    });
  });

  it('selects only current page members excluding the current user', async () => {
    const { result } = renderController();

    await waitFor(() => expect(result.current.state.data?.items).toHaveLength(2));

    expect(result.current.derived.allSelectableKeys).toEqual(['user:user-2']);

    act(() => {
      result.current.actions.toggleSelectAll();
    });

    expect(Array.from(result.current.derived.activeSelectedKeys)).toEqual([
      'user:user-2',
    ]);
    expect(result.current.derived.allSelectableSelected).toBe(true);
  });

  it('changes a single member role, reports success, reloads, and clears busy', async () => {
    const onChanged = vi.fn();
    const onSuccess = vi.fn();
    const testPorts = ports();
    const { result } = renderController({ testPorts, onChanged, onSuccess });

    await waitFor(() => expect(result.current.state.data?.items).toHaveLength(2));
    await act(async () => {
      await result.current.actions.singleRoleChange(
        member({ subject_id: 'user-2' }),
        'admin',
      );
    });

    expect(testPorts.updateMemberRole).toHaveBeenCalledWith(
      'workspace-1',
      'user',
      'user-2',
      'admin',
    );
    expect(onSuccess).toHaveBeenCalledWith('role changed');
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(result.current.state.busy).toBe(false);
    expect(testPorts.listMembers).toHaveBeenLastCalledWith(
      'workspace-1',
      expect.objectContaining({ page: 1, pageSize: 25 }),
    );
  });

  it('handles partial bulk role updates and clears selection and menu state', async () => {
    const onError = vi.fn();
    const testPorts = ports({
      bulkMembers: vi.fn().mockResolvedValue(
        bulkResponse({
          succeeded: 1,
          failed: [
            { subject_type: 'user', subject_id: 'user-3', detail: 'failed' },
          ],
        }),
      ),
    });
    const { result } = renderController({ testPorts, onError });

    await waitFor(() => expect(result.current.state.data?.items).toHaveLength(2));
    act(() => {
      result.current.actions.toggleSelect(member({ subject_id: 'user-2' }));
      result.current.actions.setBulkRoleOpen(true);
    });
    await act(async () => {
      await result.current.actions.bulkRole('admin');
    });

    expect(testPorts.bulkMembers).toHaveBeenCalledWith('workspace-1', {
      action: 'update_role',
      subjects: [{ subject_type: 'user', subject_id: 'user-2', role: 'admin' }],
    });
    expect(onError).toHaveBeenCalledWith('bulk role partial 1/1');
    expect(result.current.state.bulkRoleOpen).toBe(false);
    expect(Array.from(result.current.derived.activeSelectedKeys)).toEqual([]);
  });
});
