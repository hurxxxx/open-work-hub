import { DateInput } from '@/src/components/date/DateInput';
import { Badge, Button } from '@open-work-hub/ui';
import {
  CheckSquare,
  CornerDownRight,
  Eye,
  Flag,
  GitBranch,
  MessageSquare,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type {
  PmsTask,
  PmsTaskListMember,
  PmsTaskListStatus,
} from '../api/pms-api';
import { formatDate, getStatusTone, PRIORITY_COLOR } from './pms-constants';
import { StatusIconGlyph } from './StatusIcon';
import { buildTaskTablePresentationModel } from './task-list-presentation-model';
import { TaskAssigneeStack } from './TaskAssigneeStack';
import { TaskCard } from './TaskCard';

export const TableView = ({
  tasks,
  onSelectIssue,
  selectedIds,
  onToggleSelect,
  members,
  taskListStatuses,
  canEdit = false,
  onUpdateIssue,
}: {
  tasks: PmsTask[];
  onSelectIssue: (task: PmsTask) => void;
  selectedIds?: Set<string>;
  onToggleSelect?: (taskId: string) => void;
  members?: readonly PmsTaskListMember[];
  taskListStatuses?: PmsTaskListStatus[];
  canEdit?: boolean;
  onUpdateIssue?: (
    taskId: string,
    payload: Record<string, unknown>,
  ) => Promise<void> | void;
}) => {
  const { t } = useTranslation('apps');
  const completionDateEditable = canEdit && Boolean(onUpdateIssue);
  const tableModel = buildTaskTablePresentationModel({
    taskListStatuses,
    tasks,
  });
  return (
    <>
      <div className="space-y-2 lg:hidden">
        {tableModel.rows.map((row) => {
          const { childCount, task } = row;
          return (
            <TaskCard
              key={task.id}
              childCount={childCount}
              completedDateLabel={t('pms.taskDetail.completedDate')}
              depth={row.cardDepth}
              task={task}
              onSelectIssue={onSelectIssue}
              onToggleSelect={onToggleSelect}
              selectTaskLabel={(reference) =>
                t('pms.list.selectIssue', { reference })
              }
              selected={selectedIds?.has(task.id) ?? false}
              members={members}
              taskListStatuses={taskListStatuses}
              unassignedLabel={t('pms.taskDetail.unassigned')}
              viewDetailsLabel={(reference) =>
                t('pms.list.viewDetails', { reference })
              }
            />
          );
        })}
      </div>

      <div className="hidden overflow-hidden rounded-lg border border-app-border bg-app-surface lg:block">
        <div className="overflow-x-auto custom-scrollbar">
          <table className="app-text-body-sm w-full text-left">
            <thead>
              <tr className="app-text-overline border-b border-app-border bg-app-surface-sidebar/50 text-app-ink/50">
                {onToggleSelect && (
                  <th className="w-10 px-4 py-3">
                    <span className="sr-only">
                      {t('pms.bulk.selectAll', {
                        count: tableModel.rows.length,
                      })}
                    </span>
                  </th>
                )}
                <th className="py-3 px-4 min-w-[250px]">{t('pms.taskName')}</th>
                <th className="py-3 px-4">{t('pms.list.status')}</th>
                <th className="py-3 px-4">{t('pms.list.assignee')}</th>
                <th className="py-3 px-4">{t('pms.list.dueDate')}</th>
                <th className="py-3 px-4">
                  {t('pms.taskDetail.completedDate')}
                </th>
                <th className="py-3 px-4">{t('pms.list.priority')}</th>
                <th className="py-3 px-4">{t('pms.bulk.labelsLabel')}</th>
                <th className="py-3 px-4 text-right">
                  {t('pms.table.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-app-border">
              {tableModel.rows.map((row) => {
                const { childCount, progress, statusLabel, tableDepth, task } =
                  row;
                return (
                  <tr
                    key={task.id}
                    onClick={() => onSelectIssue(task)}
                    className="hover:bg-app-surface-hover transition-colors group cursor-pointer"
                  >
                    {onToggleSelect && (
                      <td className="py-3 px-4">
                        <input
                          aria-label={t('pms.list.selectIssue', {
                            reference: task.reference,
                          })}
                          type="checkbox"
                          checked={selectedIds?.has(task.id) ?? false}
                          onChange={(e) => {
                            e.stopPropagation();
                            onToggleSelect(task.id);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="size-3.5 cursor-pointer rounded accent-app-accent"
                        />
                      </td>
                    )}
                    <td className="py-3 px-4">
                      <div
                        className="flex min-w-0 items-center gap-2"
                        style={
                          tableDepth > 0
                            ? { paddingLeft: tableDepth * 20 }
                            : undefined
                        }
                      >
                        {tableDepth > 0 ? (
                          <CornerDownRight
                            size={13}
                            className="shrink-0 text-app-ink/35"
                          />
                        ) : null}
                        <span className="min-w-0 truncate font-medium text-app-ink">
                          {task.title}
                        </span>
                        {childCount > 0 ? (
                          <span className="app-text-micro inline-flex items-center gap-1 text-app-ink/35">
                            <GitBranch size={11} />
                            {childCount}
                          </span>
                        ) : null}
                        {task.comments_count > 0 && (
                          <div className="flex items-center gap-1 text-app-ink/40">
                            <MessageSquare size={12} />
                            <span className="app-text-micro">
                              {task.comments_count}
                            </span>
                          </div>
                        )}
                        {progress.hasChecklistProgress && (
                          <div className="flex items-center gap-0.5 text-app-ink/40">
                            <CheckSquare size={11} />
                            <span className="app-text-micro">
                              {progress.checklistProgressLabel}
                            </span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span className="inline-flex items-center gap-2">
                        <StatusIconGlyph
                          label={statusLabel}
                          status={task.status}
                          taskListStatuses={taskListStatuses}
                        />
                        <Badge
                          tone={getStatusTone(task.status, taskListStatuses)}
                        >
                          {statusLabel}
                        </Badge>
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <TaskAssigneeStack
                        members={members}
                        showName
                        task={task}
                        unassignedLabel="-"
                      />
                    </td>
                    <td className="py-3 px-4 text-app-ink/60">
                      {formatDate(task.due_date) || '-'}
                    </td>
                    <td className="py-3 px-4 text-app-ink/60">
                      {completionDateEditable ? (
                        <div onClick={(event) => event.stopPropagation()}>
                          <DateInput
                            aria-label={t('pms.taskDetail.completedDate')}
                            className="app-text-caption min-w-[7.5rem] rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
                            onValueChange={(value) => {
                              void onUpdateIssue?.(task.id, {
                                completed_date: value || null,
                              });
                            }}
                            value={task.completed_date}
                          />
                        </div>
                      ) : (
                        formatDate(task.completed_date) || '-'
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <Flag
                          size={14}
                          className={
                            PRIORITY_COLOR[task.priority] ?? 'text-app-ink/55'
                          }
                        />
                        <span className="text-app-ink/50">
                          {task.priority_label}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1">
                        {task.labels.map((label) => (
                          <Badge key={label.id} tone="neutral">
                            {label.name}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Button
                        aria-label={t('pms.list.viewDetails', {
                          reference: task.reference,
                        })}
                        title={t('pms.list.viewDetails', {
                          reference: task.reference,
                        })}
                        variant="ghost"
                        size="icon"
                        className="opacity-0 group-hover:opacity-100 focus:opacity-100"
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelectIssue(task);
                        }}
                      >
                        <Eye size={14} />
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
};
