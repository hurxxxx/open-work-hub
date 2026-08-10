import { runRequestsWithConcurrency } from '../network/request-concurrency';
import type { WorkspaceBindingItem, WorkspaceItem } from './admin-api';
import {
  directWorkspaceIdsForUser,
  workspaceBindingReplacementPayloadForUser,
  type WorkspaceBindingReplacementPayload,
} from './admin-user-access-model';

const WORKSPACE_BINDING_LOAD_CONCURRENCY = 4;
const WORKSPACE_BINDING_SAVE_CONCURRENCY = 2;

export interface AdminUserAccessWorkflowPorts {
  listWorkspaceBindings(
    workspaceId: string,
  ): Promise<readonly WorkspaceBindingItem[]>;
  replaceWorkspaceBindings(
    workspaceId: string,
    payload: WorkspaceBindingReplacementPayload,
  ): Promise<unknown>;
}

export interface LoadAdminUserAccessWorkflowInput {
  userId: string;
  workspaces: readonly WorkspaceItem[];
  ports: AdminUserAccessWorkflowPorts;
}

export interface AdminUserAccessWorkflowState {
  directWorkspaceIds: string[];
}

export interface SaveAdminUserAccessWorkflowInput {
  userId: string;
  workspaces: readonly WorkspaceItem[];
  directWorkspaceIds: readonly string[];
  ports: AdminUserAccessWorkflowPorts;
}

export interface SaveAdminUserAccessWorkflowResult {
  effectiveDirectWorkspaceIds: string[];
}

export async function loadAdminUserAccessWorkflow({
  userId,
  workspaces,
  ports,
}: LoadAdminUserAccessWorkflowInput): Promise<AdminUserAccessWorkflowState> {
  const bindingResults = await runRequestsWithConcurrency(
    workspaces,
    WORKSPACE_BINDING_LOAD_CONCURRENCY,
    async (workspace) => ({
      workspace,
      bindings: await ports.listWorkspaceBindings(workspace.id),
    }),
  );

  return {
    directWorkspaceIds: directWorkspaceIdsForUser(bindingResults, userId),
  };
}

export async function saveAdminUserAccessWorkflow({
  userId,
  workspaces,
  directWorkspaceIds,
  ports,
}: SaveAdminUserAccessWorkflowInput): Promise<SaveAdminUserAccessWorkflowResult> {
  const effectiveDirectWorkspaceIds = Array.from(new Set(directWorkspaceIds));

  await syncWorkspaceBindings({
    userId,
    workspaces,
    directWorkspaceIds: effectiveDirectWorkspaceIds,
    ports,
  });

  return { effectiveDirectWorkspaceIds };
}

async function syncWorkspaceBindings({
  userId,
  workspaces,
  directWorkspaceIds,
  ports,
}: {
  userId: string;
  workspaces: readonly WorkspaceItem[];
  directWorkspaceIds: readonly string[];
  ports: AdminUserAccessWorkflowPorts;
}): Promise<void> {
  const selectedWorkspaceIds = new Set(directWorkspaceIds);
  await runRequestsWithConcurrency(
    workspaces,
    WORKSPACE_BINDING_SAVE_CONCURRENCY,
    async (workspace) => {
      const bindings = await ports.listWorkspaceBindings(workspace.id);
      await ports.replaceWorkspaceBindings(
        workspace.id,
        workspaceBindingReplacementPayloadForUser(
          bindings,
          userId,
          selectedWorkspaceIds.has(workspace.id),
        ),
      );
    },
  );
}
