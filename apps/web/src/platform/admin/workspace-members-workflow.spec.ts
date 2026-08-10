import { describe, expect, it } from 'vitest';

import type {
  WorkspaceBindingItem,
  WorkspaceMemberBulkResponse,
  WorkspaceMemberCandidate,
  WorkspaceMemberItem,
  WorkspaceMembersResponse,
} from './admin-api';
import type { SubjectSelectionState } from './admin-shared';
import type { WorkspaceMembersWorkflowPorts } from './workspace-members-workflow';
import {
  addWorkspaceMembersWorkflow,
  bulkRemoveWorkspaceMembersWorkflow,
  bulkUpdateWorkspaceMemberRolesWorkflow,
  changeWorkspaceMemberRoleWorkflow,
  loadWorkspaceMemberCandidatesWorkflow,
  loadWorkspaceMembersPageWorkflow,
  nextWorkspaceMemberCount,
  refreshWorkspaceMemberCountWorkflow,
  reloadWorkspaceBindingsWorkflow,
  removeWorkspaceMemberWorkflow,
  workspaceBindingsWithUpdatedMember,
  workspaceBindingsWithoutMember,
  workspaceMemberCandidateQuery,
  workspaceMembersBulkOutcome,
  workspaceMembersListParams,
} from './workspace-members-workflow';

function binding(
  overrides: Partial<WorkspaceBindingItem>,
): WorkspaceBindingItem {
  return {
    subject_type: 'user',
    subject_id: 'user-1',
    subject_label: 'Alice',
    subject_secondary: 'alice@example.com',
    role: 'member',
    ...overrides,
  } as WorkspaceBindingItem;
}

