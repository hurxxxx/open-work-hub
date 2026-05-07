import { CheckSquare, Circle, Clock, MessageSquare, User2 } from 'lucide-react';
import { Badge } from '@ai-do/ui';

import type { PmsIssue, PmsTaskListStatus } from '../api/pms-api';
import {
  formatDate,
  getStatusTone,
  initials,
  PRIORITY_COLOR,
} from './pms-constants';

export function TaskIssueCard({
  issue,
  onSelectIssue,
  onToggleSelect,
  selectIssueLabel,
  selected,
  taskListStatuses,
  unassignedLabel,
}: {
  issue: PmsIssue;
  onSelectIssue: (issue: PmsIssue) => void;
  onToggleSelect?: (issueId: string) => void;
  selectIssueLabel: (reference: string) => string;
  selected?: boolean;
  taskListStatuses?: PmsTaskListStatus[];
  unassignedLabel: string;
}) {
  const hasProgress = issue.checklist_total > 0 || (issue.estimate_hours != null && issue.estimate_hours > 0);
  const dueDate = formatDate(issue.due_date);

  return (
    <article
      className="rounded-lg border border-app-border bg-app-surface p-3 shadow-sm transition-colors hover:bg-app-surface-hover"
      data-testid="mobile-task-card"
    >
      <div className="flex min-w-0 items-start gap-3">
        <div className="pt-1">
          {onToggleSelect ? (
            <input
              aria-label={selectIssueLabel(issue.reference)}
              checked={selected ?? false}
              className="h-4 w-4 cursor-pointer rounded accent-app-accent"
              onChange={(event) => {
                event.stopPropagation();
                onToggleSelect(issue.id);
              }}
              onClick={(event) => event.stopPropagation()}
              type="checkbox"
            />
          ) : (
            <Circle size={16} className="text-app-ink/35" />
          )}
        </div>

        <button
          className="min-w-0 flex-1 text-left"
          onClick={() => onSelectIssue(issue)}
          type="button"
        >
          <div className="flex min-w-0 items-center gap-2">
            <span className="app-text-caption shrink-0 text-app-ink/45">
              {issue.reference}
            </span>
            <Badge tone={getStatusTone(issue.status, taskListStatuses)}>
              {issue.status_label}
            </Badge>
          </div>

          <h3 className="app-text-body mt-2 line-clamp-2 min-w-0 break-words font-semibold text-app-ink">
            {issue.title}
          </h3>

          <div className="mt-3 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 text-app-ink/55">
            <span className="app-text-caption inline-flex min-w-0 items-center gap-1">
              {issue.assignee_name ? (
                <span className="app-text-micro flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-app-border bg-blue-500 font-bold text-white">
                  {initials(issue.assignee_name)}
                </span>
              ) : (
                <User2 size={14} className="shrink-0 text-app-ink/35" />
              )}
              <span className="max-w-[9rem] truncate">
                {issue.assignee_name ?? unassignedLabel}
              </span>
            </span>

            {dueDate ? (
              <span className="app-text-caption shrink-0">{dueDate}</span>
            ) : null}

            <span className={`app-text-caption shrink-0 font-semibold ${PRIORITY_COLOR[issue.priority] ?? 'text-app-ink/45'}`}>
              {issue.priority_label}
            </span>
          </div>

          {(issue.comments_count > 0 || hasProgress) ? (
            <div className="mt-3 flex flex-wrap items-center gap-3 text-app-ink/40">
              {issue.comments_count > 0 ? (
                <span className="app-text-caption inline-flex items-center gap-1">
                  <MessageSquare size={12} />
                  {issue.comments_count}
                </span>
              ) : null}
              {issue.checklist_total > 0 ? (
                <span className="app-text-caption inline-flex items-center gap-1">
                  <CheckSquare size={12} />
                  {issue.checklist_done}/{issue.checklist_total}
                </span>
              ) : null}
              {issue.estimate_hours != null && issue.estimate_hours > 0 ? (
                <span className="app-text-caption inline-flex items-center gap-1">
                  <Clock size={12} />
                  {Math.round((issue.time_spent_minutes / 60) * 10) / 10}/{issue.estimate_hours}h
                </span>
              ) : null}
            </div>
          ) : null}
        </button>
      </div>
    </article>
  );
}
