import { selectUserOptionsForPicker } from '@/src/platform/users/user-option-picker-model';

import type {
  WorkspaceBindingItem,
  WorkspaceMemberBulkSubject,
  WorkspaceMemberCandidate,
  WorkspaceMemberItem,
} from './admin-api';
import {
  WORKSPACE_ROLE_RANK,
  emptySubjectSelection,
  type SelectedSubject,
  type SubjectSelectionState,
} from './admin-shared';

export const DEFAULT_WORKSPACE_MEMBER_ROLE = 'member';

export type WorkspaceAddMemberState = {
  workspaceId: string | null;
  panelOpen: boolean;
  pickerOpen: boolean;
  selection: SubjectSelectionState;
  role: string;
};

export type WorkspaceAddMemberStatePatch = Partial<
  Omit<WorkspaceAddMemberState, 'workspaceId'>
>;

export type WorkspaceRoleOption = {
  value: string;
  label: string;
  description: string;
};

export function createWorkspaceAddMemberState(
  workspaceId: string | null,
): WorkspaceAddMemberState {
  return {
    workspaceId,
    panelOpen: false,
    pickerOpen: false,
    selection: emptySubjectSelection(),
    role: DEFAULT_WORKSPACE_MEMBER_ROLE,
  };
}

export function patchWorkspaceAddMemberState(
  current: WorkspaceAddMemberState,
  workspaceId: string | null,
  patch: WorkspaceAddMemberStatePatch,
): WorkspaceAddMemberState {
  return {
    ...(current.workspaceId === workspaceId
      ? current
      : createWorkspaceAddMemberState(workspaceId)),
    ...patch,
  };
}

export function sortWorkspaceBindings(
  bindings: readonly WorkspaceBindingItem[],
  locale: string,
): WorkspaceBindingItem[] {
  return Array.from(bindings).sort((left, right) => {
    const rankDiff =
      (WORKSPACE_ROLE_RANK[left.role] ?? 99) -
      (WORKSPACE_ROLE_RANK[right.role] ?? 99);
    if (rankDiff !== 0) return rankDiff;
    return left.subject_label.localeCompare(right.subject_label, locale);
  });
}

export function previewWorkspaceBindings(
  sortedBindings: readonly WorkspaceBindingItem[],
  limit = 5,
): WorkspaceBindingItem[] {
  const adminBindings: WorkspaceBindingItem[] = [];
  for (const binding of sortedBindings) {
    if (binding.role === 'admin') {
      adminBindings.push(binding);
    }
    if (adminBindings.length >= limit) break;
  }
  if (adminBindings.length > 0) {
    return adminBindings;
  }
  return sortedBindings.slice(0, limit);
}

export function workspaceMemberSubjectIds(
  bindings: readonly WorkspaceBindingItem[],
): Set<string> {
  return new Set(bindings.map((binding) => binding.subject_id));
}

export function selectedWorkspaceMemberSubjects(
  selection: SubjectSelectionState,
): SelectedSubject[] {
  return Array.from(selection.users.values());
}

export function workspaceAddMemberBulkSubjects(
  selection: SubjectSelectionState,
  role: string,
): WorkspaceMemberBulkSubject[] {
  return selectedWorkspaceMemberSubjects(selection).map((subject) => ({
    subject_type: 'user',
    subject_id: subject.id,
    role,
  }));
}

export function filterWorkspaceMemberCandidates(
  candidates: readonly WorkspaceMemberCandidate[],
  excludeIds: ReadonlySet<string>,
): WorkspaceMemberCandidate[] {
  return selectUserOptionsForPicker({
    users: candidates,
    query: '',
    excludeIds,
  });
}

export function workspaceRoleSelectOptions(
  roleOptions: readonly WorkspaceRoleOption[],
): Array<{ value: string; label: string }> {
  return roleOptions.map((option) => ({
    value: option.value,
    label: option.label,
  }));
}

export function workspaceMemberKey(item: {
  subject_type: string;
  subject_id: string;
}): string {
  return `${item.subject_type}:${item.subject_id}`;
}

export function workspaceMemberBulkSubject(
  key: string,
): WorkspaceMemberBulkSubject {
  const separatorIndex = key.indexOf(':');
  return {
    subject_type: 'user',
    subject_id:
      separatorIndex >= 0 ? key.slice(separatorIndex + 1) : key,
  };
}

export function workspaceMemberBulkSubjects(
  keys: Iterable<string>,
): WorkspaceMemberBulkSubject[] {
  return Array.from(keys, workspaceMemberBulkSubject);
}

export function workspaceMemberBulkRoleSubjects(
  keys: Iterable<string>,
  role: string,
): WorkspaceMemberBulkSubject[] {
  return workspaceMemberBulkSubjects(keys).map((subject) => ({
    ...subject,
    role,
  }));
}

export function selectableWorkspaceMemberKeys(
  items: readonly WorkspaceMemberItem[],
  currentUserId: string,
): Set<string> {
  const keys = new Set<string>();
  for (const item of items) {
    if (item.subject_type === 'user' && item.subject_id === currentUserId) {
      continue;
    }
    keys.add(workspaceMemberKey(item));
  }
  return keys;
}

export function activeWorkspaceMemberSelection(
  selectedKeys: ReadonlySet<string>,
  selectableKeys: ReadonlySet<string>,
): Set<string> {
  return new Set(
    Array.from(selectedKeys).filter((key) => selectableKeys.has(key)),
  );
}

export function workspaceMembersAllSelectableSelected(
  selectableKeys: readonly string[],
  activeSelectedKeys: ReadonlySet<string>,
): boolean {
  return (
    selectableKeys.length > 0 &&
    selectableKeys.every((key) => activeSelectedKeys.has(key))
  );
}

export function toggleWorkspaceMemberSelectionKey(
  selectedKeys: ReadonlySet<string>,
  key: string,
): Set<string> {
  const next = new Set(selectedKeys);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  return next;
}

export function toggleWorkspaceMemberPageSelection(
  selectedKeys: ReadonlySet<string>,
  selectableKeys: readonly string[],
  allSelectableSelected: boolean,
): Set<string> {
  const next = new Set(selectedKeys);
  if (allSelectableSelected) {
    for (const key of selectableKeys) {
      next.delete(key);
    }
    return next;
  }
  for (const key of selectableKeys) {
    next.add(key);
  }
  return next;
}
