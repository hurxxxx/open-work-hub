import { runRequestsWithConcurrency } from '../network/request-concurrency';
import type { WorkspaceItem } from './admin-api';
import { DEFAULT_WORKSPACE_MEMBER_ROLE } from './admin-user-access-model';

const WORKSPACE_MEMBERSHIP_SAVE_CONCURRENCY = 2;

export interface AdminUserAccessWorkflowPorts {
  addWorkspaceMember(
    workspaceId: string,
    userId: string,
    role: string,
  ): Promise<unknown>;
  removeWorkspaceMember(workspaceId: string, userId: string): Promise<unknown>;
}

export interface SaveAdminUserAccessWorkflowInput {
  userId: string;
  workspaces: readonly WorkspaceItem[];
  currentWorkspaceIds: readonly string[];
  nextWorkspaceIds: readonly string[];
  ports: AdminUserAccessWorkflowPorts;
}

export interface SaveAdminUserAccessWorkflowResult {
  effectiveWorkspaceIds: string[];
}

type WorkspaceMembershipMutation = {
  action: 'add' | 'remove';
  workspaceId: string;
};

export async function saveAdminUserAccessWorkflow({
  userId,
  workspaces,
  currentWorkspaceIds,
  nextWorkspaceIds,
  ports,
}: SaveAdminUserAccessWorkflowInput): Promise<SaveAdminUserAccessWorkflowResult> {
  const knownWorkspaceIds = new Set(
    workspaces.map((workspace) => workspace.id),
  );
  const unknownWorkspaceId = nextWorkspaceIds.find(
    (workspaceId) => !knownWorkspaceIds.has(workspaceId),
  );
  if (unknownWorkspaceId) {
    throw new Error(`Unknown workspace membership: ${unknownWorkspaceId}`);
  }

  const currentIds = new Set(
    currentWorkspaceIds.filter((workspaceId) =>
      knownWorkspaceIds.has(workspaceId),
    ),
  );
  const effectiveWorkspaceIds = Array.from(new Set(nextWorkspaceIds));
  const nextIds = new Set(effectiveWorkspaceIds);
  const mutations: WorkspaceMembershipMutation[] = [];

  for (const workspace of workspaces) {
    const currentlyAssigned = currentIds.has(workspace.id);
    const shouldBeAssigned = nextIds.has(workspace.id);
    if (currentlyAssigned === shouldBeAssigned) {
      continue;
    }
    mutations.push({
      action: shouldBeAssigned ? 'add' : 'remove',
      workspaceId: workspace.id,
    });
  }

  await runRequestsWithConcurrency(
    mutations,
    WORKSPACE_MEMBERSHIP_SAVE_CONCURRENCY,
    async (mutation) => {
      if (mutation.action === 'add') {
        await ports.addWorkspaceMember(
          mutation.workspaceId,
          userId,
          DEFAULT_WORKSPACE_MEMBER_ROLE,
        );
        return;
      }
      await ports.removeWorkspaceMember(mutation.workspaceId, userId);
    },
  );

  return { effectiveWorkspaceIds };
}
