import {
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Circle,
  Eye,
  GitBranch,
  MessageSquare,
} from 'lucide-react';
import { Badge } from '@open-alm/ui';

import type {
  PmsTask,
  PmsTaskListMember,
  PmsTaskListStatus,
} from '../api/pms-api';
import {
  formatDate,
  getStatusLabel,
  getStatusTone,
  PRIORITY_COLOR,
} from './pms-constants';
import { TaskAssigneeStack } from './TaskAssigneeStack';

export function TaskCard({
  task,
  childCount = 0,
  collapseSubtasksLabel,
  collapsed = false,
  completedDateLabel,
  depth = 0,
  expandSubtasksLabel,
  onSelectIssue,
  onToggleCollapse,
  onToggleSelect,
  selectTaskLabel,
  selected,
  contextLabel,
  members,
  taskListStatuses,
  unassignedLabel,
  viewDetailsLabel,
}: {
  task: PmsTask;
  childCount?: number;
  collapseSubtasksLabel?: string;
  collapsed?: boolean;
  completedDateLabel: string;
  depth?: number;
  expandSubtasksLabel?: string;
  onSelectIssue: (task: PmsTask) => void;
  onToggleCollapse?: (taskId: string) => void;
  onToggleSelect?: (taskId: string) => void;
  selectTaskLabel: (reference: string) => string;
  selected?: boolean;
  contextLabel?: string | null;
  members?: readonly PmsTaskListMember[];
  taskListStatuses?: PmsTaskListStatus[];
  unassignedLabel: string;
  viewDetailsLabel: (reference: string) => string;
}) {
  const hasProgress = task.checklist_total > 0;
  const dueDate = formatDate(task.due_date);
  const completedDate = formatDate(task.completed_date);
  const indent = Math.min(depth, 3) * 12;
  const toggleSubtasksLabel = collapsed
    ? (expandSubtasksLabel ?? '')
    : (collapseSubtasksLabel ?? '');

  return (
    <article
      className="rounded-lg border border-app-border bg-app-surface p-3 shadow-sm transition-colors hover:bg-app-surface-hover"
      data-testid="mobile-task-card"
      style={indent > 0 ? { marginLeft: indent } : undefined}
    >
      <div className="flex min-w-0 items-start gap-3">
        <div className="pt-1">
          {onToggleSelect ? (
            <input
              aria-label={selectTaskLabel(task.reference)}
              checked={selected ?? false}
              className="size-4 cursor-pointer rounded accent-app-accent"
              onChange={(event) => {
                event.stopPropagation();
                onToggleSelect(task.id);
              }}
              onClick={(event) => event.stopPropagation()}
              type="checkbox"
            />
          ) : (
            <Circle size={16} className="text-app-ink/35" />
          )}
        </div>

        {childCount > 0 && onToggleCollapse ? (
          <button
            aria-label={toggleSubtasksLabel}
            className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded text-app-ink/45 hover:bg-app-surface-hover hover:text-app-ink"
            onClick={(event) => {
              event.stopPropagation();
              onToggleCollapse(task.id);
            }}
            title={toggleSubtasksLabel}
            type="button"
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
          </button>
        ) : null}

        <button
          className="min-w-0 flex-1 text-left"
          onClick={() => onSelectIssue(task)}
          type="button"
        >
          <div className="flex min-w-0 items-center gap-2">
            <Badge tone={getStatusTone(task.status, taskListStatuses)}>
              {getStatusLabel(task.status, taskListStatuses)}
            </Badge>
            {childCount > 0 ? (
              <span className="app-text-micro inline-flex items-center gap-1 text-app-ink/35">
                <GitBranch size={11} />
                {childCount}
              </span>
            ) : null}
          </div>

          <h3 className="app-text-body mt-2 line-clamp-2 min-w-0 break-words font-semibold text-app-ink">
            {task.title}
          </h3>
          {contextLabel ? (
            <p className="app-text-caption mt-1 truncate text-app-ink/45">
              {contextLabel}
            </p>
          ) : null}

          <div className="mt-3 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 text-app-ink/55">
            <span className="app-text-caption inline-flex min-w-0 items-center gap-1">
              <TaskAssigneeStack
                members={members}
                showName
                sizeClassName="size-5"
                task={task}
                unassignedLabel={unassignedLabel}
              />
            </span>

            {dueDate ? (
              <span className="app-text-caption shrink-0">{dueDate}</span>
            ) : null}

            {completedDate ? (
              <span className="app-text-caption inline-flex shrink-0 items-center gap-1">
                <span className="text-app-ink/40">{completedDateLabel}</span>
                <span>{completedDate}</span>
              </span>
            ) : null}

            <span
              className={`app-text-caption shrink-0 font-semibold ${PRIORITY_COLOR[task.priority] ?? 'text-app-ink/45'}`}
            >
              {task.priority_label}
            </span>
          </div>

          {task.comments_count > 0 || hasProgress ? (
            <div className="mt-3 flex flex-wrap items-center gap-3 text-app-ink/40">
              {task.comments_count > 0 ? (
                <span className="app-text-caption inline-flex items-center gap-1">
                  <MessageSquare size={12} />
                  {task.comments_count}
                </span>
              ) : null}
              {task.checklist_total > 0 ? (
                <span className="app-text-caption inline-flex items-center gap-1">
                  <CheckSquare size={12} />
                  {task.checklist_done}/{task.checklist_total}
                </span>
              ) : null}
            </div>
          ) : null}
        </button>

        <button
          aria-label={viewDetailsLabel(task.reference)}
          className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-md border border-transparent text-app-ink/45 transition-colors hover:border-app-border hover:bg-app-surface-sidebar hover:text-app-accent focus:border-app-border focus:bg-app-surface-sidebar focus:text-app-accent"
          onClick={(event) => {
            event.stopPropagation();
            onSelectIssue(task);
          }}
          title={viewDetailsLabel(task.reference)}
          type="button"
        >
          <Eye size={14} />
        </button>
      </div>
    </article>
  );
}
