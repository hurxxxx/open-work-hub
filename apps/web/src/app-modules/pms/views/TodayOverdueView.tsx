import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  normalizeTimeZone,
  zonedDateKey,
} from '@/src/platform/time/time-utils';
import { AlertCircle, Calendar, CheckCircle2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  listAllPmsTaskLists,
  listAllTodayOverdueTasks,
  type PmsTask,
  type PmsTaskList,
} from '../api/pms-api';
import { formatDate } from './pms-constants';
import { buildPmsTaskContextLabel } from './pms-task-context';
import { buildPmsTaskListToolPath } from './pms-view-route';
import { PmsCenteredLoadingState } from './PmsCenteredStateBlock';
import { TaskAssigneeStack } from './TaskAssigneeStack';
import { buildTodayOverdueTaskGroups } from './today-overdue-model';
import { usePmsTaskListChangeSubscription } from './usePmsTaskListChangeSubscription';

type TodayOverdueTaskLoadResult = {
  taskLists: PmsTaskList[];
  tasks: PmsTask[];
};

export async function loadTodayOverdueTasks(
  token: string,
  today: string,
): Promise<TodayOverdueTaskLoadResult> {
  const [taskListResponse, taskResponse] = await Promise.all([
    listAllPmsTaskLists(token, undefined),
    listAllTodayOverdueTasks(token, today),
  ]);
  return {
    taskLists: taskListResponse.items,
    tasks: taskResponse.items,
  };
}

export const TodayOverdueView = (_context: Record<string, never>) => {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();

  const [data, setData] = useState<TodayOverdueTaskLoadResult>({
    taskLists: [],
    tasks: [],
  });
  const [loading, setLoading] = useState(true);
  const loadGenerationRef = useRef(0);
  const today = zonedDateKey(new Date(), normalizeTimeZone(user?.time_zone));

  const reloadTodayOverdueTasks = useCallback(async () => {
    if (!token) return;
    const loadGeneration = loadGenerationRef.current + 1;
    loadGenerationRef.current = loadGeneration;
    setLoading(true);
    try {
      const nextData = await loadTodayOverdueTasks(token, today);
      if (loadGeneration === loadGenerationRef.current) setData(nextData);
    } finally {
      if (loadGeneration === loadGenerationRef.current) setLoading(false);
    }
  }, [today, token]);

  useEffect(() => {
    void reloadTodayOverdueTasks();
  }, [reloadTodayOverdueTasks]);

  usePmsTaskListChangeSubscription(
    useCallback(() => {
      void reloadTodayOverdueTasks();
    }, [reloadTodayOverdueTasks]),
  );

  const { overdue, today: todayIssues } = buildTodayOverdueTaskGroups(
    data.tasks,
    today,
  );
  const fallbackSpaceName = t('pms.spaceOverview.fallbackSpaceName');
  const taskContextLabel = (task: PmsTask) =>
    buildPmsTaskContextLabel({
      fallbackSpaceName,
      task,
      taskLists: data.taskLists,
    });
  const taskPath = (task: PmsTask) =>
    buildPmsTaskListToolPath({
      taskId: task.id,
      taskListId: task.list_id,
    });

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-app-bg border-b border-app-border px-8 pt-6 pb-4">
        <h1 className="app-text-title-lg text-app-ink">
          {t('pms.todayOverdue.title')}
        </h1>
        <p className="app-text-body mt-1 text-app-ink/55">
          {t('pms.todayOverdue.description')}
        </p>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        {loading ? (
          <PmsCenteredLoadingState minHeightClassName="py-16" />
        ) : (
          <div className="max-w-4xl mx-auto space-y-8">
            {/* Overdue */}
            <section>
              <div className="flex items-center gap-2 mb-4 text-app-danger">
                <AlertCircle size={18} />
                <h2 className="app-text-title-md">
                  {t('pms.todayOverdue.overdue')}
                </h2>
                <span className="app-text-label rounded-full bg-app-danger/10 px-2 py-0.5 text-app-danger">
                  {overdue.length}
                </span>
              </div>
              <div className="space-y-2">
                {overdue.map((task) => (
                  <IssueAgendaItem
                    key={task.id}
                    contextLabel={taskContextLabel(task)}
                    isOverdue
                    task={task}
                    to={taskPath(task)}
                  />
                ))}
                {overdue.length === 0 && (
                  <p className="app-text-body text-app-ink/40">
                    {t('pms.todayOverdue.noOverdue')}
                  </p>
                )}
              </div>
            </section>

            {/* Today */}
            <section>
              <div className="flex items-center gap-2 mb-4 text-blue-400">
                <Calendar size={18} />
                <h2 className="app-text-title-md">
                  {t('pms.todayOverdue.today')}
                </h2>
                <span className="app-text-label rounded-full bg-blue-400/10 px-2 py-0.5 text-blue-400">
                  {todayIssues.length}
                </span>
              </div>
              <div className="space-y-2">
                {todayIssues.map((task) => (
                  <IssueAgendaItem
                    key={task.id}
                    contextLabel={taskContextLabel(task)}
                    task={task}
                    to={taskPath(task)}
                  />
                ))}
                {todayIssues.length === 0 && (
                  <p className="app-text-body text-app-ink/40">
                    {t('pms.todayOverdue.noToday')}
                  </p>
                )}
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
};

const IssueAgendaItem = ({
  contextLabel,
  task,
  to,
  isOverdue = false,
}: {
  contextLabel: string | null;
  task: PmsTask;
  to: string;
  isOverdue?: boolean;
}) => (
  <Link
    className="group flex items-center justify-between rounded-lg border border-app-border bg-app-surface-sidebar p-4 transition-colors hover:border-app-border-strong"
    to={to}
  >
    <div className="flex min-w-0 items-center gap-4">
      <span className="shrink-0 text-app-ink/55 transition-colors group-hover:text-app-success">
        <CheckCircle2 size={20} />
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="app-text-body truncate font-medium text-app-ink transition-colors group-hover:text-app-accent">
            {task.title}
          </h3>
        </div>
        <div className="app-text-caption mt-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-app-ink/55">
          <span
            className={cn(
              'flex shrink-0 items-center gap-1',
              isOverdue ? 'text-app-danger' : '',
            )}
          >
            <Calendar size={12} />
            {formatDate(task.due_date)}
          </span>
          {contextLabel ? (
            <span className="min-w-0 truncate">{contextLabel}</span>
          ) : null}
          {task.labels.length > 0 && (
            <span className="flex shrink-0 items-center gap-1">
              <span className="size-2 rounded-full bg-app-info" />
              {task.labels[0].name}
            </span>
          )}
        </div>
      </div>
    </div>
    <TaskAssigneeStack task={task} />
  </Link>
);
