import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  History,
  FolderKanban,
  ChevronRight,
  Plus,
  LayoutDashboard,
  Loader2,
} from 'lucide-react';
import { DonutChartCard, Panel } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  getPmsDashboardSummary,
  listPmsLists,
  type PmsDashboardSummary,
  type PmsList,
} from '@/src/domains/pms/pms-api';
import { CreateProjectModal } from './CreateProjectModal';

function upsertProject(projects: PmsList[], project: PmsList): PmsList[] {
  return [project, ...projects.filter((item) => item.id !== project.id)].sort(
    (left, right) => right.updated_at.localeCompare(left.updated_at),
  );
}

export const OverviewView = () => {
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState<PmsDashboardSummary | null>(null);
  const [projects, setProjects] = useState<PmsList[]>([]);
  const [loading, setLoading] = useState(true);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    Promise.all([
      getPmsDashboardSummary(token),
      listPmsLists(token),
    ])
      .then(([dash, projs]) => {
        setDashboard(dash);
        setProjects(projs.items);
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
          {user?.full_name ? `Hello, ${user.full_name.split(' ')[0]}!` : 'Welcome!'}
        </h2>
        <p className="app-text-body max-w-xl text-app-ink/60">
          {dashboard
            ? `${dashboard.project_count} lists · ${dashboard.active_issue_count} active issues · ${dashboard.overdue_issue_count} overdue`
            : 'Loading summary...'}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Lists */}
        <Panel>
          <h3 className="app-text-title-md mb-4 flex items-center justify-between text-app-ink">
            <div className="flex items-center gap-2">
              <History size={16} className="text-app-accent" />
              Lists
            </div>
            <button
              onClick={() => setCreateProjectOpen(true)}
              className="app-text-control-sm flex items-center gap-1 text-app-accent transition-colors hover:text-app-accent/80"
            >
              <Plus size={14} />
              <span>New</span>
            </button>
          </h3>
          <div className="space-y-3">
            {projects.map((project) => (
              <div
                key={project.id}
                onClick={() => navigate(`/tool/pms-list-${project.id}`)}
                className="flex items-center gap-3 p-2 hover:bg-app-surface-hover rounded-md transition-colors group cursor-pointer"
              >
                <div className="w-8 h-8 bg-blue-500/10 rounded flex items-center justify-center">
                  <FolderKanban size={16} className="text-blue-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="app-text-body-sm truncate font-medium text-app-ink transition-colors group-hover:text-app-accent">
                    {project.name}
                  </div>
                  <div className="app-text-micro text-app-ink/40">
                    {project.team_name && <span>{project.team_name} · </span>}
                    {project.issue_count} issues · {Math.round(project.progress * 100)}% done
                  </div>
                </div>
                <ChevronRight
                  size={14}
                  className="text-app-ink/30 opacity-0 group-hover:opacity-100 transition-opacity"
                />
              </div>
            ))}
            {projects.length === 0 && (
              <p className="app-text-body text-app-ink/40">No lists yet</p>
            )}
          </div>
        </Panel>

        {/* Status Distribution */}
        {statusCategories.length > 0 && (
          <DonutChartCard
            title={
              <span className="app-text-title-md flex items-center gap-2 text-app-ink">
                <LayoutDashboard size={16} className="text-app-accent" />
                Status Distribution
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
              Recent Activity
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
              <p className="app-text-body text-app-ink/40">No recent activity</p>
            )}
          </div>
        </Panel>
      </div>

      <CreateProjectModal
        isOpen={createProjectOpen}
        onClose={() => setCreateProjectOpen(false)}
        onCreated={(project) => {
          setProjects((current) => upsertProject(current, project));
          navigate(`/tool/pms-list-${project.id}`);
          if (!token) return;
          void getPmsDashboardSummary(token).then((dash) => {
            setDashboard(dash);
          });
        }}
      />
    </div>
  );
};
