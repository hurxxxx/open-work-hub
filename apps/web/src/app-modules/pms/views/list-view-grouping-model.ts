import type { PmsTask, PmsTaskListMember } from '../api/pms-api';
import {
  getTaskAssigneeGroupKey,
  getTaskAssigneeIds,
  getTaskRoot,
  type IssueHierarchyInfo,
} from './pms-task-hierarchy';

export type AssigneeTaskGroup = {
  assigneeIds: string[];
  key: string;
  issues: PmsTask[];
  label: string;
  rootCount: number;
};

function taskAssigneeName(
  task: PmsTask,
  assigneeId: string,
  members: readonly PmsTaskListMember[],
): string {
  const member = members.find((item) => item.user_id === assigneeId);
  if (member?.full_name) return member.full_name;
  const assigneeIndex = task.assignee_ids?.indexOf(assigneeId) ?? -1;
  if (assigneeIndex >= 0 && task.assignee_names?.[assigneeIndex]) {
    return task.assignee_names[assigneeIndex];
  }
  if (task.assignee_id === assigneeId && task.assignee_name) {
    return task.assignee_name;
  }
  return assigneeId;
}

export function buildAssigneeTaskGroups({
  hierarchy,
  members,
  orderedTasks,
  unassignedLabel,
  visibleTasks,
}: {
  hierarchy: Map<string, IssueHierarchyInfo>;
  members: readonly PmsTaskListMember[];
  orderedTasks: readonly PmsTask[];
  unassignedLabel: string;
  visibleTasks: readonly PmsTask[];
}): AssigneeTaskGroup[] {
  const groups = new Map<string, AssigneeTaskGroup>();
  for (const root of orderedTasks) {
    if (getTaskRoot(root, hierarchy).id !== root.id) continue;
    const assigneeIds = getTaskAssigneeIds(root);
    const key = getTaskAssigneeGroupKey(root);
    const current = groups.get(key);
    if (current) {
      current.rootCount += 1;
      continue;
    }
    groups.set(key, {
      assigneeIds,
      key,
      issues: [],
      label:
        assigneeIds.length > 0
          ? assigneeIds
              .map((assigneeId) => taskAssigneeName(root, assigneeId, members))
              .join(' · ')
          : unassignedLabel,
      rootCount: 1,
    });
  }
  for (const task of visibleTasks) {
    const root = getTaskRoot(task, hierarchy);
    const key = getTaskAssigneeGroupKey(root);
    groups.get(key)?.issues.push(task);
  }
  return Array.from(groups.values());
}
