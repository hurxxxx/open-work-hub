import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useSearchParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  Layout,
  Star,
  Lock,
  Settings,
  Plus,
  List as ListIcon,
  Grid,
  Calendar,
  Activity,
  Table,
  Loader2,
  Download,
  ChevronDown,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  getCurrentOrLastWorkspaceSlug,
  resolveDefaultWorkspaceAppPath,
} from '@/src/domains/workspaces/workspace-utils';
import {
  getPmsList,
  listPmsProjects,
  listSpaces,
  listProjectIssues,
  listProjectMembers,
  listProjectMilestones,
  listProjectLabels,
  listProjectStatuses,
  getIssueDetail,
  updateIssue,
  exportProjectCsv,
  type IssueFilterParams,
  type PmsList,
  type PmsIssue,
  type PmsProjectMember,
  type PmsSpace,
  type PmsMilestone,
  type PmsLabel,
  type PmsProjectStatus,
} from '@/src/domains/pms/pms-api';
import {
  createDefaultIssueFilterParams,
  reconcileSelectedIssueIds,
} from '@/src/domains/pms/pms-filters';

import { OverviewView } from './OverviewView';
import { ListView } from './ListView';
import { BoardView } from './BoardView';
import { CalendarView } from './CalendarView';
import { GanttView } from './GanttView';
import { TableView } from './TableView';
import { TaskDetail } from './TaskDetail';
import { NewTaskModal } from './NewTaskModal';
import { AssignedToMeView } from './AssignedToMeView';
import { TodayOverdueView } from './TodayOverdueView';
import { PersonalListView } from './PersonalListView';
import { ProjectSettingsPanel } from './ProjectSettingsPanel';
import { CreateSpaceModal } from './CreateSpaceModal';
import { FilterBar } from './FilterBar';
import { BulkActionBar } from './BulkActionBar';
import { SpaceDocsView } from './SpaceDocsView';
import { SpaceOverviewView } from './SpaceOverviewView';
import { projectRoleAllows } from '@/src/domains/pms/pms-permissions';

function isSameListCollection(left: PmsList[], right: PmsList[]): boolean {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((item, index) => {
    const other = right[index];
    return (
      item?.id === other?.id
      && item?.updated_at === other?.updated_at
      && item?.team_id === other?.team_id
      && item?.folder_id === other?.folder_id
    );
  });
}

