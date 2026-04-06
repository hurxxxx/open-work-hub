import {
  Button,
  DataTable,
  DataTableToolbar,
  DetailDrawer,
  EmptyState,
  FilterBar,
  InlineNotice,
  Input,
  MetricInline,
  Panel,
  SearchField,
  Select,
  StatusBadge,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  type DataTableColumn,
  useToast,
} from '@aidoo/ui';
import { useEffect, useMemo, useState } from 'react';

import {
  createIssueComment,
  createPmsProject,
  createProjectIssue,
  createProjectMilestone,
  getIssueDetail,
  getPmsDashboardSummary,
  listIssueActivityLogs,
  listPmsProjects,
  listProjectIssues,
  listProjectMembers,
  listProjectMilestones,
  updateIssue,
  type PmsActivityLog,
  type PmsDashboardSummary,
  type PmsIssue,
  type PmsIssueDetail,
  type PmsMilestone,
  type PmsProject,
  type PmsProjectMember,
} from './pms-api';

const ISSUE_COLUMNS: DataTableColumn<PmsIssue>[] = [
  {
    accessorKey: 'reference',
    header: 'Issue',
    cell: ({ row }) => (
      <div className="grid gap-1">
        <strong className="text-sm">{row.original.reference}</strong>
        <span className="text-[0.94rem] font-semibold text-[var(--ui-color-ink)]">
          {row.original.title}
        </span>
        <small className="text-[0.82rem] text-[var(--ui-color-ink-subtle)]">
          {row.original.description || '설명 없음'}
        </small>
      </div>
    ),
  },
  { accessorKey: 'status_label', header: 'Status' },
  { accessorKey: 'priority_label', header: 'Priority' },
  { accessorKey: 'assignee_name', header: 'Assignee' },
  {
    accessorKey: 'due_date',
    header: 'Due',
    cell: ({ row }) => row.original.due_date ?? '미정',
  },
];

const BOARD_STATUSES = [
  { id: 'backlog', label: 'Backlog' },
  { id: 'todo', label: 'Todo' },
  { id: 'in_progress', label: 'In Progress' },
  { id: 'done', label: 'Done' },
] as const;
const UNASSIGNED_VALUE = '__unassigned__';
const NO_MILESTONE_VALUE = '__no_milestone__';

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string | null) {
  return value ?? '미정';
}

function isMobileViewport() {
  return typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function'
    ? window.matchMedia('(max-width: 720px)').matches
    : false;
}

export interface PmsWorkspaceProps {
  token: string;
}

