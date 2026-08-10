import type {
  WorkspaceBindingItem,
  WorkspaceMemberBulkResponse,
  WorkspaceMemberBulkSubject,
  WorkspaceMemberCandidate,
  WorkspaceMemberItem,
  WorkspaceMembersListParams,
  WorkspaceMembersResponse,
} from './admin-api';
import type { SubjectSelectionState } from './admin-shared';
import {
  workspaceAddMemberBulkSubjects,
  workspaceMemberBulkRoleSubjects,
  workspaceMemberBulkSubjects,
} from './workspace-members-model';

type WorkspaceMemberTarget = {
  subject_type:
    | WorkspaceBindingItem['subject_type']
    | WorkspaceMemberItem['subject_type'];
  subject_id: string;
};

export interface WorkspaceMembersWorkflowPorts {
  listBindings(workspaceId: string): Promise<WorkspaceBindingItem[]>;
  listMembers(
    workspaceId: string,
    params?: WorkspaceMembersListParams,
  ): Promise<WorkspaceMembersResponse>;
  listCandidates(
    workspaceId: string,
    query?: string,
  ): Promise<WorkspaceMemberCandidate[]>;
  bulkMembers(
    workspaceId: string,
    payload: {
      action: 'add' | 'remove' | 'update_role';
      subjects: WorkspaceMemberBulkSubject[];
    },
  ): Promise<WorkspaceMemberBulkResponse>;
  updateMemberRole(
    workspaceId: string,
    subjectType: WorkspaceMemberTarget['subject_type'],
    subjectId: string,
    role: string,
  ): Promise<WorkspaceBindingItem>;
  removeMember(
    workspaceId: string,
    subjectType: WorkspaceMemberTarget['subject_type'],
    subjectId: string,
  ): Promise<void>;
}

export interface WorkspaceMembersListState {
  query: string;
  roleFilter: string | null;
  page: number;
  pageSize: number;
  pendingOnly: boolean;
}

export interface WorkspaceMembersBulkOutcome {
  succeeded: number;
  failedCount: number;
  partial: boolean;
}

export function workspaceMembersListParams({
  query,
  roleFilter,
  page,
  pageSize,
  pendingOnly,
}: WorkspaceMembersListState): WorkspaceMembersListParams {
  return {
    q: query.trim() || undefined,
    role: roleFilter ? [roleFilter] : undefined,
    page,
    pageSize,
    pendingOnly,
  };
}

export function workspaceMemberCandidateQuery(
  query: string,
): string | undefined {
  return query.trim() || undefined;
}

export function workspaceMembersBulkOutcome(
  result: WorkspaceMemberBulkResponse,
): WorkspaceMembersBulkOutcome {
  const failedCount = result.failed.length;
  return {
    succeeded: result.succeeded,
    failedCount,
    partial: failedCount > 0,
  };
}

export function nextWorkspaceMemberCount(
  currentCount: number,
  delta: number,
): number {
  return Math.max(0, currentCount + delta);
}

export function workspaceBindingsWithUpdatedMember(
  bindings: readonly WorkspaceBindingItem[],
  target: WorkspaceMemberTarget,
  updated: WorkspaceBindingItem,
): WorkspaceBindingItem[] {
  return bindings.map((item) =>
    sameWorkspaceMember(item, target) ? updated : item,
  );
}

export function workspaceBindingsWithoutMember(
  bindings: readonly WorkspaceBindingItem[],
  target: WorkspaceMemberTarget,
): WorkspaceBindingItem[] {
  return bindings.filter((item) => !sameWorkspaceMember(item, target));
}

export async function reloadWorkspaceBindingsWorkflow({
  workspaceId,
  ports,
}: {
  workspaceId: string;
  ports: Pick<WorkspaceMembersWorkflowPorts, 'listBindings'>;
}): Promise<WorkspaceBindingItem[]> {
  return ports.listBindings(workspaceId);
}

export async function refreshWorkspaceMemberCountWorkflow({
  workspaceId,
  ports,
}: {
  workspaceId: string;
  ports: Pick<WorkspaceMembersWorkflowPorts, 'listMembers'>;
}): Promise<number> {
  const response = await ports.listMembers(workspaceId, {
    page: 1,
    pageSize: 1,
  });
  return response.total;
}

export async function loadWorkspaceMemberCandidatesWorkflow({
  workspaceId,
  query,
  ports,
}: {
  workspaceId: string;
  query: string;
  ports: Pick<WorkspaceMembersWorkflowPorts, 'listCandidates'>;
}): Promise<WorkspaceMemberCandidate[]> {
  return ports.listCandidates(workspaceId, workspaceMemberCandidateQuery(query));
}

