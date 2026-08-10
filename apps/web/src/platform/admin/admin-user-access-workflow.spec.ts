import { describe, expect, it } from 'vitest';

import type { WorkspaceBindingItem, WorkspaceItem } from './admin-api';
import type { AdminUserAccessWorkflowPorts } from './admin-user-access-workflow';
import {
  loadAdminUserAccessWorkflow,
  saveAdminUserAccessWorkflow,
} from './admin-user-access-workflow';

const workspaceAlpha = {
  id: 'workspace-alpha',
  key: 'alpha',
  name: 'Alpha',
  description: '',
  active: true,
  member_count: 0,
} as WorkspaceItem;

const workspaceBeta = {
  id: 'workspace-beta',
  key: 'beta',
  name: 'Beta',
  description: '',
  active: true,
  member_count: 0,
} as WorkspaceItem;

function binding(
  overrides: Partial<WorkspaceBindingItem>,
): WorkspaceBindingItem {
  return {
    subject_type: 'user',
    subject_id: 'user-1',
    role: 'member',
    ...overrides,
  } as WorkspaceBindingItem;
}

function createPorts(
  overrides: Partial<AdminUserAccessWorkflowPorts> = {},
): AdminUserAccessWorkflowPorts {
  return {
    listWorkspaceBindings: async () => [],
    replaceWorkspaceBindings: async () => [],
    ...overrides,
  };
}

describe('admin user access workflow', () => {
  it('loads direct workspace IDs through ports', async () => {
    const listedWorkspaceIds: string[] = [];
    const ports = createPorts({
      listWorkspaceBindings: async (workspaceId) => {
        listedWorkspaceIds.push(workspaceId);
        if (workspaceId === workspaceAlpha.id) {
          return [
            binding({ subject_type: 'team', subject_id: 'team-1' }),
            binding({ subject_id: 'user-1', role: 'owner' }),
          ];
        }
        return [binding({ subject_id: 'other-user', role: 'admin' })];
      },
    });

    const result = await loadAdminUserAccessWorkflow({
      userId: 'user-1',
      workspaces: [workspaceAlpha, workspaceBeta],
      ports,
    });

    expect(listedWorkspaceIds).toEqual([workspaceAlpha.id, workspaceBeta.id]);
    expect(result.directWorkspaceIds).toEqual([workspaceAlpha.id]);
  });

  it('saves workspace bindings with preserved roles', async () => {
    const replacedBindings: Array<{
      workspaceId: string;
      users: Array<{ subject_id: string; role: string }>;
    }> = [];
    const ports = createPorts({
      listWorkspaceBindings: async (workspaceId) => {
        if (workspaceId === workspaceAlpha.id) {
          return [
            binding({ subject_id: 'other-user', role: 'admin' }),
            binding({ subject_type: 'team', subject_id: 'team-1' }),
            binding({ subject_id: 'user-1', role: 'owner' }),
          ];
        }
        return [binding({ subject_id: 'beta-user', role: 'member' })];
      },
      replaceWorkspaceBindings: async (workspaceId, payload) => {
        replacedBindings.push({ workspaceId, users: payload.users });
      },
    });

    const result = await saveAdminUserAccessWorkflow({
      userId: 'user-1',
      workspaces: [workspaceAlpha, workspaceBeta],
      directWorkspaceIds: [workspaceBeta.id],
      ports,
    });

    expect(result.effectiveDirectWorkspaceIds).toEqual([workspaceBeta.id]);
    expect(replacedBindings).toEqual([
      {
        workspaceId: workspaceAlpha.id,
        users: [{ subject_id: 'other-user', role: 'admin' }],
      },
      {
        workspaceId: workspaceBeta.id,
        users: [
          { subject_id: 'beta-user', role: 'member' },
          { subject_id: 'user-1', role: 'member' },
        ],
      },
    ]);
  });

  it('removes workspace bindings when a user is no longer selected', async () => {
    const replacedBindings: Array<{
      workspaceId: string;
      users: Array<{ subject_id: string; role: string }>;
    }> = [];
    const ports = createPorts({
      listWorkspaceBindings: async () => [
        binding({ subject_id: 'other-user', role: 'admin' }),
        binding({ subject_id: 'user-1', role: 'owner' }),
      ],
      replaceWorkspaceBindings: async (workspaceId, payload) => {
        replacedBindings.push({ workspaceId, users: payload.users });
      },
    });

    await saveAdminUserAccessWorkflow({
      userId: 'user-1',
      workspaces: [workspaceAlpha],
      directWorkspaceIds: [],
      ports,
    });

    expect(replacedBindings).toEqual([
      {
        workspaceId: workspaceAlpha.id,
        users: [{ subject_id: 'other-user', role: 'admin' }],
      },
    ]);
  });
});
