import { LazyMotion, domAnimation, m } from 'motion/react';
import { useTranslation } from 'react-i18next';
import {
  Calendar,
  CheckSquare,
  CornerDownRight,
  Eye,
  Flag,
  GitBranch,
  MoreHorizontal,
  Plus,
} from 'lucide-react';
import type {
  PmsTask,
  PmsTaskListMember,
  PmsTaskListStatus,
} from '../api/pms-api';
import { PRIORITY_COLOR, formatDate } from './pms-constants';
import { PMS_DEFAULT_LABEL_COLOR } from './pms-color-palettes';
import { StatusIconGlyph } from './StatusIcon';
import { buildTaskBoardPresentationModel } from './task-list-presentation-model';
import { TaskAssigneeStack } from './TaskAssigneeStack';

export const BoardView = ({
  tasks,
  onSelectIssue,
  onUpdateIssue,
  selectedIds,
  onToggleSelect,
  members,
  taskListStatuses,
}: {
  tasks: PmsTask[];
  onSelectIssue: (task: PmsTask) => void;
  onUpdateIssue?: (taskId: string, payload: Record<string, unknown>) => void;
  selectedIds?: Set<string>;
  onToggleSelect?: (taskId: string) => void;
  members?: readonly PmsTaskListMember[];
  taskListStatuses?: PmsTaskListStatus[];
}) => {
  const { t } = useTranslation('apps');
  const boardModel = buildTaskBoardPresentationModel({
    taskListStatuses,
    tasks,
  });

  function handleDrop(e: React.DragEvent, targetStatus: string) {
    e.preventDefault();
    const taskId = e.dataTransfer.getData('text/plain');
    if (taskId && onUpdateIssue) {
      onUpdateIssue(taskId, { status: targetStatus });
    }
  }

  function handleDragOver(e: React.DragEvent) {
    if (onUpdateIssue) e.preventDefault();
  }

  return (
    <LazyMotion features={domAnimation}>
      <div className="flex gap-6 h-full overflow-x-auto pb-4 custom-scrollbar">
        {boardModel.columns.map((column) => {
          return (
            <div
              key={column.status}
              className="flex-shrink-0 w-80 flex flex-col gap-4"
              onDrop={(e) => handleDrop(e, column.status)}
              onDragOver={handleDragOver}
            >
              <div className="flex items-center justify-between px-2">
                <div className="flex items-center gap-2">
                  <StatusIconGlyph
                    label={column.label}
                    status={column.status}
                    taskListStatuses={taskListStatuses}
                  />
                  <h3 className="app-text-overline text-app-ink">
                    {column.label}
                  </h3>
                  <span className="app-text-micro font-bold text-app-ink/70">
                    {column.taskCount}
                  </span>
                </div>
                {onUpdateIssue ? (
                  <div className="flex items-center gap-1 text-app-ink/70">
                    <Plus
                      size={14}
                      className="cursor-pointer hover:text-white"
                    />
                    <MoreHorizontal
                      size={14}
                      className="cursor-pointer hover:text-white"
                    />
                  </div>
                ) : null}
              </div>

              <div className="flex-1 space-y-3">
                {column.tasks.map((taskPresentation) => {
                  const {
                    childCount,
                    depth,
                    parent,
                    progress,
                    showParent,
                    task,
                  } = taskPresentation;
                  return (
                    <m.div
                      key={task.id}
                      layoutId={task.id}
                      draggable={Boolean(onUpdateIssue)}
                      onDragStartCapture={(
                        e: React.DragEvent<HTMLDivElement>,
                      ) => {
                        if (e.dataTransfer)
                          e.dataTransfer.setData('text/plain', task.id);
                      }}
                      onClick={() => onSelectIssue(task)}
                      className="card p-4 hover:border-app-accent transition-all cursor-pointer group space-y-4 relative"
                      style={depth > 0 ? { marginLeft: depth * 10 } : undefined}
                    >
                      {onToggleSelect && (
                        <div
                          className={`absolute top-2 left-2 z-10 ${selectedIds?.has(task.id) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity`}
                        >
                          <input
                            type="checkbox"
                            aria-label={task.title}
                            checked={selectedIds?.has(task.id) ?? false}
                            onChange={(e) => {
                              e.stopPropagation();
                              onToggleSelect(task.id);
                            }}
                            onClick={(e) => e.stopPropagation()}
                            className="size-3.5 cursor-pointer rounded accent-app-accent"
                          />
                        </div>
                      )}
                      <button
                        aria-label={t('pms.list.viewDetails', {
                          reference: task.reference,
                        })}
                        className="absolute right-2 top-2 z-10 inline-flex size-7 items-center justify-center rounded-md border border-transparent bg-app-surface/90 text-app-ink/45 opacity-0 shadow-sm transition-opacity hover:border-app-border hover:bg-app-surface-sidebar hover:text-app-accent focus:border-app-border focus:bg-app-surface-sidebar focus:text-app-accent focus:opacity-100 focus-visible:opacity-100 group-hover:opacity-100"
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelectIssue(task);
                        }}
                        title={t('pms.list.viewDetails', {
                          reference: task.reference,
                        })}
                        type="button"
                      >
                        <Eye size={14} />
                      </button>
                      <div className="flex flex-wrap items-center gap-1.5 pr-7">
                        {task.labels.map((label) => (
                          <span
                            key={label.id}
                            className="app-text-micro rounded border border-app-border bg-app-surface-sidebar px-1.5 py-0.5 text-app-ink/55"
                            style={
                              label.color !== PMS_DEFAULT_LABEL_COLOR
                                ? {
                                    borderColor: label.color,
                                    color: label.color,
                                  }
                                : undefined
                            }
                          >
                            {label.name}
                          </span>
                        ))}
                        {childCount > 0 ? (
                          <span className="app-text-micro inline-flex items-center gap-1 text-app-ink/35">
                            <GitBranch size={11} />
                            {childCount}
                          </span>
                        ) : null}
                      </div>
                      {showParent && parent ? (
                        <div className="app-text-caption flex min-w-0 items-center gap-1 text-app-ink/40">
                          <CornerDownRight size={12} className="shrink-0" />
                          <span className="truncate">{parent.title}</span>
                        </div>
                      ) : null}
                      <div className="flex min-w-0 items-start gap-2">
                        {depth > 0 ? (
                          <CornerDownRight
                            size={13}
                            className="mt-0.5 shrink-0 text-app-ink/35"
                          />
                        ) : null}
                        <h4 className="app-text-body min-w-0 font-medium leading-tight text-app-ink transition-colors group-hover:text-app-accent">
                          {task.title}
                        </h4>
                      </div>
                      <div className="flex items-center justify-between pt-2 border-t border-app-border/50">
                        <div className="flex items-center gap-3">
                          <Flag
                            size={14}
                            className={
                              PRIORITY_COLOR[task.priority] ?? 'text-app-ink/55'
                            }
                          />
                          {progress.hasChecklistProgress && (
                            <span className="app-text-micro flex items-center gap-0.5 text-app-ink/55">
                              <CheckSquare size={11} />
                              {progress.checklistProgressLabel}
                            </span>
                          )}
                          {task.due_date && (
                            <div className="app-text-micro flex items-center gap-1 text-app-ink/55">
                              <Calendar size={10} />
                              <span>{formatDate(task.due_date)}</span>
                            </div>
                          )}
                        </div>
                        <div className="flex items-center">
                          <TaskAssigneeStack
                            members={members}
                            task={task}
                            unassignedLabel={t('pms.taskDetail.unassigned')}
                          />
                        </div>
                      </div>
                    </m.div>
                  );
                })}
                {onUpdateIssue ? (
                  <button
                    type="button"
                    className="app-text-micro w-full rounded-lg border border-dashed border-app-border py-2 text-app-ink/70 transition-all hover:border-app-border-strong hover:text-app-ink/45"
                  >
                    {t('pms.list.addTask')}
                  </button>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </LazyMotion>
  );
};