export async function loadWorkspaceMembersPageWorkflow({
  workspaceId,
  listState,
  ports,
}: {
  workspaceId: string;
  listState: WorkspaceMembersListState;
  ports: Pick<WorkspaceMembersWorkflowPorts, 'listMembers'>;
}): Promise<WorkspaceMembersResponse> {
  return ports.listMembers(workspaceId, workspaceMembersListParams(listState));
}

export async function addWorkspaceMembersWorkflow({
  workspaceId,
  selection,
  role,
  ports,
}: {
  workspaceId: string;
  selection: SubjectSelectionState;
  role: string;
  ports: Pick<WorkspaceMembersWorkflowPorts, 'bulkMembers' | 'listBindings'>;
}): Promise<{
  result: WorkspaceMemberBulkResponse;
  outcome: WorkspaceMembersBulkOutcome;
  bindings: WorkspaceBindingItem[];
  memberCountDelta: number;
}> {
  const subjects = workspaceAddMemberBulkSubjects(selection, role);
  const result = await ports.bulkMembers(workspaceId, {
    action: 'add',
    subjects,
  });
  const bindings = await ports.listBindings(workspaceId);
  return {
    result,
    outcome: workspaceMembersBulkOutcome(result),
    bindings,
    memberCountDelta: result.succeeded,
  };
}

export async function changeWorkspaceMemberRoleWorkflow({
  workspaceId,
  member,
  role,
  currentBindings,
  ports,
}: {
  workspaceId: string;
  member: WorkspaceMemberTarget;
  role: string;
  currentBindings?: readonly WorkspaceBindingItem[];
  ports: Pick<WorkspaceMembersWorkflowPorts, 'updateMemberRole'>;
}): Promise<{
  updated: WorkspaceBindingItem;
  bindings: WorkspaceBindingItem[] | null;
}> {
  const updated = await ports.updateMemberRole(
    workspaceId,
    member.subject_type,
    member.subject_id,
    role,
  );

  return {
    updated,
    bindings: currentBindings
      ? workspaceBindingsWithUpdatedMember(currentBindings, member, updated)
      : null,
  };
}

export async function removeWorkspaceMemberWorkflow({
  workspaceId,
  member,
  currentBindings,
  ports,
}: {
  workspaceId: string;
  member: WorkspaceMemberTarget;
  currentBindings?: readonly WorkspaceBindingItem[];
  ports: Pick<WorkspaceMembersWorkflowPorts, 'removeMember'>;
}): Promise<{
  bindings: WorkspaceBindingItem[] | null;
  memberCountDelta: number;
}> {
  await ports.removeMember(workspaceId, member.subject_type, member.subject_id);

  return {
    bindings: currentBindings
      ? workspaceBindingsWithoutMember(currentBindings, member)
      : null,
    memberCountDelta: -1,
  };
}

export async function bulkRemoveWorkspaceMembersWorkflow({
  workspaceId,
  selectedKeys,
  ports,
}: {
  workspaceId: string;
  selectedKeys: Iterable<string>;
  ports: Pick<WorkspaceMembersWorkflowPorts, 'bulkMembers'>;
}): Promise<{
  result: WorkspaceMemberBulkResponse;
  outcome: WorkspaceMembersBulkOutcome;
  memberCountDelta: number;
}> {
  const result = await ports.bulkMembers(workspaceId, {
    action: 'remove',
    subjects: workspaceMemberBulkSubjects(selectedKeys),
  });

  return {
    result,
    outcome: workspaceMembersBulkOutcome(result),
    memberCountDelta: -result.succeeded,
  };
}

export async function bulkUpdateWorkspaceMemberRolesWorkflow({
  workspaceId,
  selectedKeys,
  role,
  ports,
}: {
  workspaceId: string;
  selectedKeys: Iterable<string>;
  role: string;
  ports: Pick<WorkspaceMembersWorkflowPorts, 'bulkMembers'>;
}): Promise<{
  result: WorkspaceMemberBulkResponse;
  outcome: WorkspaceMembersBulkOutcome;
}> {
  const result = await ports.bulkMembers(workspaceId, {
    action: 'update_role',
    subjects: workspaceMemberBulkRoleSubjects(selectedKeys, role),
  });

  return {
    result,
    outcome: workspaceMembersBulkOutcome(result),
  };
}

function sameWorkspaceMember(
  left: WorkspaceMemberTarget,
  right: WorkspaceMemberTarget,
): boolean {
  return (
    left.subject_type === right.subject_type &&
    left.subject_id === right.subject_id
  );
}
