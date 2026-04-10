import { MessageSquare, Flag, MoreHorizontal, CheckSquare, Clock } from 'lucide-react';
import { Badge, Button } from '@aidoo/ui';
import type { PmsIssue, PmsProjectStatus } from '@/src/domains/pms/pms-api';
import { getStatusTone, PRIORITY_COLOR, initials, formatDate } from './pms-constants';

export const TableView = ({
  issues,
  onSelectIssue,
  selectedIds,
  onToggleSelect,
  projectStatuses,
}: {
  issues: PmsIssue[];
  onSelectIssue: (issue: PmsIssue) => void;
  selectedIds?: Set<string>;
  onToggleSelect?: (issueId: string) => void;
  projectStatuses?: PmsProjectStatus[];
}) => {
  return (
    <div className="overflow-hidden rounded-lg border border-app-border bg-app-surface">
      <div className="overflow-x-auto custom-scrollbar">
        <table className="app-text-body-sm w-full text-left">
          <thead>
            <tr className="app-text-overline border-b border-app-border bg-app-surface-sidebar/50 text-app-ink/50">
              {onToggleSelect && <th className="py-3 px-4 w-10"></th>}
              <th className="py-3 px-4 w-12">#</th>
              <th className="py-3 px-4 min-w-[250px]">Task Name</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Assignee</th>
              <th className="py-3 px-4">Due Date</th>
              <th className="py-3 px-4">Priority</th>
              <th className="py-3 px-4">Labels</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-app-border">
            {issues.map((issue) => (
              <tr
                key={issue.id}
                onClick={() => onSelectIssue(issue)}
                className="hover:bg-app-surface-hover transition-colors group cursor-pointer"
              >
                {onToggleSelect && (
                  <td className="py-3 px-4">
                    <input
                      type="checkbox"
                      checked={selectedIds?.has(issue.id) ?? false}
                      onChange={(e) => { e.stopPropagation(); onToggleSelect(issue.id); }}
                      onClick={(e) => e.stopPropagation()}
                      className="h-3.5 w-3.5 rounded accent-app-accent cursor-pointer"
                    />
                  </td>
                )}
                <td className="py-3 px-4 text-app-ink/40">{issue.reference}</td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <span className="text-app-ink font-medium">{issue.title}</span>
                    {issue.comments_count > 0 && (
                      <div className="flex items-center gap-1 text-app-ink/40">
                        <MessageSquare size={12} />
                        <span className="app-text-micro">{issue.comments_count}</span>
                      </div>
                    )}
                    {issue.checklist_total > 0 && (
                      <div className="flex items-center gap-0.5 text-app-ink/40">
                        <CheckSquare size={11} />
                        <span className="app-text-micro">{issue.checklist_done}/{issue.checklist_total}</span>
                      </div>
                    )}
                    {issue.estimate_hours != null && issue.estimate_hours > 0 && (
                      <div className="flex items-center gap-0.5 text-app-ink/40">
                        <Clock size={11} />
                        <span className="app-text-micro">{Math.round(issue.time_spent_minutes / 60 * 10) / 10}/{issue.estimate_hours}h</span>
                      </div>
                    )}
                  </div>
                </td>
                <td className="py-3 px-4">
                  <Badge tone={getStatusTone(issue.status, projectStatuses)}>{issue.status_label}</Badge>
                </td>
                <td className="py-3 px-4">
                  {issue.assignee_name ? (
                    <div className="flex items-center gap-2">
                      <div className="app-text-micro flex h-6 w-6 items-center justify-center rounded-full border border-app-border bg-blue-500 font-bold text-white">
                        {initials(issue.assignee_name)}
                      </div>
                      <span className="text-app-ink/60">{issue.assignee_name}</span>
                    </div>
                  ) : (
                    <span className="text-app-ink/30">-</span>
                  )}
                </td>
                <td className="py-3 px-4 text-app-ink/60">{formatDate(issue.due_date) || '-'}</td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <Flag size={14} className={PRIORITY_COLOR[issue.priority] ?? 'text-gray-500'} />
                    <span className="text-app-ink/50">{issue.priority_label}</span>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <div className="flex flex-wrap gap-1">
                    {issue.labels.map((label) => (
                      <Badge key={label.id} tone="neutral">
                        {label.name}
                      </Badge>
                    ))}
                  </div>
                </td>
                <td className="py-3 px-4 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="opacity-0 group-hover:opacity-100"
                  >
                    <MoreHorizontal size={14} />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
