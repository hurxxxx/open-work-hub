import { MessageSquare, Flag, MoreHorizontal } from 'lucide-react';
import { Badge, Button } from '@aidoo/ui';
import type { PmsIssue } from '@/src/domains/pms/pms-api';
import { STATUS_TONE, PRIORITY_COLOR, initials, formatDate } from './pms-constants';

export const TableView = ({
  issues,
  onSelectIssue,
}: {
  issues: PmsIssue[];
  onSelectIssue: (issue: PmsIssue) => void;
}) => {
  return (
    <div className="overflow-hidden rounded-lg border border-clickup-border bg-clickup-card">
      <div className="overflow-x-auto custom-scrollbar">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-clickup-sidebar/50 border-b border-clickup-border text-clickup-text/50 uppercase tracking-wider font-bold">
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
          <tbody className="divide-y divide-clickup-border">
            {issues.map((issue, i) => (
              <tr
                key={issue.id}
                onClick={() => onSelectIssue(issue)}
                className="hover:bg-clickup-hover transition-colors group cursor-pointer"
              >
                <td className="py-3 px-4 text-clickup-text/40">{issue.reference}</td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <span className="text-clickup-text font-medium">{issue.title}</span>
                    {issue.comments_count > 0 && (
                      <div className="flex items-center gap-1 text-clickup-text/40">
                        <MessageSquare size={12} />
                        <span className="text-[10px]">{issue.comments_count}</span>
                      </div>
                    )}
                  </div>
                </td>
                <td className="py-3 px-4">
                  <Badge tone={STATUS_TONE[issue.status] ?? 'neutral'}>{issue.status_label}</Badge>
                </td>
                <td className="py-3 px-4">
                  {issue.assignee_name ? (
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center text-[10px] font-bold text-white border border-clickup-border">
                        {initials(issue.assignee_name)}
                      </div>
                      <span className="text-clickup-text/60">{issue.assignee_name}</span>
                    </div>
                  ) : (
                    <span className="text-clickup-text/30">-</span>
                  )}
                </td>
                <td className="py-3 px-4 text-clickup-text/60">{formatDate(issue.due_date) || '-'}</td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <Flag size={14} className={PRIORITY_COLOR[issue.priority] ?? 'text-gray-500'} />
                    <span className="text-clickup-text/50">{issue.priority_label}</span>
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
