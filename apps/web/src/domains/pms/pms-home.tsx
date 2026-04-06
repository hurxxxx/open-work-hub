import {
  Button,
  EmptyState,
  InlineNotice,
  Input,
  MetricInline,
  Panel,
  StatusBadge,
  type DataTableColumn,
  DataTable,
} from '@aidoo/ui';
import { useEffect, useState } from 'react';

import {
  createPmsProject,
  getPmsDashboardSummary,
  listPmsProjects,
  type PmsDashboardSummary,
  type PmsProject,
} from './pms-api';

const PROJECT_COLUMNS: DataTableColumn<PmsProject>[] = [
  {
    accessorKey: 'name',
    header: 'Project',
    cell: ({ row }) => (
      <div className="grid gap-0.5">
        <strong className="text-[0.84rem] text-[var(--ui-color-ink)]">
          {row.original.name}
        </strong>
        <small className="text-[0.74rem] text-[var(--ui-color-ink-subtle)]">
          {row.original.key} · {row.original.description || '설명 없음'}
        </small>
      </div>
    ),
  },
  {
    accessorKey: 'progress',
    header: 'Progress',
    cell: ({ row }) => `${Math.round(row.original.progress * 100)}%`,
  },
  {
    accessorKey: 'issue_count',
    header: 'Open',
    cell: ({ row }) => String(row.original.issue_count),
  },
  {
    accessorKey: 'overdue_issue_count',
    header: 'Overdue',
    cell: ({ row }) => String(row.original.overdue_issue_count),
  },
];

export interface PmsHomeProps {
  token: string;
  onOpenProject: (projectId: string) => void;
}

