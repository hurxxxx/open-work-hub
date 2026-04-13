import { motion } from 'motion/react';
import { Plus, MoreHorizontal, Flag, Calendar, User2, CheckSquare, Clock } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import type { PmsIssue, PmsProjectStatus } from '@/src/domains/pms/pms-api';
import { getStatusSlugs, STATUS_DOT_COLOR, PRIORITY_COLOR, initials, formatDate } from './pms-constants';

export const BoardView = ({
  issues,
  onSelectIssue,
  onUpdateIssue,
  selectedIds,
  onToggleSelect,
  projectStatuses,
}: {
  issues: PmsIssue[];
  onSelectIssue: (issue: PmsIssue) => void;
  onUpdateIssue?: (issueId: string, payload: Record<string, unknown>) => void;
  selectedIds?: Set<string>;
  onToggleSelect?: (issueId: string) => void;
  projectStatuses?: PmsProjectStatus[];
}) => {
  const allSlugs = getStatusSlugs(projectStatuses);
  const visibleStatuses = allSlugs.filter(s => {
    const ps = projectStatuses?.find(st => st.slug === s);
    return ps ? ps.category !== 'canceled' : s !== 'canceled';
  });

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
	                <div
	                  className={cn("w-2 h-2 rounded-full", STATUS_DOT_COLOR[status])}
	                  style={!STATUS_DOT_COLOR[status]
	                    ? (() => {
	                        const matchedStatus = projectStatuses?.find((projectStatus) => projectStatus.slug === status);
	                        return matchedStatus?.color ? { backgroundColor: matchedStatus.color } : undefined;
	                      })()
	                    : undefined}
	                />
                <h3 className="app-text-overline text-app-ink">{label}</h3>
                <span className="app-text-micro font-bold text-gray-600">{statusIssues.length}</span>
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
                  onDragStartCapture={(e: React.DragEvent<HTMLDivElement>) => {
                    if (e.dataTransfer) e.dataTransfer.setData('text/plain', issue.id);
                  }}
                  onClick={() => onSelectIssue(issue)}
                  className="card p-4 hover:border-app-accent transition-all cursor-pointer group space-y-4 relative"
                >
                  {onToggleSelect && (
                    <div className={`absolute top-2 left-2 z-10 ${selectedIds?.has(issue.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity`}>
                      <input
                        type="checkbox"
                        checked={selectedIds?.has(issue.id) ?? false}
                        onChange={(e) => { e.stopPropagation(); onToggleSelect(issue.id); }}
                        onClick={(e) => e.stopPropagation()}
                        className="h-3.5 w-3.5 rounded accent-app-accent cursor-pointer"
                      />
                    </div>
                  )}
                  <div className="flex flex-wrap gap-1">
                    {issue.labels.map(label => (
                      <span
                        key={label.id}
                        className="app-text-micro rounded border border-app-border bg-app-surface-sidebar px-1.5 py-0.5 text-gray-500"
                        style={label.color !== '#1f2d38' ? { borderColor: label.color, color: label.color } : undefined}
                      >
                        {label.name}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="app-text-micro text-app-ink/40">{issue.reference}</span>
                    <h4 className="app-text-body font-medium leading-tight text-app-ink transition-colors group-hover:text-app-accent">
                      {issue.title}
                    </h4>
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-app-border/50">
                    <div className="flex items-center gap-3">
                      <Flag size={14} className={PRIORITY_COLOR[issue.priority] ?? 'text-gray-500'} />
                      {issue.checklist_total > 0 && (
                        <span className="app-text-micro flex items-center gap-0.5 text-gray-500">
                          <CheckSquare size={11} />
                          {issue.checklist_done}/{issue.checklist_total}
                        </span>
                      )}
                      {issue.estimate_hours != null && issue.estimate_hours > 0 && (
                        <span className="app-text-micro flex items-center gap-0.5 text-gray-500">
                          <Clock size={11} />
                          {Math.round(issue.time_spent_minutes / 60 * 10) / 10}/{issue.estimate_hours}h
                        </span>
                      )}
                      {issue.due_date && (
                        <div className="app-text-micro flex items-center gap-1 text-gray-500">
                          <Calendar size={10} />
                          <span>{formatDate(issue.due_date)}</span>
                        </div>
                      )}
                    </div>
                    <div className="flex items-center -space-x-2">
                      {issue.assignee_name ? (
                        <div className="app-text-micro flex h-6 w-6 items-center justify-center rounded-full border-2 border-app-bg bg-blue-500 font-bold text-white">
                          {initials(issue.assignee_name)}
                        </div>
                      ) : (
                        <div className="w-6 h-6 rounded-full bg-app-surface-sidebar border-2 border-app-bg flex items-center justify-center text-gray-600">
                          <User2 size={12} />
                        </div>
                      )}
                    </div>
                  </div>
                </motion.div>
              ))}
              <button className="app-text-micro w-full rounded-lg border border-dashed border-app-border py-2 text-gray-600 transition-all hover:border-gray-400 hover:text-gray-400">
                + Add Task
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};
