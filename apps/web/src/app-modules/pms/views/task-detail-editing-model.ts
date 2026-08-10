import type { TFunction } from 'i18next';

import type {
  PmsTask,
  PmsTaskListMember,
  PmsTaskListStatus,
} from '../api/pms-api';
import { getStatusLabel } from './pms-constants';

export type TaskUserRole = 'assignees' | 'followers';

const DEFAULT_STATUS_LABEL_KEYS: Record<string, string> = {
  canceled: 'pms.filter.status.canceled',
  complete: 'pms.filter.status.complete',
  done: 'pms.filter.status.done',
  in_progress: 'pms.filter.status.inProgress',
  review: 'pms.filter.status.review',
  todo: 'pms.filter.status.todo',
};

export function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function resolveSelectedAssigneeIds(
  issue: Pick<PmsTask, 'assignee_id' | 'assignee_ids'>,
): string[] {
  const currentAssigneeIds = issue.assignee_ids ?? [];
  if (currentAssigneeIds.length > 0) {
    return currentAssigneeIds;
  }
  return issue.assignee_id ? [issue.assignee_id] : [];
}

export function resolveTaskDetailMemberNames(
  members: Pick<PmsTaskListMember, 'full_name' | 'user_id'>[],
  userIds: string[],
  fallbackNames: string[] = [],
): string[] {
  return userIds.map((userId, index) => {
    const memberName = members.find(
      (member) => member.user_id === userId,
    )?.full_name;
    return memberName ?? fallbackNames[index] ?? userId;
  });
}

export function resolveTaskDetailStatusLabel(
  slug: string,
  taskListStatuses: PmsTaskListStatus[] | undefined,
  t: TFunction,
): string {
  const configuredStatus = taskListStatuses?.find(
    (status) => status.slug === slug,
  );
  if (configuredStatus) return configuredStatus.name;
  const labelKey = DEFAULT_STATUS_LABEL_KEYS[slug];
  return labelKey ? t(labelKey) : getStatusLabel(slug, taskListStatuses);
}

export function applyTaskUserRoleState(
  task: PmsTask,
  role: TaskUserRole,
  userIds: string[],
  userNames: string[],
): PmsTask {
  if (role === 'assignees') {
    return {
      ...task,
      assignee_id: userIds[0] ?? null,
      assignee_ids: userIds,
      assignee_name: userNames[0] ?? null,
      assignee_names: userNames,
    };
  }
  return {
    ...task,
    follower_ids: userIds,
    follower_names: userNames,
  };
}

export function restoreTaskUserRoleState(
  task: PmsTask,
  role: TaskUserRole,
  previousTask: PmsTask,
): PmsTask {
  if (role === 'assignees') {
    return {
      ...task,
      assignee_id: previousTask.assignee_id,
      assignee_ids: previousTask.assignee_ids,
      assignee_name: previousTask.assignee_name,
      assignee_names: previousTask.assignee_names,
    };
  }
  return {
    ...task,
    follower_ids: previousTask.follower_ids,
    follower_names: previousTask.follower_names,
  };
}

export function toggleTaskUserRoleId(
  currentIds: string[],
  userId: string,
): string[] {
  return currentIds.includes(userId)
    ? currentIds.filter((id) => id !== userId)
    : [...currentIds, userId];
}