export const PMSView = () => {
  const { toolId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { token, user } = useAuth();
  const pmsRoot = resolveDefaultWorkspaceAppPath(user, 'pms');
  const currentWorkspaceSlug = getCurrentOrLastWorkspaceSlug();
  const [activeTab, setActiveTab] = useState<'List' | 'Board' | 'Calendar' | 'Gantt' | 'Table'>('List');
  const [selectedIssue, setSelectedIssue] = useState<PmsIssue | null>(null);
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);

  const [projects, setProjects] = useState<PmsList[]>([]);
  const [spaces, setSpaces] = useState<PmsSpace[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [members, setMembers] = useState<PmsProjectMember[]>([]);
  const [milestones, setMilestones] = useState<PmsMilestone[]>([]);
  const [labels, setLabels] = useState<PmsLabel[]>([]);
  const [projectStatuses, setProjectStatuses] = useState<PmsProjectStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterParams, setFilterParams] = useState<IssueFilterParams>(createDefaultIssueFilterParams());
  const [selectedIssueIds, setSelectedIssueIds] = useState<Set<string>>(new Set());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [projectSwitcherOpen, setProjectSwitcherOpen] = useState(false);


  const projectSwitcherRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!projectSwitcherOpen) return;
    function onClick(e: MouseEvent) {
      if (projectSwitcherRef.current && !projectSwitcherRef.current.contains(e.target as Node)) {
        setProjectSwitcherOpen(false);
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [projectSwitcherOpen]);

  const isAssignedTasksView = toolId === 'pms-tasks' || toolId === 'pms-tasks-assigned';
  const isTodayView = toolId === 'pms-tasks-today';
  const isPersonalView = toolId === 'pms-tasks-personal';
  const routeProjectId = toolId?.startsWith('pms-list-')
    ? toolId.replace('pms-list-', '')
    : toolId?.startsWith('pms-project-')
      ? toolId.replace('pms-project-', '')
      : null;
  const spaceDocsMatch = toolId?.match(/^pms-space-([0-9a-f-]+)-docs(?:-([0-9a-f-]+))?$/);
  const spaceDocsSpaceId = spaceDocsMatch?.[1] ?? null;
  const spaceDocsDocId = spaceDocsMatch?.[2] ?? null;
  const spaceOverviewId = (toolId && /^pms-space-.+$/.test(toolId) && !spaceDocsMatch) ? toolId.replace('pms-space-', '') : null;
  const isOverviewRoute = !toolId;
  const selectedProject = projects.find(p => p.id === selectedProjectId);
  const projectName = selectedProject?.name || 'List';
  const canEditProject = projectRoleAllows(selectedProject?.role, 'member');
  const canManageProject = projectRoleAllows(selectedProject?.role, 'admin');
  const requestedIssueId = searchParams.get('issue');

  // Listen for the SubSidebar header "+" button (and any future quick-create
  // entry points) so they can pop the New Task modal without needing a
  // direct ref into this component. Only respond when a list is selected
  // and the user can edit it — otherwise the modal would mount without a
  // valid projectId.
  const newTaskTriggerRef = useRef<{ enabled: boolean }>({ enabled: false });
  newTaskTriggerRef.current.enabled = Boolean(selectedProjectId && canEditProject);
  useEffect(() => {
    const handler = () => {
      if (newTaskTriggerRef.current.enabled) setIsNewTaskModalOpen(true);
    };
    window.addEventListener('pms:create-task', handler);
    return () => window.removeEventListener('pms:create-task', handler);
  }, []);

  const getErrorMessage = useCallback(
    (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback),
    [],
  );

  const applyIssueCollection = useCallback((nextIssues: PmsIssue[]) => {
    setIssues(nextIssues);
    setSelectedIssueIds((current) => reconcileSelectedIssueIds(current, nextIssues));
    setSelectedIssue((current) => {
      if (!current) {
        return null;
      }

      return nextIssues.find((item) => item.id === current.id) ?? null;
    });
  }, []);

  const clearSelectedIssue = useCallback(() => {
    setSelectedIssue(null);
    if (!requestedIssueId) {
      return;
    }

    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('issue');
    setSearchParams(nextParams, { replace: true });
  }, [requestedIssueId, searchParams, setSearchParams]);

  // Keep project catalog in sync with the route so newly created projects open immediately.
  useEffect(() => {
    if (!token) return;
    const activeToken = token;
    let cancelled = false;

    async function loadProjects() {
      setLoading(true);
      setError(null);

      try {
        const [response, spaceItems] = await Promise.all([
          listPmsProjects(activeToken),
          listSpaces(activeToken),
        ]);
        if (cancelled) {
          return;
        }

        setSpaces(spaceItems);
        let nextProjects = response.items;
        let requestedProjectResolved = false;

        if (routeProjectId) {
          requestedProjectResolved = response.items.some((project) => project.id === routeProjectId);
          if (!requestedProjectResolved) {
            const requestedProject = await getPmsList(activeToken, routeProjectId);
            if (cancelled) {
              return;
            }
            nextProjects = [...response.items, requestedProject];
            requestedProjectResolved = true;
          }
        }

        setProjects((current) => (isSameListCollection(current, nextProjects) ? current : nextProjects));
        setSelectedProjectId((current) => {
          if (routeProjectId) {
            return requestedProjectResolved ? routeProjectId : '';
          }
          if (current && nextProjects.some((project) => project.id === current)) {
            return current;
          }
          return nextProjects[0]?.id || '';
        });
      } catch (err) {
        if (cancelled) {
          return;
        }
        setSelectedProjectId('');
        setError(getErrorMessage(err, '프로젝트를 불러오지 못했습니다.'));
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadProjects();

    return () => {
      cancelled = true;
    };
  }, [getErrorMessage, routeProjectId, token]);

  const reloadIssues = useCallback(async () => {
    if (!token || !selectedProjectId) return;

    try {
      setError(null);
      const res = await listProjectIssues(token, selectedProjectId, filterParams);
      applyIssueCollection(res.items);
    } catch (err) {
      setError(getErrorMessage(err, '이슈 목록을 불러오지 못했습니다.'));
    }
  }, [applyIssueCollection, getErrorMessage, filterParams, selectedProjectId, token]);

  // Load issues + members + milestones when project changes
  useEffect(() => {
    if (!token || !selectedProjectId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      listProjectIssues(token, selectedProjectId, filterParams),
      listProjectMembers(token, selectedProjectId),
      listProjectMilestones(token, selectedProjectId),
      listProjectLabels(token, selectedProjectId),
      listProjectStatuses(token, selectedProjectId),
    ])
      .then(([issueRes, memberRes, milestoneRes, labelRes, statusRes]) => {
        if (cancelled) return;
        applyIssueCollection(issueRes.items);
        setMembers(memberRes.items);
        setMilestones(milestoneRes.items);
        setLabels(labelRes.items);
        setProjectStatuses(statusRes.items);
      })
      .catch(err => {
        if (cancelled) return;
        setError(getErrorMessage(err, '프로젝트 데이터를 불러오지 못했습니다.'));
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [applyIssueCollection, getErrorMessage, token, selectedProjectId, filterParams]);

  const toggleIssueSelection = useCallback((issueId: string) => {
    setSelectedIssueIds(prev => {
      const next = new Set(prev);
      if (next.has(issueId)) next.delete(issueId);
      else next.add(issueId);
      return next;
    });
  }, []);

  const handleBulkDone = useCallback(async () => {
    setSelectedIssueIds(new Set());
    await reloadIssues();
  }, [reloadIssues]);

  const handleUpdateIssue = useCallback(
    async (issueId: string, payload: Record<string, unknown>) => {
      if (!token) return;
      const updatedIssue = await updateIssue(token, issueId, payload);
      applyIssueCollection(
        issues.map((item) => (item.id === updatedIssue.id ? updatedIssue : item)),
      );
      await reloadIssues();
    },
    [applyIssueCollection, issues, reloadIssues, token],
  );

  useEffect(() => {
    setActiveTab('List');
  }, [toolId]);

  useEffect(() => {
    setSelectedIssue((current) => {
      if (!current) {
        return null;
      }

      return current.list_id === selectedProjectId ? current : null;
    });
    setSelectedIssueIds(new Set());
    setFilterParams(createDefaultIssueFilterParams());
  }, [selectedProjectId]);

  useEffect(() => {
    if (!token || !requestedIssueId) {
      return;
    }

    let cancelled = false;
    setError(null);
    setActiveTab('List');
    setSelectedIssueIds(new Set());

    getIssueDetail(token, requestedIssueId)
      .then((detail) => {
        if (cancelled) {
          return;
        }

        setFilterParams(
          createDefaultIssueFilterParams({
            archived_state: detail.issue.archived ? 'archived' : 'active',
          }),
        );
        setSelectedProjectId(detail.issue.list_id);
        setSelectedIssue(detail.issue);
      })
      .catch((caughtError) => {
        if (cancelled) {
          return;
        }

        setError(getErrorMessage(caughtError, '요청한 이슈를 불러오지 못했습니다.'));
      });

    return () => {
      cancelled = true;
    };
  }, [getErrorMessage, requestedIssueId, token]);

  if (isAssignedTasksView) return <AssignedToMeView />;
  if (isTodayView) return <TodayOverdueView />;
  if (isPersonalView) return <PersonalListView />;
  if (spaceDocsSpaceId) {
    const spaceName = projects.find((project) => project.team_id === spaceDocsSpaceId)?.team_name ?? null;
    return <SpaceDocsView spaceId={spaceDocsSpaceId} spaceName={spaceName} docId={spaceDocsDocId} />;
  }
  if (spaceOverviewId) {
    const spaceName = projects.find((project) => project.team_id === spaceOverviewId)?.team_name ?? null;
    return <SpaceOverviewView spaceId={spaceOverviewId} spaceName={spaceName} />;
  }
  if (isOverviewRoute) {
    if (!loading && spaces.length === 0) {
      return (
        <>
          <div className="flex h-full items-center justify-center px-8">
            <div className="w-full max-w-xl rounded-2xl border border-app-border bg-app-surface p-8 text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-app-accent text-app-bg">
                <Layout size={22} />
              </div>
              <h1 className="app-text-title-lg text-app-ink">No Spaces Yet</h1>
              <p className="app-text-body mt-3 text-app-ink/60">
                PMS 앱 접근은 준비됐지만 아직 속한 스페이스가 없습니다. 새 스페이스를 만들고 바로 리스트와 문서를 운영할 수 있습니다.
              </p>
              <div className="mt-6 flex justify-center">
                <button
                  className="app-text-control-sm rounded-lg bg-app-accent px-4 py-2 text-app-bg transition-colors hover:bg-app-accent/90"
                  onClick={() => setCreateSpaceOpen(true)}
                  type="button"
                >
                  Create Space
                </button>
              </div>
            </div>
          </div>
          <CreateSpaceModal
            isOpen={createSpaceOpen}
            onClose={() => setCreateSpaceOpen(false)}
            onCreated={(space) => {
              setSpaces((current) => [space, ...current.filter((item) => item.id !== space.id)]);
              navigate(`/tool/pms-space-${space.id}`);
            }}
          />
        </>
      );
    }
    return (
      <div className="h-full flex flex-col relative">
        <header className="bg-app-bg border-b border-app-border px-8 pt-6 transition-colors">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-8 h-8 bg-app-accent rounded flex items-center justify-center text-app-bg">
              <Layout size={20} />
            </div>
            <div>
              <h1 className="app-text-title-lg text-app-ink">PMS Overview</h1>
              <div className="app-text-caption flex items-center gap-2 text-gray-500">
                <Lock size={10} />
                <span>Spaces, Lists and Docs</span>
              </div>
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <OverviewView />
        </main>
      </div>
    );
  }
  if (error && !loading && !selectedProjectId) {
    return (
      <div className="app-text-body flex h-full items-center justify-center text-red-400">
        {error}
      </div>
    );
  }
  if (!selectedProjectId && !loading) {
    return (
      <div className="app-text-body flex h-full items-center justify-center text-gray-500">
        No lists found.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-app-bg border-b border-app-border px-6 pt-3 transition-colors">
        {/* Row 1: breadcrumb */}
        <nav className="app-text-caption flex items-center gap-1.5 text-gray-500 mb-1.5 min-w-0">
          <Link to={currentWorkspaceSlug ? `/w/${encodeURIComponent(currentWorkspaceSlug)}/pms` : pmsRoot} className="hover:text-app-ink transition-colors shrink-0">PMS</Link>
          {selectedProject?.team_name ? (
            <>
              <span className="text-gray-600 shrink-0">/</span>
              <span className="truncate max-w-[160px]">{selectedProject.team_name}</span>
            </>
          ) : null}
          {selectedProject?.folder_name ? (
            <>
              <span className="text-gray-600 shrink-0">/</span>
              <span className="truncate max-w-[160px]">{selectedProject.folder_name}</span>
            </>
          ) : null}
        </nav>

        {/* Row 2: title + actions */}
        <div className="flex items-center justify-between gap-4 mb-3 min-w-0">
          <div className="flex items-center gap-2.5 flex-1 min-w-0">
            <div className="w-7 h-7 bg-app-accent rounded flex items-center justify-center text-app-bg shrink-0">
              <Layout size={16} />
            </div>
            <h1 className="app-text-title-md text-app-ink truncate min-w-0">
              {selectedProject?.name || projectName}
            </h1>
            <button
              type="button"
              className="shrink-0 text-gray-600 hover:text-yellow-500 transition-colors"
              title="Favorite"
            >
              <Star size={14} />
            </button>
            {projects.length > 1 && (
              <div ref={projectSwitcherRef} className="relative shrink-0">
                <button
                  type="button"
                  onClick={() => setProjectSwitcherOpen(o => !o)}
                  className="flex h-7 w-7 items-center justify-center rounded text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                  title="Switch list"
                >
                  <ChevronDown size={14} />
                </button>
                {projectSwitcherOpen && (
                  <div className="absolute top-full left-0 mt-1 z-30 min-w-[220px] max-h-72 overflow-y-auto custom-scrollbar bg-app-bg border border-app-border rounded-lg shadow-xl py-1">
                    {projects.map(p => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => {
                          setProjectSwitcherOpen(false);
                          clearSelectedIssue();
                          navigate(`/tool/pms-list-${p.id}`);
                        }}
                        className={cn(
                          'app-text-body-sm w-full px-3 py-1.5 text-left hover:bg-app-surface-hover truncate',
                          p.id === selectedProjectId ? 'text-app-accent font-medium' : 'text-app-ink'
                        )}
                      >
                        {p.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {selectedProjectId && (
              <button
                onClick={() => { if (token) void exportProjectCsv(token, selectedProjectId); }}
                className="flex h-8 w-8 items-center justify-center rounded text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                title="Export CSV"
              >
                <Download size={15} />
              </button>
            )}
            {canManageProject ? (
              <button
                onClick={() => setSettingsOpen(true)}
                className="flex h-8 w-8 items-center justify-center rounded text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                title="Settings"
              >
                <Settings size={15} />
              </button>
            ) : null}
            {canEditProject ? (
              <>
                <div className="w-px h-5 bg-app-border mx-1" />
                <button
                  onClick={() => setIsNewTaskModalOpen(true)}
                  className="app-text-body-sm flex h-8 items-center gap-1.5 rounded-md bg-app-accent px-3 font-semibold text-app-accent-fg shadow-sm"
                >
                  <Plus size={14} />
                  <span>New Task</span>
                </button>
              </>
            ) : null}
          </div>
        </div>

        <div className="flex items-center gap-6">
          {(['List', 'Board', 'Calendar', 'Gantt', 'Table'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as typeof activeTab)}
              className={cn(
                'app-text-body-sm relative pb-3 font-medium transition-all',
                activeTab === tab ? 'text-app-ink' : 'text-gray-500 hover:text-app-ink'
              )}
            >
              <div className="flex items-center gap-2">
                {tab === 'List' && <ListIcon size={14} />}
                {tab === 'Board' && <Grid size={14} />}
                {tab === 'Calendar' && <Calendar size={14} />}
                {tab === 'Gantt' && <Activity size={14} />}
                {tab === 'Table' && <Table size={14} />}
                {tab}
              </div>
              {activeTab === tab && (
                <motion.div layoutId="activeTab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-app-accent" />
              )}
            </button>
          ))}
          <button className="app-text-body-sm pb-3 text-gray-500 hover:text-gray-300">
            <Plus size={14} />
          </button>
        </div>
      </header>

      {selectedProjectId && (
        <FilterBar
          projectId={selectedProjectId}
          filterParams={filterParams}
          setFilterParams={setFilterParams}
          members={members}
          milestones={milestones}
          labels={labels}
          projectStatuses={projectStatuses}
        />
      )}

      <main className={cn(
        "flex-1 custom-scrollbar",
        "overflow-y-auto p-8"
      )}>
        {loading && issues.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 size={24} className="animate-spin text-app-accent" />
          </div>
        ) : error ? (
          <div className="app-text-body flex h-64 items-center justify-center text-red-400">{error}</div>
        ) : (
          <AnimatePresence mode="wait">
            {activeTab === 'List' && (
              <motion.div key="list" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <ListView issues={issues} onSelectIssue={setSelectedIssue} selectedIds={selectedIssueIds} onToggleSelect={toggleIssueSelection} projectStatuses={projectStatuses} />
              </motion.div>
            )}
            {activeTab === 'Board' && (
              <motion.div key="board" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <BoardView issues={issues} onSelectIssue={setSelectedIssue} onUpdateIssue={handleUpdateIssue} selectedIds={selectedIssueIds} onToggleSelect={toggleIssueSelection} projectStatuses={projectStatuses} />
              </motion.div>
            )}
            {activeTab === 'Calendar' && (
              <motion.div key="calendar" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <CalendarView issues={issues} projectStatuses={projectStatuses} />
              </motion.div>
            )}
            {activeTab === 'Gantt' && (
              <motion.div key="gantt" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <GanttView issues={issues} projectStatuses={projectStatuses} />
              </motion.div>
            )}
            {activeTab === 'Table' && (
              <motion.div key="table" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <TableView issues={issues} onSelectIssue={setSelectedIssue} selectedIds={selectedIssueIds} onToggleSelect={toggleIssueSelection} projectStatuses={projectStatuses} />
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </main>

      {/* Task detail — full-size modal overlay (ClickUp style) */}
      <AnimatePresence>
        {selectedIssue && (
          <motion.div
            key="task-modal"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-stretch"
          >
            <div className="absolute inset-0 bg-black/40" onClick={clearSelectedIssue} />
            <motion.div
              initial={{ y: 30, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 30, opacity: 0 }}
              transition={{ type: 'spring', damping: 28, stiffness: 350 }}
              className="relative z-10 my-6 mx-auto w-[80%] bg-app-bg border border-app-border rounded-xl shadow-2xl overflow-hidden flex flex-col"
            >
              <TaskDetail
                issue={selectedIssue}
                members={members}
                milestones={milestones}
                projectLabels={labels}
                projectStatuses={projectStatuses}
                spaceName={selectedProject?.team_name}
                canEdit={canEditProject}
                onClose={clearSelectedIssue}
                onUpdate={reloadIssues}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isNewTaskModalOpen && (
          <NewTaskModal
            isOpen={isNewTaskModalOpen}
            onClose={() => setIsNewTaskModalOpen(false)}
            projectId={selectedProjectId}
            onCreated={reloadIssues}
            projectStatuses={projectStatuses}
            canCreate={canEditProject}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {settingsOpen && selectedProjectId && (
          <ProjectSettingsPanel
            projectId={selectedProjectId}
            teamId={selectedProject?.team_id ?? null}
            currentUserRole={selectedProject?.role ?? null}
            onClose={() => setSettingsOpen(false)}
            onLabelsChanged={(updated) => setLabels(updated)}
            onStatusesChanged={(updated) => setProjectStatuses(updated)}
          />
        )}
      </AnimatePresence>

      {selectedIssueIds.size > 0 && selectedProjectId && (
        <BulkActionBar
          projectId={selectedProjectId}
          selectedIds={selectedIssueIds}
          totalCount={issues.length}
          onSelectAll={() => setSelectedIssueIds(new Set(issues.map(i => i.id)))}
          onDeselectAll={() => setSelectedIssueIds(new Set())}
          onDone={handleBulkDone}
          members={members}
          labels={labels}
          projectStatuses={projectStatuses}
        />
      )}

      <CreateSpaceModal
        isOpen={createSpaceOpen}
        onClose={() => setCreateSpaceOpen(false)}
        onCreated={(space) => {
          setSpaces((current) => [space, ...current.filter((item) => item.id !== space.id)]);
          navigate(`/tool/pms-space-${space.id}`);
        }}
      />
    </div>
  );
};
