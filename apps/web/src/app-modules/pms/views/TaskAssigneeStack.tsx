import { User2 } from 'lucide-react';

import { UserOptionAvatar } from '@/src/platform/users/UserSearchMultiSelect';
import {
  userOptionDisplayName,
  userOptionNameWithDepartment,
  type UserOptionLike,
} from '@/src/platform/users/user-option-picker-model';
import type { PmsTask, PmsTaskListMember } from '../api/pms-api';

type TaskAssigneeStackProps = {
  members?: readonly PmsTaskListMember[];
  showName?: boolean;
  sizeClassName?: string;
  task: Pick<
    PmsTask,
    'id' | 'assignee_id' | 'assignee_ids' | 'assignee_name' | 'assignee_names'
  >;
  unassignedLabel?: string;
  visibleCount?: number;
};

type TaskAssigneeOption = UserOptionLike & {
  id: string;
};

function taskAssigneeOptions(
  task: TaskAssigneeStackProps['task'],
  members: readonly PmsTaskListMember[],
): TaskAssigneeOption[] {
  const ids =
    task.assignee_ids && task.assignee_ids.length > 0
      ? task.assignee_ids
      : task.assignee_id
        ? [task.assignee_id]
        : [];
  const names =
    task.assignee_names && task.assignee_names.length > 0
      ? task.assignee_names
      : task.assignee_name
        ? [task.assignee_name]
        : [];
  const memberById = new Map(members.map((member) => [member.user_id, member]));

  return ids.map((id, index) => {
    const member = memberById.get(id);
    if (member) {
      return {
        ...member,
        id: member.user_id,
      };
    }
    const fallbackName = names[index] ?? task.assignee_name ?? id;
    return {
      id,
      email: '',
      full_name: fallbackName,
    };
  });
}

export function resolveTaskAssigneeTitle({
  members = [],
  task,
}: Pick<TaskAssigneeStackProps, 'members' | 'task'>): string {
  return taskAssigneeOptions(task, members)
    .map((option) => userOptionNameWithDepartment(option))
    .join(', ');
}

export function TaskAssigneeStack({
  members = [],
  showName = false,
  sizeClassName = 'size-6',
  task,
  unassignedLabel,
  visibleCount = 3,
}: TaskAssigneeStackProps) {
  const assignees = taskAssigneeOptions(task, members);
  if (assignees.length === 0) {
    return (
      <span
        className="inline-flex items-center gap-1 text-app-ink/35"
        title={unassignedLabel}
      >
        <User2 size={14} className="shrink-0" />
        {showName && unassignedLabel ? (
          <span className="max-w-[9rem] truncate">{unassignedLabel}</span>
        ) : null}
      </span>
    );
  }

  const visible = assignees.slice(0, visibleCount);
  const hiddenCount = Math.max(0, assignees.length - visible.length);
  const title = assignees
    .map((option) => userOptionNameWithDepartment(option))
    .join(', ');
  const primaryAssignee = assignees[0] as TaskAssigneeOption;

  return (
    <span className="inline-flex min-w-0 items-center gap-1.5" title={title}>
      <span className="flex shrink-0 items-center">
        {visible.map((assignee, index) => (
          <UserOptionAvatar
            key={assignee.id}
            className={index > 0 ? '-ml-1.5 ring-2 ring-app-bg' : 'ring-2 ring-app-bg'}
            sizeClassName={sizeClassName}
            user={assignee}
          />
        ))}
        {hiddenCount > 0 ? (
          <span
            className={`app-text-micro -ml-1.5 inline-flex ${sizeClassName} items-center justify-center rounded-full border border-app-border bg-app-surface-sidebar font-semibold text-app-ink/70 ring-2 ring-app-bg`}
          >
            +{hiddenCount}
          </span>
        ) : null}
      </span>
      {showName ? (
        <span className="min-w-0 truncate text-app-ink/60">
          {assignees.length === 1
            ? userOptionDisplayName(primaryAssignee)
            : `${userOptionDisplayName(primaryAssignee)} +${assignees.length - 1}`}
        </span>
      ) : null}
    </span>
  );
}
