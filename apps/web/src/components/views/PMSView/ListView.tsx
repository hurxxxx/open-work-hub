import { Activity, Plus, Layout, ChevronDown, Circle, User2, CheckSquare, Clock } from 'lucide-react';
import { Badge, Button } from '@aidoo/ui';
import type { PmsIssue, PmsProjectStatus } from '@/src/domains/pms/pms-api';
import { getStatusSlugs, getStatusTone, PRIORITY_COLOR, initials, formatDate } from './pms-constants';

export const ListView = ({
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
    <div className="space-y-8">
      <div className="app-text-body-sm flex items-center gap-4 rounded-md border border-clickup-border bg-clickup-sidebar/30 p-2 text-clickup-text/60">
        <Button variant="subtle" size="dense" className="app-text-body-sm gap-1 font-medium">
          <Activity size={14} />
          Group: Status
        </Button>
        <Button variant="ghost" size="dense" className="app-text-body-sm gap-1 font-medium">
          <Plus size={14} />
          Subtasks
        </Button>
        <Button variant="ghost" size="dense" className="app-text-body-sm gap-1 font-medium">
          <Layout size={14} />
          Columns
        </Button>
      </div>

      {getStatusSlugs(projectStatuses).map((status) => {
        const statusIssues = issues.filter((i) => i.status === status);
        if (statusIssues.length === 0) return null;

        return (
          <div key={status} className="space-y-2">
            <div className="flex items-center gap-2 px-2 py-1">
              <ChevronDown size={14} className="text-clickup-text/50" />
              <Badge tone={getStatusTone(status, projectStatuses)}>{statusIssues[0]?.status_label ?? status}</Badge>
              <span className="app-text-label text-clickup-text/40">
                {statusIssues.length}
              </span>
            </div>

            <div className="border border-clickup-border rounded-lg overflow-hidden bg-clickup-sidebar/20">
              <table className="app-text-body-sm w-full text-left">
                <thead>
                  <tr className="app-text-overline border-b border-clickup-border bg-clickup-sidebar/50 text-clickup-text/50">
                    <th className="w-10 py-2 px-4"></th>
                    <th className="w-1/3 px-4 py-2">Name</th>
                    <th className="px-4 py-2">Assignee</th>
                    <th className="px-4 py-2">Due Date</th>
                    <th className="px-4 py-2">Priority</th>
                    <th className="px-4 py-2">Status</th>
                    <th className="px-4 py-2">Comments</th>
                    <th className="px-4 py-2 text-right">
                      <Plus size={14} className="inline cursor-pointer" />
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-clickup-border">
                  {statusIssues.map((issue) => (
                    <tr
                      key={issue.id}
                      onClick={() => onSelectIssue(issue)}
                      className="hover:bg-clickup-hover transition-colors group cursor-pointer"
                    >
                      <td className="py-2 px-4">
                        {onToggleSelect ? (
                          <input
                            type="checkbox"
                            checked={selectedIds?.has(issue.id) ?? false}
                            onChange={(e) => { e.stopPropagation(); onToggleSelect(issue.id); }}
                            onClick={(e) => e.stopPropagation()}
                            className="h-3.5 w-3.5 rounded accent-clickup-purple cursor-pointer"
                          />
                        ) : (
                          <Circle size={14} className="text-clickup-text/40" />
                        )}
                      </td>
                      <td className="py-2 px-4">
                        <div className="flex items-center gap-2">
                          <span className="app-text-caption text-clickup-text/40">{issue.reference}</span>
                          <span className="text-clickup-text font-medium">{issue.title}</span>
                        </div>
                      </td>
                      <td className="py-2 px-4">
                        {issue.assignee_name ? (
                          <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-[8px] font-bold text-white border border-clickup-border">
                            {initials(issue.assignee_name)}
                          </div>
                        ) : (
                          <User2 size={14} className="text-clickup-text/30" />
                        )}
                      </td>
                      <td className="py-2 px-4">
                        <span className="text-clickup-text/50">{formatDate(issue.due_date) || 'Not set'}</span>
                      </td>
                      <td className="py-2 px-4">
                        <span className={`app-text-caption font-semibold ${PRIORITY_COLOR[issue.priority] ?? ''}`}>
                          {issue.priority_label}
                        </span>
                      </td>
                      <td className="py-2 px-4">
                        <Badge tone={getStatusTone(issue.status, projectStatuses)}>{issue.status_label}</Badge>
                      </td>
                      <td className="py-2 px-4">
                        <span className="text-clickup-text/40">{issue.comments_count}</span>
                        {issue.checklist_total > 0 && (
                          <span className="app-text-caption ml-2 inline-flex items-center gap-0.5 text-clickup-text/40">
                            <CheckSquare size={11} />
                            <span>{issue.checklist_done}/{issue.checklist_total}</span>
                          </span>
                        )}
                        {issue.estimate_hours != null && issue.estimate_hours > 0 && (
                          <span className="app-text-caption ml-2 inline-flex items-center gap-0.5 text-clickup-text/40">
                            <Clock size={11} />
                            <span>{Math.round(issue.time_spent_minutes / 60 * 10) / 10}/{issue.estimate_hours}h</span>
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-4 text-right">
                        <Plus
                          size={14}
                          className="inline opacity-0 group-hover:opacity-100 text-clickup-text/50 transition-opacity"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
};
