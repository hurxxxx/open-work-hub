import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  History,
  FolderKanban,
  ChevronRight,
  Plus,
  LayoutDashboard,
  Loader2,
} from 'lucide-react';
import { DonutChartCard, Panel } from '@aidoo/ui';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  getPmsDashboardSummary,
  listPmsTaskLists,
  type PmsDashboardSummary,
  type PmsTaskList,
} from '../api/pms-api';
import { CreateTaskListModal } from './CreateTaskListModal';

function upsertTaskList(taskLists: PmsTaskList[], taskList: PmsTaskList): PmsTaskList[] {
  return [taskList, ...taskLists.filter((item) => item.id !== taskList.id)].sort(
    (left, right) => right.updated_at.localeCompare(left.updated_at),
  );
}

export const OverviewView = () => {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState<PmsDashboardSummary | null>(null);
  const [taskLists, setTaskLists] = useState<PmsTaskList[]>([]);
  const [loading, setLoading] = useState(true);
  const [createTaskListOpen, setCreateTaskListOpen] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    Promise.all([
      getPmsDashboardSummary(token),
      listPmsTaskLists(token),
    ])
      .then(([dash, taskListResponse]) => {
        setDashboard(dash);
        setTaskLists(taskListResponse.items);
      })
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 size={24} className="animate-spin text-app-accent" />
      </div>
    );
  }

  const statusCategories = dashboard?.status_counts.map(s => s.label) ?? [];
  const statusValues = dashboard?.status_counts.map(s => s.count) ?? [];
  const statusColors = ['#6b7280', '#6b7280', '#3b82f6', '#22c55e', '#ef4444'];

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Welcome Section */}
      <div className="rounded-xl border border-app-border bg-app-surface p-8">
        <h2 className="app-text-title-lg mb-2 text-app-ink">
          {user?.full_name
            ? t('pms.overviewPage.greetingName', { name: user.full_name.split(' ')[0] })
            : t('pms.overviewPage.greeting')}
        </h2>
        <p className="app-text-body max-w-xl text-app-ink/60">
          {dashboard
            ? t('pms.overviewPage.summary', {
                lists: dashboard.list_count,
                active: dashboard.active_issue_count,
                overdue: dashboard.overdue_issue_count,
              })
            : t('pms.overviewPage.loadingSummary')}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Lists */}
        <Panel>
          <h3 className="app-text-title-md mb-4 flex items-center justify-between text-app-ink">
            <div className="flex items-center gap-2">
              <History size={16} className="text-app-accent" />
              {t('pms.overviewPage.lists')}
            </div>
            <button
              onClick={() => setCreateTaskListOpen(true)}
              className="app-text-control-sm flex items-center gap-1 text-app-accent transition-colors hover:text-app-accent/80"
            >
              <Plus size={14} />
              <span>{t('common:actions.create')}</span>
            </button>
          </h3>
          <div className="space-y-3">
            {taskLists.map((taskList) => (
              <div
                key={taskList.id}
                onClick={() => navigate(`/tool/pms-list-${taskList.id}`)}
                className="flex items-center gap-3 p-2 hover:bg-app-surface-hover rounded-md transition-colors group cursor-pointer"
              >
                <div className="w-8 h-8 bg-blue-500/10 rounded flex items-center justify-center">
                  <FolderKanban size={16} className="text-blue-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="app-text-body-sm truncate font-medium text-app-ink transition-colors group-hover:text-app-accent">
                    {taskList.name}
                  </div>
                  <div className="app-text-micro text-app-ink/40">
                    {taskList.team_name && <span>{taskList.team_name} · </span>}
                    {t('pms.overviewPage.listProgress', {
                      count: taskList.issue_count,
                      progress: Math.round(taskList.progress * 100),
                    })}
                  </div>
                </div>
                <ChevronRight
                  size={14}
                  className="text-app-ink/30 opacity-0 group-hover:opacity-100 transition-opacity"
                />
              </div>
            ))}
            {taskLists.length === 0 && (
              <p className="app-text-body text-app-ink/40">{t('pms.overviewPage.noLists')}</p>
            )}
          </div>
        </Panel>

        {/* Status Distribution */}
        {statusCategories.length > 0 && (
          <DonutChartCard
            title={
              <span className="app-text-title-md flex items-center gap-2 text-app-ink">
                <LayoutDashboard size={16} className="text-app-accent" />
                {t('pms.overviewPage.statusDistribution')}
              </span>
            }
            categories={statusCategories}
            series={statusCategories.map((cat, i) => ({
              key: cat,
              label: cat,
              color: statusColors[i % statusColors.length],
              data: [statusValues[i]],
            }))}
          />
        )}

        {/* Recent Activity */}
        <Panel>
          <h3 className="app-text-title-md mb-4 flex items-center justify-between text-app-ink">
            <div className="flex items-center gap-2">
              <History size={16} className="text-app-accent" />
              {t('pms.overviewPage.recentActivity')}
            </div>
          </h3>
          <div className="space-y-3">
            {dashboard?.recent_activity.slice(0, 5).map((activity) => (
              <div
                key={activity.id}
                className="flex items-center gap-3 p-2 hover:bg-app-surface-hover rounded-md transition-colors cursor-pointer"
              >
                <div className="w-6 h-6 rounded-full bg-app-surface-sidebar border border-app-border flex items-center justify-center text-[8px] font-bold text-app-ink/60">
                  {activity.actor_name?.[0] ?? '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="app-text-caption truncate text-app-ink/70">{activity.message}</div>
                  <div className="app-text-micro text-app-ink/40">{activity.issue_reference}</div>
                </div>
              </div>
            ))}
            {(!dashboard?.recent_activity || dashboard.recent_activity.length === 0) && (
              <p className="app-text-body text-app-ink/40">
                {t('pms.overviewPage.noRecentActivity')}
              </p>
            )}
          </div>
        </Panel>
      </div>

      <CreateTaskListModal
        isOpen={createTaskListOpen}
        onClose={() => setCreateTaskListOpen(false)}
        onCreated={(taskList) => {
          setTaskLists((current) => upsertTaskList(current, taskList));
          navigate(`/tool/pms-list-${taskList.id}`);
          if (!token) return;
          void getPmsDashboardSummary(token).then((dash) => {
            setDashboard(dash);
          });
        }}
      />
    </div>
  );
};
