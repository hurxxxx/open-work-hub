import { describe, expect, it } from 'vitest';

import type { WorkspaceItem } from './admin-api';
import {
  saveAdminUserAccessWorkflow,
  type AdminUserAccessWorkflowPorts,
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

function createPorts(
  overrides: Partial<AdminUserAccessWorkflowPorts> = {},
): AdminUserAccessWorkflowPorts {
  return {
    addWorkspaceMember: async () => undefined,
    removeWorkspaceMember: async () => undefined,
    ...overrides,
  };
}

describe('admin user access workflow', () => {
  it('adds and removes only the changed user memberships', async () => {
    const operations: string[] = [];
    const ports = createPorts({
      addWorkspaceMember: async (workspaceId, userId, role) => {
        operations.push(['add', workspaceId, userId, role].join(':'));
      },
      removeWorkspaceMember: async (workspaceId, userId) => {
        operations.push(['remove', workspaceId, userId].join(':'));
      },
    });

    const result = await saveAdminUserAccessWorkflow({
      userId: 'user-1',
      workspaces: [workspaceAlpha, workspaceBeta],
      currentWorkspaceIds: [workspaceAlpha.id],
      nextWorkspaceIds: [workspaceBeta.id, workspaceBeta.id],
      ports,
    });

    expect(operations).toEqual([
      'remove:workspace-alpha:user-1',
      'add:workspace-beta:user-1:member',
    ]);
    expect(result.effectiveWorkspaceIds).toEqual([workspaceBeta.id]);
  });

  it('does not touch memberships whose desired state is unchanged', async () => {
    const addWorkspaceMember = async () => {
      throw new Error('unexpected add');
    };
    const removeWorkspaceMember = async () => {
      throw new Error('unexpected remove');
    };

    await expect(
      saveAdminUserAccessWorkflow({
        userId: 'user-1',
        workspaces: [workspaceAlpha],
        currentWorkspaceIds: [workspaceAlpha.id],
        nextWorkspaceIds: [workspaceAlpha.id],
        ports: { addWorkspaceMember, removeWorkspaceMember },
      }),
    ).resolves.toEqual({
      effectiveWorkspaceIds: [workspaceAlpha.id],
    });
  });

  it('rejects unknown workspace IDs instead of silently dropping them', async () => {
    await expect(
      saveAdminUserAccessWorkflow({
        userId: 'user-1',
        workspaces: [workspaceAlpha],
        currentWorkspaceIds: [],
        nextWorkspaceIds: ['workspace-missing'],
        ports: createPorts(),
      }),
    ).rejects.toThrow('Unknown workspace membership: workspace-missing');
  });
});
