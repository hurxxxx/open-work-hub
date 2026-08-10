import type { PmsSpaceMember, PmsUserSummary } from '../api/pms-api';

export const NO_MEMBER_SELECTION = '__none__';
export const DEFAULT_SPACE_MEMBER_ROLE = 'member';

export type TaskListMemberRoleValue = 'owner' | 'admin' | 'member' | 'viewer';

export type TaskListMemberRoleOption = {
  value: TaskListMemberRoleValue;
  labelKey: string;
};

export type TaskListMemberCandidateOption = {
  value: string;
  label: string;
};

export const TASK_LIST_MEMBER_ROLE_OPTIONS: TaskListMemberRoleOption[] = [
  { value: 'owner', labelKey: 'pms.settings.role.owner' },
  { value: 'admin', labelKey: 'pms.settings.role.admin' },
  { value: 'member', labelKey: 'pms.settings.role.member' },
  { value: 'viewer', labelKey: 'pms.settings.role.viewer' },
];

export function roleOptionsForTaskListSettings(
  canManageAdmins: boolean,
): TaskListMemberRoleOption[] {
  if (canManageAdmins) return TASK_LIST_MEMBER_ROLE_OPTIONS;
  return TASK_LIST_MEMBER_ROLE_OPTIONS.filter(
    (option) => option.value === 'member' || option.value === 'viewer',
  );
}

export function buildTaskListMemberCandidateOptions({
  availableUsers,
  candidatePlaceholder,
  members,
}: {
  availableUsers: readonly PmsUserSummary[];
  candidatePlaceholder: string;
  members: readonly PmsSpaceMember[];
}): TaskListMemberCandidateOption[] {
  const memberIds = new Set(members.map((member) => member.user_id));
  const options: TaskListMemberCandidateOption[] = [
    { value: NO_MEMBER_SELECTION, label: candidatePlaceholder },
  ];
  for (const candidate of availableUsers) {
    if (memberIds.has(candidate.id)) continue;
    options.push({
      value: candidate.id,
      label: `${candidate.full_name} (${candidate.email})`,
    });
  }
  return options;
}

export function canMutateTaskListSettingsMember({
  canManageAdmins,
  currentUserId,
  member,
}: {
  canManageAdmins: boolean;
  currentUserId: string | null | undefined;
  member: Pick<PmsSpaceMember, 'role' | 'user_id'>;
}): boolean {
  if (member.user_id === currentUserId) return false;
  return (
    canManageAdmins || (member.role !== 'owner' && member.role !== 'admin')
  );
}