export function PmsHome({ token, onOpenProject }: PmsHomeProps) {
  const [dashboard, setDashboard] = useState<PmsDashboardSummary | null>(null);
  const [projects, setProjects] = useState<PmsProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projectForm, setProjectForm] = useState({
    key: '',
    name: '',
    description: '',
  });

  async function loadState() {
    setLoading(true);
    setError(null);
    try {
      const [dashboardState, projectsState] = await Promise.all([
        getPmsDashboardSummary(token),
        listPmsProjects(token),
      ]);
      setDashboard(dashboardState);
      setProjects(projectsState.items);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : 'PMS 홈을 불러오지 못했습니다.',
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadState();
  }, [token]);

  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const nextProject = await createPmsProject(token, {
        key: projectForm.key.trim(),
        name: projectForm.name.trim(),
        description: projectForm.description.trim(),
      });
      setProjectForm({ key: '', name: '', description: '' });
      await loadState();
      onOpenProject(nextProject.id);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '프로젝트를 만들지 못했습니다.',
      );
    }
  }

  return (
    <div className="grid gap-3">
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

      <section className="grid gap-3 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] px-3 py-2 lg:grid-cols-4">
        <MetricInline label="Projects" value={String(dashboard?.project_count ?? 0)} />
        <MetricInline label="Active issues" value={String(dashboard?.active_issue_count ?? 0)} />
        <MetricInline label="Overdue" value={String(dashboard?.overdue_issue_count ?? 0)} />
        <MetricInline
          label="Milestones due soon"
          value={String(dashboard?.milestone_due_soon_count ?? 0)}
        />
      </section>

      <div className="grid gap-3 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Panel
          eyebrow="Team space"
          title="프로젝트 허브"
          description="팀 스페이스의 프로젝트와 최근 상태를 봅니다."
        >
          <div className="grid gap-3">
            <form className="grid gap-2" onSubmit={(event) => void handleCreateProject(event)}>
              <div className="grid grid-cols-[84px_minmax(0,1fr)] gap-2">
                <Input
                  value={projectForm.key}
                  onChange={(event) =>
                    setProjectForm((current) => ({
                      ...current,
                      key: event.target.value.toUpperCase(),
                    }))
                  }
                  placeholder="KEY"
                />
                <Input
                  value={projectForm.name}
                  onChange={(event) =>
                    setProjectForm((current) => ({ ...current, name: event.target.value }))
                  }
                  placeholder="프로젝트 이름"
                />
              </div>
              <Input
                value={projectForm.description}
                onChange={(event) =>
                  setProjectForm((current) => ({
                    ...current,
                    description: event.target.value,
                  }))
                }
                placeholder="설명"
              />
              <Button type="submit" variant="primary">
                새 프로젝트
              </Button>
            </form>

            <div className="grid gap-2 border-t border-[var(--ui-color-border)] pt-3">
              {projects.length ? (
                projects.map((project) => (
                  <button
                    key={project.id}
                    type="button"
                    className="grid gap-1 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] px-3 py-2.5 text-left"
                    onClick={() => onOpenProject(project.id)}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <strong className="text-[0.82rem] text-[var(--ui-color-ink)]">
                        {project.key}
                      </strong>
                      <StatusBadge>{project.role}</StatusBadge>
                    </div>
                    <span className="text-[0.88rem] font-semibold text-[var(--ui-color-ink)]">
                      {project.name}
                    </span>
                    <small className="text-[0.74rem] text-[var(--ui-color-ink-subtle)]">
                      Open {project.issue_count} · Overdue {project.overdue_issue_count}
                    </small>
                  </button>
                ))
              ) : (
                <EmptyState
                  title="프로젝트가 없습니다"
                  description="첫 프로젝트를 만들면 팀 스페이스 홈에서 바로 열 수 있습니다."
                />
              )}
            </div>
          </div>
        </Panel>

        <div className="grid gap-3">
          <Panel
            eyebrow="Overview"
            title="진행 중인 프로젝트"
            description="프로젝트 리스트를 기준으로 작업면에 진입합니다."
          >
            <DataTable
              columns={PROJECT_COLUMNS}
              rows={projects}
              loading={loading}
              selection={{
                getRowId: (project) => project.id,
                onRowClick: (project) => onOpenProject(project.id),
              }}
              emptyState={
                <EmptyState
                  title="프로젝트가 없습니다"
                  description="좌측에서 새 프로젝트를 만들면 여기서 바로 관리할 수 있습니다."
                />
              }
            />
          </Panel>

          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_340px]">
            <Panel
              eyebrow="Recent activity"
              title="최근 업데이트"
              description="팀 스페이스 기준 최근 작업입니다."
            >
              {dashboard?.recent_activity.length ? (
                <div className="grid gap-2">
                  {dashboard.recent_activity.map((activity) => (
                    <div
                      key={activity.id}
                      className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] px-3 py-2.5"
                    >
                      <strong className="block text-[0.82rem] text-[var(--ui-color-ink)]">
                        {activity.issue_reference}
                      </strong>
                      <p className="m-0 text-[0.8rem] text-[var(--ui-color-ink)]">
                        {activity.message}
                      </p>
                      <small className="text-[0.72rem] text-[var(--ui-color-ink-subtle)]">
                        {activity.created_at}
                      </small>
                    </div>
                  ))}
                </div>
              ) : (
                <InlineNotice tone="info">표시할 최근 활동이 없습니다.</InlineNotice>
              )}
            </Panel>

            <Panel
              eyebrow="Workload"
              title="상태 분포"
              description="이슈 상태와 우선순위를 빠르게 봅니다."
            >
              <div className="grid gap-3">
                <div className="grid gap-2">
                  {dashboard?.status_counts.length ? (
                    dashboard.status_counts.map((item) => (
                      <div
                        key={item.status}
                        className="flex items-center justify-between gap-3 rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] px-3 py-2"
                      >
                        <span className="text-[0.82rem] text-[var(--ui-color-ink)]">
                          {item.label}
                        </span>
                        <strong className="text-[0.82rem] text-[var(--ui-color-ink)]">
                          {item.count}
                        </strong>
                      </div>
                    ))
                  ) : (
                    <InlineNotice tone="info">상태 데이터가 없습니다.</InlineNotice>
                  )}
                </div>
                <div className="grid gap-2 border-t border-[var(--ui-color-border)] pt-3">
                  {dashboard?.priority_counts.length ? (
                    dashboard.priority_counts.map((item) => (
                      <div
                        key={item.priority}
                        className="flex items-center justify-between gap-3 text-[0.8rem]"
                      >
                        <span className="text-[var(--ui-color-ink-subtle)]">{item.label}</span>
                        <strong className="text-[var(--ui-color-ink)]">{item.count}</strong>
                      </div>
                    ))
                  ) : (
                    <InlineNotice tone="info">우선순위 데이터가 없습니다.</InlineNotice>
                  )}
                </div>
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}
