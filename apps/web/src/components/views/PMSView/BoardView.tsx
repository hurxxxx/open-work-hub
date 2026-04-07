import { motion } from 'motion/react';
import { Plus, MoreHorizontal, Flag, Calendar, User2 } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import type { PmsIssue } from '@/src/domains/pms/pms-api';
import { ISSUE_STATUSES, STATUS_DOT_COLOR, PRIORITY_COLOR, initials, formatDate } from './pms-constants';

export const BoardView = ({
  issues,
  onSelectIssue,
  onUpdateIssue,
}: {
  issues: PmsIssue[];
  onSelectIssue: (issue: PmsIssue) => void;
  onUpdateIssue?: (issueId: string, payload: Record<string, unknown>) => void;
}) => {
  const visibleStatuses = ISSUE_STATUSES.filter(s => s !== 'canceled');

  function handleDrop(e: React.DragEvent, targetStatus: string) {
    e.preventDefault();
    const issueId = e.dataTransfer.getData('text/plain');
    if (issueId && onUpdateIssue) {
      onUpdateIssue(issueId, { status: targetStatus });
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
  }

  return (
    <div className="flex gap-6 h-full overflow-x-auto pb-4 custom-scrollbar">
      {visibleStatuses.map(status => {
        const statusIssues = issues
          .filter(i => i.status === status)
          .sort((a, b) => a.board_position - b.board_position);
        const label = statusIssues[0]?.status_label ?? status.replace('_', ' ');

        return (
          <div
            key={status}
            className="flex-shrink-0 w-80 flex flex-col gap-4"
            onDrop={e => handleDrop(e, status)}
            onDragOver={handleDragOver}
          >
            <div className="flex items-center justify-between px-2">
              <div className="flex items-center gap-2">
                <div className={cn("w-2 h-2 rounded-full", STATUS_DOT_COLOR[status])} />
                <h3 className="text-xs font-bold text-clickup-text uppercase tracking-wider">{label}</h3>
                <span className="text-[10px] text-gray-600 font-bold">{statusIssues.length}</span>
              </div>
              <div className="flex items-center gap-1 text-gray-600">
                <Plus size={14} className="cursor-pointer hover:text-white" />
                <MoreHorizontal size={14} className="cursor-pointer hover:text-white" />
              </div>
            </div>

            <div className="flex-1 space-y-3">
              {statusIssues.map(issue => (
                <motion.div
                  key={issue.id}
                  layoutId={issue.id}
                  draggable
                  onDragStart={(e: any) => {
                    if (e.dataTransfer) e.dataTransfer.setData('text/plain', issue.id);
                  }}
                  onClick={() => onSelectIssue(issue)}
                  className="card p-4 hover:border-clickup-purple transition-all cursor-pointer group space-y-4"
                >
                  <div className="flex flex-wrap gap-1">
                    {issue.labels.map(label => (
                      <span
                        key={label.id}
                        className="px-1.5 py-0.5 bg-clickup-sidebar border border-clickup-border rounded text-[9px] text-gray-500"
                        style={label.color !== '#1f2d38' ? { borderColor: label.color, color: label.color } : undefined}
                      >
                        {label.name}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-clickup-text/40">{issue.reference}</span>
                    <h4 className="text-sm font-medium text-clickup-text leading-tight group-hover:text-clickup-purple transition-colors">
                      {issue.title}
                    </h4>
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-clickup-border/50">
                    <div className="flex items-center gap-3">
                      <Flag size={14} className={PRIORITY_COLOR[issue.priority] ?? 'text-gray-500'} />
                      {issue.due_date && (
                        <div className="flex items-center gap-1 text-[10px] text-gray-500">
                          <Calendar size={10} />
                          <span>{formatDate(issue.due_date)}</span>
                        </div>
                      )}
                    </div>
                    <div className="flex items-center -space-x-2">
                      {issue.assignee_name ? (
                        <div className="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center text-[9px] font-bold text-white border-2 border-clickup-bg">
                          {initials(issue.assignee_name)}
                        </div>
                      ) : (
                        <div className="w-6 h-6 rounded-full bg-clickup-sidebar border-2 border-clickup-bg flex items-center justify-center text-gray-600">
                          <User2 size={12} />
                        </div>
                      )}
                    </div>
                  </div>
                </motion.div>
              ))}
              <button className="w-full py-2 border border-dashed border-clickup-border rounded-lg text-[10px] text-gray-600 hover:text-gray-400 hover:border-gray-400 transition-all">
                + Add Task
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};