function member(overrides: Partial<WorkspaceMemberItem>): WorkspaceMemberItem {
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

function candidate(
  overrides: Partial<WorkspaceMemberCandidate>,
): WorkspaceMemberCandidate {
  return {
    id: 'user-1',
    email: 'alice@example.com',
    full_name: 'Alice',
    display_name: 'Alice',
    status: 'active',
    ...overrides,
  } as WorkspaceMemberCandidate;
}

function membersResponse(
  overrides: Partial<WorkspaceMembersResponse> = {},
): WorkspaceMembersResponse {
  return {
    items: [],
    total: 0,
    page: 1,
    page_size: 25,
    role_counts: { admin: 0, member: 0 },
    user_count: 0,
    pending_count: 0,
    ...overrides,
  } as WorkspaceMembersResponse;
}

function bulkResponse(
  overrides: Partial<WorkspaceMemberBulkResponse> = {},
): WorkspaceMemberBulkResponse {
  return {
    succeeded: 0,
    failed: [],
    ...overrides,
  };
}

function selection(ids: readonly string[]): SubjectSelectionState {
  return {
    users: new Map(
      ids.map((id) => [
        id,
        {
          id,
          kind: 'user' as const,
          label: `User ${id}`,
          secondary: `${id}@example.com`,
        },
      ]),
    ),
  };
}

function createPorts(
  overrides: Partial<WorkspaceMembersWorkflowPorts> = {},
): WorkspaceMembersWorkflowPorts {
  return {
    listBindings: async () => [],
    listMembers: async () => membersResponse(),
    listCandidates: async () => [],
    bulkMembers: async () => bulkResponse(),
    updateMemberRole: async (_workspaceId, _subjectType, subjectId, role) =>
      binding({ subject_id: subjectId, role }),
    removeMember: async () => undefined,
    ...overrides,
  };
}

describe('workspace members workflow', () => {
  it('normalizes list and candidate queries before calling ports', async () => {
    const listCalls: Array<Record<string, unknown>> = [];
    const candidateCalls: Array<Record<string, unknown>> = [];
    const ports = createPorts({
      listMembers: async (workspaceId, params) => {
        listCalls.push({ workspaceId, params });
        return membersResponse({ total: 2, page: 2, page_size: 25 });
      },
      listCandidates: async (workspaceId, query) => {
        candidateCalls.push({ workspaceId, query });
        return [candidate({ id: 'user-2' })];
      },
    });

    expect(
      workspaceMembersListParams({
        query: '  alice  ',
        roleFilter: 'admin',
        page: 2,
        pageSize: 25,
        pendingOnly: false,
      }),
    ).toEqual({
      q: 'alice',
      role: ['admin'],
      page: 2,
      pageSize: 25,
      pendingOnly: false,
    });
    expect(workspaceMemberCandidateQuery('   ')).toBeUndefined();

    const page = await loadWorkspaceMembersPageWorkflow({
      workspaceId: 'workspace-1',
      listState: {
        query: ' alice ',
        roleFilter: null,
        page: 2,
        pageSize: 25,
        pendingOnly: true,
      },
      ports,
    });
    const candidates = await loadWorkspaceMemberCandidatesWorkflow({
      workspaceId: 'workspace-1',
      query: '  bob  ',
      ports,
    });

    expect(page.total).toBe(2);
    expect(candidates.map((item) => item.id)).toEqual(['user-2']);
    expect(listCalls).toEqual([
      {
        workspaceId: 'workspace-1',
        params: {
          q: 'alice',
          role: undefined,
          page: 2,
          pageSize: 25,
          pendingOnly: true,
        },
      },
    ]);
    expect(candidateCalls).toEqual([
      { workspaceId: 'workspace-1', query: 'bob' },
    ]);
  });

  it('reloads bindings and refreshes member count through workflow ports', async () => {
    const ports = createPorts({
      listBindings: async (workspaceId) => [
        binding({ subject_id: `${workspaceId}-user` }),
      ],
      listMembers: async (workspaceId, params) =>
        membersResponse({
          total: workspaceId === 'workspace-1' && params?.pageSize === 1 ? 7 : 0,
        }),
    });

    await expect(
      reloadWorkspaceBindingsWorkflow({
        workspaceId: 'workspace-1',
        ports,
      }),
    ).resolves.toEqual([binding({ subject_id: 'workspace-1-user' })]);
    await expect(
      refreshWorkspaceMemberCountWorkflow({
        workspaceId: 'workspace-1',
        ports,
      }),
    ).resolves.toBe(7);
  });

  it('adds selected members, reloads bindings, and normalizes bulk outcomes', async () => {
    const bulkCalls: Array<Record<string, unknown>> = [];
    const ports = createPorts({
      bulkMembers: async (workspaceId, payload) => {
        bulkCalls.push({ workspaceId, payload });
        return bulkResponse({
          succeeded: 1,
          failed: [
            {
              subject_type: 'user',
              subject_id: 'user-2',
              detail: 'Already a member',
            },
          ],
        });
      },
      listBindings: async () => [
        binding({ subject_id: 'user-1', role: 'admin' }),
        binding({ subject_id: 'user-3' }),
      ],
    });

    const result = await addWorkspaceMembersWorkflow({
      workspaceId: 'workspace-1',
      selection: selection(['user-1', 'user-2']),
      role: 'admin',
      ports,
    });

    expect(bulkCalls).toEqual([
      {
        workspaceId: 'workspace-1',
        payload: {
          action: 'add',
          subjects: [
            { subject_type: 'user', subject_id: 'user-1', role: 'admin' },
            { subject_type: 'user', subject_id: 'user-2', role: 'admin' },
          ],
        },
      },
    ]);
    expect(result.bindings.map((item) => item.subject_id)).toEqual([
      'user-1',
      'user-3',
    ]);
    expect(result.memberCountDelta).toBe(1);
    expect(result.outcome).toEqual({
      succeeded: 1,
      failedCount: 1,
      partial: true,
    });
    expect(workspaceMembersBulkOutcome(result.result)).toEqual(result.outcome);
  });

  it('patches role and removal results into binding lists', async () => {
    const currentBindings = [
      binding({ subject_id: 'user-1', role: 'member' }),
      binding({ subject_id: 'user-2', role: 'member' }),
    ];
    const updateCalls: Array<Record<string, string>> = [];
    const removeCalls: Array<Record<string, string>> = [];
    const ports = createPorts({
      updateMemberRole: async (workspaceId, subjectType, subjectId, role) => {
        updateCalls.push({ workspaceId, subjectType, subjectId, role });
        return binding({ subject_id: subjectId, role });
      },
      removeMember: async (workspaceId, subjectType, subjectId) => {
        removeCalls.push({ workspaceId, subjectType, subjectId });
      },
    });

    const roleResult = await changeWorkspaceMemberRoleWorkflow({
      workspaceId: 'workspace-1',
      member: member({ subject_id: 'user-2' }),
      role: 'admin',
      currentBindings,
      ports,
    });
    const removeResult = await removeWorkspaceMemberWorkflow({
      workspaceId: 'workspace-1',
      member: currentBindings[0],
      currentBindings,
      ports,
    });

    expect(updateCalls).toEqual([
      {
        workspaceId: 'workspace-1',
        subjectType: 'user',
        subjectId: 'user-2',
        role: 'admin',
      },
    ]);
    expect(roleResult.bindings?.map((item) => [item.subject_id, item.role]))
      .toEqual([
        ['user-1', 'member'],
        ['user-2', 'admin'],
      ]);
    expect(
      workspaceBindingsWithUpdatedMember(
        currentBindings,
        member({ subject_id: 'user-1' }),
        binding({ subject_id: 'user-1', role: 'admin' }),
      ).map((item) => item.role),
    ).toEqual(['admin', 'member']);
    expect(removeCalls).toEqual([
      {
        workspaceId: 'workspace-1',
        subjectType: 'user',
        subjectId: 'user-1',
      },
    ]);
    expect(removeResult.bindings?.map((item) => item.subject_id)).toEqual([
      'user-2',
    ]);
    expect(
      workspaceBindingsWithoutMember(
        currentBindings,
        member({ subject_id: 'user-2' }),
      ).map((item) => item.subject_id),
    ).toEqual(['user-1']);
    expect(removeResult.memberCountDelta).toBe(-1);
    expect(nextWorkspaceMemberCount(0, removeResult.memberCountDelta)).toBe(0);
  });

  it('builds bulk remove and role-update payloads from selected keys', async () => {
    const bulkCalls: Array<Record<string, unknown>> = [];
    const ports = createPorts({
      bulkMembers: async (workspaceId, payload) => {
        bulkCalls.push({ workspaceId, payload });
        return bulkResponse({ succeeded: payload.subjects.length });
      },
    });

    const removeResult = await bulkRemoveWorkspaceMembersWorkflow({
      workspaceId: 'workspace-1',
      selectedKeys: new Set(['user:user-1', 'user:user-2']),
      ports,
    });
    const roleResult = await bulkUpdateWorkspaceMemberRolesWorkflow({
      workspaceId: 'workspace-1',
      selectedKeys: ['user:user-3'],
      role: 'admin',
      ports,
    });

    expect(bulkCalls).toEqual([
      {
        workspaceId: 'workspace-1',
        payload: {
          action: 'remove',
          subjects: [
            { subject_type: 'user', subject_id: 'user-1' },
            { subject_type: 'user', subject_id: 'user-2' },
          ],
        },
      },
      {
        workspaceId: 'workspace-1',
        payload: {
          action: 'update_role',
          subjects: [
            { subject_type: 'user', subject_id: 'user-3', role: 'admin' },
          ],
        },
      },
    ]);
    expect(removeResult.memberCountDelta).toBe(-2);
    expect(removeResult.outcome.partial).toBe(false);
    expect(roleResult.outcome).toEqual({
      succeeded: 1,
      failedCount: 0,
      partial: false,
    });
  });
});