export function PmsWorkspace({ token }: PmsWorkspaceProps) {
  const toast = useToast();
  const [dashboard, setDashboard] = useState<PmsDashboardSummary | null>(null);
  const [projects, setProjects] = useState<PmsProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [members, setMembers] = useState<PmsProjectMember[]>([]);
  const [milestones, setMilestones] = useState<PmsMilestone[]>([]);
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
  const [selectedIssueDetail, setSelectedIssueDetail] = useState<PmsIssueDetail | null>(null);
  const [activityLogs, setActivityLogs] = useState<PmsActivityLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [projectLoading, setProjectLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issueSearch, setIssueSearch] = useState('');
  const [submittedIssueSearch, setSubmittedIssueSearch] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [mobileIssueOpen, setMobileIssueOpen] = useState(false);
  const [projectForm, setProjectForm] = useState({
    key: '',
    name: '',
    description: '',
  });
  const [issueForm, setIssueForm] = useState({
    title: '',
    description: '',
    status: 'backlog',
    priority: 'medium',
    assignee_id: UNASSIGNED_VALUE,
    milestone_id: NO_MILESTONE_VALUE,
    due_date: '',
  });
  const [milestoneForm, setMilestoneForm] = useState({
    title: '',
    description: '',
    status: 'planned',
    due_date: '',
  });
  const [commentDraft, setCommentDraft] = useState('');
  const [issueEditor, setIssueEditor] = useState({
    status: 'backlog',
    priority: 'medium',
    assignee_id: UNASSIGNED_VALUE,
    milestone_id: NO_MILESTONE_VALUE,
  });

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );

  async function loadOverview(preferredProjectId?: string) {
    setLoading(true);
    setError(null);
    try {
      const [dashboardState, projectsState] = await Promise.all([
        getPmsDashboardSummary(token),
        listPmsProjects(token),
      ]);
      setDashboard(dashboardState);
      setProjects(projectsState.items);
      const nextProjectId =
        preferredProjectId && projectsState.items.some((item) => item.id === preferredProjectId)
          ? preferredProjectId
          : projectsState.items[0]?.id ?? '';
      setSelectedProjectId(nextProjectId);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'PMS 개요를 불러오지 못했습니다.',
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadProject(projectId: string) {
    if (!projectId) {
      setMembers([]);
      setMilestones([]);
      setIssues([]);
      return;
    }

    setProjectLoading(true);
    setError(null);
    try {
      const [membersState, milestonesState, issuesState] = await Promise.all([
        listProjectMembers(token, projectId),
        listProjectMilestones(token, projectId),
        listProjectIssues(token, projectId, {
          q: submittedIssueSearch,
          priority: priorityFilter,
          status: statusFilter === 'all' ? [] : [statusFilter],
        }),
      ]);
      setMembers(membersState.items);
      setMilestones(milestonesState.items);
      setIssues(issuesState.items);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : '프로젝트 상세 데이터를 불러오지 못했습니다.',
      );
    } finally {
      setProjectLoading(false);
    }
  }

  async function loadIssue(issueId: string) {
    try {
      const [detail, logs] = await Promise.all([
        getIssueDetail(token, issueId),
        listIssueActivityLogs(token, issueId),
      ]);
      setSelectedIssueDetail(detail);
      setActivityLogs(logs.items);
      setIssueEditor({
        status: detail.issue.status,
        priority: detail.issue.priority,
        assignee_id: detail.issue.assignee_id ?? UNASSIGNED_VALUE,
        milestone_id: detail.issue.milestone_id ?? NO_MILESTONE_VALUE,
      });
    } catch (caughtError) {
      toast.error(
        'Issue load failed',
        caughtError instanceof Error ? caughtError.message : '이슈 상세를 불러오지 못했습니다.',
      );
    }
  }

  useEffect(() => {
    void loadOverview();
  }, [token]);

  useEffect(() => {
    void loadProject(selectedProjectId);
  }, [priorityFilter, selectedProjectId, statusFilter, submittedIssueSearch, token]);

  useEffect(() => {
    if (!selectedIssueId) {
      setSelectedIssueDetail(null);
      setActivityLogs([]);
      return;
    }
    void loadIssue(selectedIssueId);
  }, [selectedIssueId, token]);

  useEffect(() => {
    if (!selectedIssueId || !issues.some((issue) => issue.id === selectedIssueId)) {
      setSelectedIssueId(null);
      setSelectedIssueDetail(null);
      setActivityLogs([]);
      setMobileIssueOpen(false);
    }
  }, [issues, selectedIssueId]);

  async function refreshCurrentProject() {
    await Promise.all([
      loadOverview(selectedProjectId),
      selectedProjectId ? loadProject(selectedProjectId) : Promise.resolve(),
      selectedIssueId ? loadIssue(selectedIssueId) : Promise.resolve(),
    ]);
  }

  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const nextProject = await createPmsProject(token, {
        key: projectForm.key.trim(),
        name: projectForm.name.trim(),
        description: projectForm.description.trim(),
      });
      setProjectForm({ key: '', name: '', description: '' });
      toast.success('Project created', `${nextProject.name} 프로젝트를 만들었습니다.`);
      await loadOverview(nextProject.id);
    } catch (caughtError) {
      toast.error(
        'Create failed',
        caughtError instanceof Error ? caughtError.message : '프로젝트를 만들지 못했습니다.',
      );
    }
  }

  async function handleCreateIssue(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) {
      return;
    }
    try {
      const nextIssue = await createProjectIssue(token, selectedProjectId, {
        title: issueForm.title.trim(),
        description: issueForm.description.trim(),
        status: issueForm.status,
        priority: issueForm.priority,
        assignee_id:
          issueForm.assignee_id === UNASSIGNED_VALUE ? null : issueForm.assignee_id,
        milestone_id:
          issueForm.milestone_id === NO_MILESTONE_VALUE ? null : issueForm.milestone_id,
        due_date: issueForm.due_date || null,
      });
      setIssueForm({
        title: '',
        description: '',
        status: 'backlog',
        priority: 'medium',
        assignee_id: UNASSIGNED_VALUE,
        milestone_id: NO_MILESTONE_VALUE,
        due_date: '',
      });
      setSelectedIssueId(nextIssue.id);
      toast.success('Issue created', `${nextIssue.reference} 이슈를 만들었습니다.`);
      await refreshCurrentProject();
    } catch (caughtError) {
      toast.error(
        'Create failed',
        caughtError instanceof Error ? caughtError.message : '이슈를 만들지 못했습니다.',
      );
    }
  }

  async function handleCreateMilestone(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) {
      return;
    }
    try {
      await createProjectMilestone(token, selectedProjectId, {
        title: milestoneForm.title.trim(),
        description: milestoneForm.description.trim(),
        status: milestoneForm.status,
        due_date: milestoneForm.due_date || null,
      });
      setMilestoneForm({
        title: '',
        description: '',
        status: 'planned',
        due_date: '',
      });
      toast.success('Milestone created', '마일스톤을 추가했습니다.');
      await refreshCurrentProject();
    } catch (caughtError) {
      toast.error(
        'Create failed',
        caughtError instanceof Error ? caughtError.message : '마일스톤을 만들지 못했습니다.',
      );
    }
  }

  async function handleMoveIssue(issue: PmsIssue, nextStatus: string) {
    try {
      const boardPosition =
        issues.filter((candidate) => candidate.status === nextStatus).length + 1;
      await updateIssue(token, issue.id, {
        status: nextStatus,
        board_position: boardPosition,
      });
      toast.info(
        'Board updated',
        `${issue.reference} 상태를 ${BOARD_STATUSES.find((item) => item.id === nextStatus)?.label ?? nextStatus}(으)로 옮겼습니다.`,
      );
      await refreshCurrentProject();
    } catch (caughtError) {
      toast.error(
        'Move failed',
        caughtError instanceof Error ? caughtError.message : '보드 상태를 바꾸지 못했습니다.',
      );
    }
  }

  async function handleSaveIssueEditor() {
    if (!selectedIssueDetail) {
      return;
    }
    try {
      await updateIssue(token, selectedIssueDetail.issue.id, {
        status: issueEditor.status,
        priority: issueEditor.priority,
        assignee_id:
          issueEditor.assignee_id === UNASSIGNED_VALUE ? null : issueEditor.assignee_id,
        milestone_id:
          issueEditor.milestone_id === NO_MILESTONE_VALUE ? null : issueEditor.milestone_id,
      });
      toast.success('Issue updated', '상태와 담당 정보를 반영했습니다.');
      await refreshCurrentProject();
    } catch (caughtError) {
      toast.error(
        'Update failed',
        caughtError instanceof Error ? caughtError.message : '이슈를 갱신하지 못했습니다.',
      );
    }
  }

  async function handleCommentSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedIssueId || !commentDraft.trim()) {
      return;
    }
    try {
      await createIssueComment(token, selectedIssueId, commentDraft.trim());
      setCommentDraft('');
      toast.success('Comment added', '댓글을 저장했습니다.');
      await refreshCurrentProject();
    } catch (caughtError) {
      toast.error(
        'Comment failed',
        caughtError instanceof Error ? caughtError.message : '댓글을 저장하지 못했습니다.',
      );
    }
  }

  const boardGroups = BOARD_STATUSES.map((column) => ({
    ...column,
    items: issues
      .filter((issue) => issue.status === column.id)
      .sort((left, right) => left.board_position - right.board_position),
  }));
  const showOverviewStrip = Boolean(
    dashboard &&
      (dashboard.project_count ||
        dashboard.active_issue_count ||
        dashboard.overdue_issue_count ||
        dashboard.my_issue_count ||
        dashboard.milestone_due_soon_count),
  );
  const showRightRail = Boolean(selectedProject);
  const workspaceGridClass = showRightRail
    ? 'grid gap-3 xl:grid-cols-[250px_minmax(0,1fr)_280px]'
    : 'grid gap-3 xl:grid-cols-[250px_minmax(0,1fr)]';

  if (loading) {
    return (
      <Panel eyebrow="PMS" title="프로젝트 관리 도구" description="대시보드를 불러오는 중입니다.">
        <InlineNotice tone="info">프로젝트, 마일스톤, 이슈 데이터를 준비하는 중입니다.</InlineNotice>
      </Panel>
    );
  }

  const issueDetailBody = selectedIssueDetail ? (
    <div className="grid gap-4">
      <Panel
        eyebrow={selectedIssueDetail.issue.reference}
        title={selectedIssueDetail.issue.title}
        description={selectedIssueDetail.issue.description || '설명 없음'}
      >
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Select
              value={issueEditor.status}
              onValueChange={(value) => setIssueEditor((current) => ({ ...current, status: value }))}
              options={BOARD_STATUSES.map((item) => ({ value: item.id, label: item.label }))}
            />
            <Select
              value={issueEditor.priority}
              onValueChange={(value) =>
                setIssueEditor((current) => ({ ...current, priority: value }))
              }
              options={[
                { value: 'low', label: 'Low' },
                { value: 'medium', label: 'Medium' },
                { value: 'high', label: 'High' },
                { value: 'critical', label: 'Critical' },
              ]}
            />
            <Select
              value={issueEditor.assignee_id}
              onValueChange={(value) =>
                setIssueEditor((current) => ({ ...current, assignee_id: value }))
              }
              options={[
                { value: UNASSIGNED_VALUE, label: '미배정' },
                ...members.map((member) => ({
                  value: member.user_id,
                  label: member.full_name,
                })),
              ]}
            />
            <Select
              value={issueEditor.milestone_id}
              onValueChange={(value) =>
                setIssueEditor((current) => ({ ...current, milestone_id: value }))
              }
              options={[
                { value: NO_MILESTONE_VALUE, label: '마일스톤 없음' },
                ...milestones.map((milestone) => ({
                  value: milestone.id,
                  label: milestone.title,
                })),
              ]}
            />
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            <MetricInline
              label="Assignee"
              value={selectedIssueDetail.issue.assignee_name ?? '미배정'}
            />
            <MetricInline label="Due" value={formatDate(selectedIssueDetail.issue.due_date)} />
            <MetricInline
              label="Milestone"
              value={selectedIssueDetail.issue.milestone_title ?? '없음'}
            />
          </div>
          <Button variant="primary" onClick={() => void handleSaveIssueEditor()}>
            이슈 갱신
          </Button>
        </div>
      </Panel>
      <Panel eyebrow="Comments" title="댓글" description="작업 히스토리와 협업 메모를 남깁니다.">
        <div className="grid gap-3">
          {selectedIssueDetail.comments.length ? (
            selectedIssueDetail.comments.map((comment) => (
              <article
                key={comment.id}
                className="grid gap-1 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-white px-4 py-3"
              >
                <strong className="text-sm">{comment.author_name}</strong>
                <p className="text-sm text-[var(--ui-color-ink)]">{comment.body}</p>
                <small className="text-[0.78rem] text-[var(--ui-color-ink-subtle)]">
                  {comment.created_at}
                </small>
              </article>
            ))
          ) : (
            <InlineNotice tone="info">아직 댓글이 없습니다.</InlineNotice>
          )}
          <form className="grid gap-2" onSubmit={(event) => void handleCommentSubmit(event)}>
            <textarea
              className="min-h-24 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border-strong)] bg-white px-4 py-3 text-sm outline-none"
              value={commentDraft}
              onChange={(event) => setCommentDraft(event.target.value)}
              placeholder="진행 메모나 결정 사항을 남기세요."
            />
            <Button type="submit" variant="secondary">
              댓글 추가
            </Button>
          </form>
        </div>
      </Panel>
      <Panel eyebrow="Activity" title="활동 로그" description="상태와 필드 변경 내역입니다.">
        <div className="grid gap-2">
          {activityLogs.length ? (
            activityLogs.map((log) => (
              <div
                key={log.id}
                className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-white px-4 py-3 text-sm"
              >
                <strong className="block text-[var(--ui-color-ink)]">{log.message}</strong>
                <small className="text-[var(--ui-color-ink-subtle)]">{log.created_at}</small>
              </div>
            ))
          ) : (
            <InlineNotice tone="info">기록된 활동 로그가 없습니다.</InlineNotice>
          )}
        </div>
      </Panel>
    </div>
  ) : (
    <EmptyState
      title="이슈를 선택하세요"
      description="보드 카드나 리스트 행을 눌러 상세와 활동 로그를 확인합니다."
    />
  );

  return (
    <>
      <div className="grid gap-3">
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

        {showOverviewStrip ? (
          <section className="grid gap-3 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] px-3 py-2 lg:grid-cols-5">
            <MetricInline label="Projects" value={String(dashboard?.project_count ?? 0)} />
            <MetricInline
              label="Active issues"
              value={String(dashboard?.active_issue_count ?? 0)}
            />
            <MetricInline label="Overdue" value={String(dashboard?.overdue_issue_count ?? 0)} />
            <MetricInline label="My issues" value={String(dashboard?.my_issue_count ?? 0)} />
            <MetricInline
              label="Milestones due soon"
              value={String(dashboard?.milestone_due_soon_count ?? 0)}
            />
          </section>
        ) : null}

        <div className={workspaceGridClass}>
          <div className="grid content-start gap-3">
            <Panel
              eyebrow="Projects"
              title="프로젝트"
              description="실행 중인 프로젝트를 선택합니다."
            >
              <div className="grid gap-2.5">
                {projects.length ? (
                  projects.map((project) => (
                    <button
                      key={project.id}
                      type="button"
                      className={`grid gap-1 rounded-[var(--ui-radius-md)] border px-3 py-2.5 text-left ${
                        project.id === selectedProjectId
                          ? 'border-[var(--ui-color-accent)] bg-[var(--ui-color-accent-weak)]'
                          : 'border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)]'
                      }`}
                      onClick={() => setSelectedProjectId(project.id)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <strong className="text-[0.84rem]">{project.key}</strong>
                        <span className="text-[0.76rem] text-[var(--ui-color-ink-subtle)]">
                          {formatPercent(project.progress)}
                        </span>
                      </div>
                      <span className="text-[0.88rem] font-semibold">{project.name}</span>
                      <small className="text-[0.76rem] text-[var(--ui-color-ink-subtle)]">
                        Open {project.issue_count} · Overdue {project.overdue_issue_count}
                      </small>
                    </button>
                  ))
                ) : (
                  <div className="rounded-[var(--ui-radius-md)] border border-dashed border-[var(--ui-color-border-strong)] bg-[var(--ui-color-surface-subtle)] px-3 py-4 text-center">
                    <strong className="block text-[0.94rem] text-[var(--ui-color-ink)]">
                      프로젝트가 없습니다
                    </strong>
                    <small className="mt-1 block text-[0.8rem] text-[var(--ui-color-ink-muted)]">
                      첫 프로젝트를 만들면 보드가 바로 열립니다.
                    </small>
                  </div>
                )}

                <div className="mt-1 border-t border-t-[var(--ui-color-border)] pt-3">
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
                          setProjectForm((current) => ({
                            ...current,
                            name: event.target.value,
                          }))
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
                    <Button type="submit" variant="secondary">
                      프로젝트 만들기
                    </Button>
                  </form>
                </div>
              </div>
            </Panel>

            {showRightRail ? (
              <Panel
                eyebrow="Members"
                title="멤버"
                description="현재 프로젝트의 접근 주체입니다."
              >
                {members.length ? (
                  <div className="grid gap-2">
                    {members.map((member) => (
                      <div
                        key={member.user_id}
                        className="flex items-center justify-between gap-3 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] px-3 py-2"
                      >
                        <div className="grid gap-0.5">
                          <strong className="text-[0.84rem]">{member.full_name}</strong>
                          <small className="text-[0.74rem] text-[var(--ui-color-ink-subtle)]">
                            {member.email}
                          </small>
                        </div>
                        <StatusBadge>{member.role}</StatusBadge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <InlineNotice tone="info">프로젝트 멤버가 아직 없습니다.</InlineNotice>
                )}
              </Panel>
            ) : null}
          </div>

          <div className="grid content-start gap-3">
            {selectedProject ? (
              <Panel
                eyebrow={selectedProject.key}
                title={selectedProject.name}
                description={selectedProject.description || '프로젝트 설명이 아직 없습니다.'}
                status={<StatusBadge>{selectedProject.role}</StatusBadge>}
              >
                <div className="grid gap-4">
                  <div className="grid gap-3 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] px-3 py-3 md:grid-cols-4">
                    <MetricInline label="Progress" value={formatPercent(selectedProject.progress)} />
                    <MetricInline label="Issues" value={String(selectedProject.issue_count)} />
                    <MetricInline
                      label="Milestones"
                      value={String(selectedProject.milestone_count)}
                    />
                    <MetricInline
                      label="Overdue"
                      value={String(selectedProject.overdue_issue_count)}
                    />
                  </div>

                  <div className="flex flex-col gap-2.5 border-b border-b-[var(--ui-color-border)] pb-3 lg:flex-row lg:items-center lg:justify-between">
                    <form
                      className="flex flex-col gap-2 sm:flex-row sm:items-center"
                      onSubmit={(event) => {
                        event.preventDefault();
                        setSubmittedIssueSearch(issueSearch.trim());
                      }}
                    >
                      <SearchField
                        aria-label="PMS issues search"
                        className="sm:min-w-[260px]"
                        value={issueSearch}
                        onChange={(event) => setIssueSearch(event.target.value)}
                        shortcut="⌘/"
                      />
                      <Button type="submit" variant="secondary">
                        필터 적용
                      </Button>
                    </form>
                    <div className="flex flex-wrap gap-2">
                      <Select
                        value={priorityFilter}
                        onValueChange={setPriorityFilter}
                        options={[
                          { value: 'all', label: 'All priorities' },
                          { value: 'low', label: 'Low' },
                          { value: 'medium', label: 'Medium' },
                          { value: 'high', label: 'High' },
                          { value: 'critical', label: 'Critical' },
                        ]}
                      />
                      <Select
                        value={statusFilter}
                        onValueChange={setStatusFilter}
                        options={[
                          { value: 'all', label: 'All status' },
                          ...BOARD_STATUSES.map((status) => ({
                            value: status.id,
                            label: status.label,
                          })),
                        ]}
                      />
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setPriorityFilter('all');
                          setStatusFilter('all');
                          setIssueSearch('');
                          setSubmittedIssueSearch('');
                        }}
                      >
                        초기화
                      </Button>
                    </div>
                  </div>

                  <details className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)]">
                    <summary className="cursor-pointer list-none px-3 py-2 text-[0.84rem] font-semibold text-[var(--ui-color-ink)]">
                      새 이슈 만들기
                    </summary>
                    <form
                      className="grid gap-2 border-t border-t-[var(--ui-color-border)] px-3 py-3"
                      onSubmit={(event) => void handleCreateIssue(event)}
                    >
                      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_120px_120px]">
                        <Input
                          value={issueForm.title}
                          onChange={(event) =>
                            setIssueForm((current) => ({
                              ...current,
                              title: event.target.value,
                            }))
                          }
                          placeholder="이슈 제목"
                        />
                        <Select
                          value={issueForm.status}
                          onValueChange={(value) =>
                            setIssueForm((current) => ({ ...current, status: value }))
                          }
                          options={BOARD_STATUSES.map((status) => ({
                            value: status.id,
                            label: status.label,
                          }))}
                        />
                        <Select
                          value={issueForm.priority}
                          onValueChange={(value) =>
                            setIssueForm((current) => ({ ...current, priority: value }))
                          }
                          options={[
                            { value: 'low', label: 'Low' },
                            { value: 'medium', label: 'Medium' },
                            { value: 'high', label: 'High' },
                            { value: 'critical', label: 'Critical' },
                          ]}
                        />
                      </div>
                      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_180px_180px_140px]">
                        <Input
                          value={issueForm.description}
                          onChange={(event) =>
                            setIssueForm((current) => ({
                              ...current,
                              description: event.target.value,
                            }))
                          }
                          placeholder="간단 설명"
                        />
                        <Select
                          value={issueForm.assignee_id}
                          onValueChange={(value) =>
                            setIssueForm((current) => ({ ...current, assignee_id: value }))
                          }
                          options={[
                            { value: UNASSIGNED_VALUE, label: '미배정' },
                            ...members.map((member) => ({
                              value: member.user_id,
                              label: member.full_name,
                            })),
                          ]}
                        />
                        <Select
                          value={issueForm.milestone_id}
                          onValueChange={(value) =>
                            setIssueForm((current) => ({ ...current, milestone_id: value }))
                          }
                          options={[
                            { value: NO_MILESTONE_VALUE, label: '마일스톤 없음' },
                            ...milestones.map((milestone) => ({
                              value: milestone.id,
                              label: milestone.title,
                            })),
                          ]}
                        />
                        <Input
                          type="date"
                          value={issueForm.due_date}
                          onChange={(event) =>
                            setIssueForm((current) => ({
                              ...current,
                              due_date: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="flex justify-end">
                        <Button type="submit" variant="primary">
                          이슈 만들기
                        </Button>
                      </div>
                    </form>
                  </details>

                  <Tabs defaultValue="board">
                    <TabsList>
                      <TabsTrigger value="board">Board</TabsTrigger>
                      <TabsTrigger value="list">List</TabsTrigger>
                    </TabsList>

                    <TabsContent value="board">
                      <div className="grid gap-3 xl:grid-cols-4">
                        {boardGroups.map((column) => (
                          <section
                            key={column.id}
                            className="grid min-h-[280px] gap-2 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] p-2.5"
                            onDragOver={(event) => event.preventDefault()}
                            onDrop={(event) => {
                              event.preventDefault();
                              const issueId = event.dataTransfer.getData('text/plain');
                              const issue = issues.find((candidate) => candidate.id === issueId);
                              if (issue) {
                                void handleMoveIssue(issue, column.id);
                              }
                            }}
                          >
                            <div className="flex items-center justify-between gap-2 border-b border-b-[var(--ui-color-border)] pb-2">
                              <strong className="text-[0.84rem]">{column.label}</strong>
                              <StatusBadge>{column.items.length}</StatusBadge>
                            </div>
                            {column.items.length ? (
                              column.items.map((issue) => (
                                <article
                                  key={issue.id}
                                  draggable
                                  className="grid cursor-pointer gap-1.5 rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-white px-3 py-2.5"
                                  onDragStart={(event) =>
                                    event.dataTransfer.setData('text/plain', issue.id)
                                  }
                                  onClick={() => {
                                    setSelectedIssueId(issue.id);
                                    if (isMobileViewport()) {
                                      setMobileIssueOpen(true);
                                    }
                                  }}
                                >
                                  <div className="flex items-center justify-between gap-2">
                                    <strong className="text-[0.78rem]">{issue.reference}</strong>
                                    <span className="text-[0.68rem] text-[var(--ui-color-ink-subtle)]">
                                      {issue.priority_label}
                                    </span>
                                  </div>
                                  <span className="text-[0.86rem] font-semibold">{issue.title}</span>
                                  <small className="text-[0.74rem] text-[var(--ui-color-ink-subtle)]">
                                    {issue.assignee_name ?? '미배정'} · Due {formatDate(issue.due_date)}
                                  </small>
                                </article>
                              ))
                            ) : (
                              <InlineNotice tone="info">이 컬럼의 이슈가 없습니다.</InlineNotice>
                            )}
                          </section>
                        ))}
                      </div>
                    </TabsContent>

                    <TabsContent value="list">
                      <DataTableToolbar
                        title="전체 이슈"
                        meta={`${issues.length} issues · ${projectLoading ? 'syncing' : 'live'}`}
                      />
                      <DataTable
                        columns={ISSUE_COLUMNS}
                        rows={issues}
                        loading={projectLoading}
                        selection={{
                          selectedRowId: selectedIssueId ?? undefined,
                          onRowClick: (issue) => {
                            setSelectedIssueId(issue.id);
                            if (isMobileViewport()) {
                              setMobileIssueOpen(true);
                            }
                          },
                          getRowId: (issue) => issue.id,
                        }}
                        emptyState={
                          <EmptyState
                            title="이슈가 없습니다"
                            description="새 이슈를 만들거나 필터를 완화해보세요."
                          />
                        }
                      />
                    </TabsContent>
                  </Tabs>
                </div>
              </Panel>
            ) : (
              <section className="grid gap-2 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] px-4 py-3">
                <p className="m-0 text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                  PMS
                </p>
                <h2 className="m-0 text-[0.96rem] font-semibold text-[var(--ui-color-ink)]">
                  시작하려면 프로젝트를 만드세요
                </h2>
                <p className="m-0 text-[0.8rem] text-[var(--ui-color-ink-muted)]">
                  좌측 패널에서 프로젝트를 만들면 보드, 마일스톤, 최근 활동이 작업면에 열립니다.
                </p>
                <div className="grid gap-1.5 border-t border-[var(--ui-color-border)] pt-2 text-[0.8rem] text-[var(--ui-color-ink-muted)]">
                  <span>1. 프로젝트 키와 이름을 입력합니다.</span>
                  <span>2. 프로젝트를 만든 뒤 이슈 보드를 엽니다.</span>
                  <span>3. 마일스톤과 담당자를 붙여 운영을 시작합니다.</span>
                </div>
              </section>
            )}
          </div>

          {showRightRail ? (
            <div className="grid content-start gap-3">
              <Panel
                eyebrow="Milestones"
                title="마일스톤"
                description="일정 기준 데이터와 진행률을 관리합니다."
              >
                <div className="grid gap-3">
                  <form className="grid gap-2" onSubmit={(event) => void handleCreateMilestone(event)}>
                    <Input
                      value={milestoneForm.title}
                      onChange={(event) =>
                        setMilestoneForm((current) => ({
                          ...current,
                          title: event.target.value,
                        }))
                      }
                      placeholder="마일스톤 제목"
                    />
                    <div className="grid gap-2 sm:grid-cols-2">
                      <Select
                        value={milestoneForm.status}
                        onValueChange={(value) =>
                          setMilestoneForm((current) => ({
                            ...current,
                            status: value,
                          }))
                        }
                        options={[
                          { value: 'planned', label: 'Planned' },
                          { value: 'active', label: 'Active' },
                          { value: 'complete', label: 'Complete' },
                        ]}
                      />
                      <Input
                        type="date"
                        value={milestoneForm.due_date}
                        onChange={(event) =>
                          setMilestoneForm((current) => ({
                            ...current,
                            due_date: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <Input
                      value={milestoneForm.description}
                      onChange={(event) =>
                        setMilestoneForm((current) => ({
                          ...current,
                          description: event.target.value,
                        }))
                      }
                      placeholder="설명"
                    />
                    <Button type="submit" variant="secondary">
                      마일스톤 추가
                    </Button>
                  </form>
                  {milestones.length ? (
                    <div className="grid gap-2">
                      {milestones.map((milestone) => (
                        <article
                          key={milestone.id}
                          className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] px-3 py-2.5"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <strong className="text-[0.84rem]">{milestone.title}</strong>
                            <StatusBadge>{formatPercent(milestone.progress)}</StatusBadge>
                          </div>
                          <small className="block text-[0.74rem] text-[var(--ui-color-ink-subtle)]">
                            Due {formatDate(milestone.due_date)} · {milestone.issue_count} issues
                          </small>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <InlineNotice tone="info">등록된 마일스톤이 없습니다.</InlineNotice>
                  )}
                </div>
              </Panel>

              <Panel
                eyebrow="Recent activity"
                title="최근 업데이트"
                description="최근 변경 로그를 빠르게 훑습니다."
              >
                {dashboard?.recent_activity.length ? (
                  <div className="grid gap-2">
                    {dashboard.recent_activity.map((activity) => (
                      <div
                        key={activity.id}
                        className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] px-3 py-2.5"
                      >
                        <strong className="block text-[0.82rem]">{activity.issue_reference}</strong>
                        <p className="text-[0.82rem] text-[var(--ui-color-ink)]">{activity.message}</p>
                        <small className="text-[0.72rem] text-[var(--ui-color-ink-subtle)]">
                          {activity.created_at}
                        </small>
                      </div>
                    ))}
                  </div>
                ) : (
                  <InlineNotice tone="info">표시할 활동 로그가 없습니다.</InlineNotice>
                )}
              </Panel>
            </div>
          ) : null}
        </div>
      </div>

      {isMobileViewport() ? (
        mobileIssueOpen ? (
          <Panel
            className="mt-5"
            eyebrow="Issue detail"
            title={selectedIssueDetail?.issue.reference ?? 'Issue detail'}
            description="모바일에서는 전체 폭 상세 패널로 이슈를 엽니다."
            actions={
              <Button variant="secondary" onClick={() => setMobileIssueOpen(false)}>
                닫기
              </Button>
            }
          >
            {issueDetailBody}
          </Panel>
        ) : null
      ) : (
        <DetailDrawer
          open={Boolean(selectedIssueId)}
          onOpenChange={(open) => {
            if (!open) {
              setSelectedIssueId(null);
            }
          }}
          title={selectedIssueDetail?.issue.reference ?? 'Issue detail'}
          description={selectedIssueDetail?.issue.title ?? '이슈를 선택하세요.'}
        >
          {issueDetailBody}
        </DetailDrawer>
      )}
    </>
  );
}
