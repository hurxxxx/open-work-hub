import { Activity, Plus, Layout, ChevronDown, Circle, User2 } from 'lucide-react';
import { Badge, Button } from '@aidoo/ui';
import type { PmsIssue } from '@/src/domains/pms/pms-api';
import { ISSUE_STATUSES, STATUS_TONE, PRIORITY_COLOR, initials, formatDate } from './pms-constants';

export const ListView = ({
  issues,
  onSelectIssue,
}: {
  issues: PmsIssue[];
  onSelectIssue: (issue: PmsIssue) => void;
}) => {
  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4 text-xs font-medium text-clickup-text/50 bg-clickup-sidebar/30 p-2 rounded-md border border-clickup-border">
        <Button variant="subtle" size="dense" className="gap-1">
          <Activity size={14} />
          Group: Status
        </Button>
        <Button variant="ghost" size="dense" className="gap-1">
          <Plus size={14} />
          Subtasks
        </Button>
        <Button variant="ghost" size="dense" className="gap-1">
          <Layout size={14} />
          Columns
        </Button>
      </div>

      {ISSUE_STATUSES.map((status) => {
        const statusIssues = issues.filter((i) => i.status === status);
        if (statusIssues.length === 0) return null;

        return (
          <div key={status} className="space-y-2">
            <div className="flex items-center gap-2 px-2 py-1">
              <ChevronDown size={14} className="text-clickup-text/50" />
              <Badge tone={STATUS_TONE[status] ?? 'neutral'}>{statusIssues[0]?.status_label ?? status}</Badge>
              <span className="text-[10px] text-clickup-text/40 font-bold">
                {statusIssues.length}
              </span>
            </div>

            <div className="border border-clickup-border rounded-lg overflow-hidden bg-clickup-sidebar/20">
              <table className="w-full text-left text-[11px]">
                <thead>
                  <tr className="bg-clickup-sidebar/50 border-b border-clickup-border text-clickup-text/50">
                    <th className="w-10 py-2 px-4"></th>
                    <th className="py-2 px-4 font-medium w-1/3">NAME</th>
                    <th className="py-2 px-4 font-medium">ASSIGNEE</th>
                    <th className="py-2 px-4 font-medium">DUE DATE</th>
                    <th className="py-2 px-4 font-medium">PRIORITY</th>
                    <th className="py-2 px-4 font-medium">STATUS</th>
                    <th className="py-2 px-4 font-medium">COMMENTS</th>
                    <th className="py-2 px-4 font-medium text-right">
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
                        <Circle size={14} className="text-clickup-text/40" />
                      </td>
                      <td className="py-2 px-4">
                        <div className="flex items-center gap-2">
                          <span className="text-clickup-text/40 text-[10px]">{issue.reference}</span>
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
                        <span className={`text-[10px] font-bold ${PRIORITY_COLOR[issue.priority] ?? ''}`}>
                          {issue.priority_label}
                        </span>
                      </td>
                      <td className="py-2 px-4">
                        <Badge tone={STATUS_TONE[issue.status] ?? 'neutral'}>{issue.status_label}</Badge>
                      </td>
                      <td className="py-2 px-4">
                        <span className="text-clickup-text/40">{issue.comments_count}</span>
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
