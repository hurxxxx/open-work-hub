import { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useSearchParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  Layout,
  FolderKanban,
  Star,
  Lock,
  Search,
  Settings,
  Plus,
  List as ListIcon,
  Grid,
  Calendar,
  Activity,
  Table,
  Loader2,
  Download,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  listPmsProjects,
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
import { FilterBar } from './FilterBar';
import { BulkActionBar } from './BulkActionBar';
import { SpaceDocsView } from './SpaceDocsView';
import { SpaceOverviewView } from './SpaceOverviewView';

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

const PROJECT_ROLE_RANK: Record<string, number> = {
  viewer: 0,
  member: 1,
  editor: 2,
  admin: 3,
  owner: 4,
};

function projectRoleAllows(role: string | null | undefined, minRole: keyof typeof PROJECT_ROLE_RANK): boolean {
  if (!role) {
    return false;
  }

  return (PROJECT_ROLE_RANK[role] ?? -1) >= PROJECT_ROLE_RANK[minRole];
}

export const PMSView = () => {
  const { toolId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState<'List' | 'Board' | 'Calendar' | 'Gantt' | 'Table'>('List');
  const [selectedIssue, setSelectedIssue] = useState<PmsIssue | null>(null);
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);

  const [projects, setProjects] = useState<PmsList[]>([]);
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
  const isOverviewRoute = !toolId || toolId === 'pms-space-team';
  const selectedProject = projects.find(p => p.id === selectedProjectId);
  const projectName = selectedProject?.name || 'List';
  const canEditProject = projectRoleAllows(selectedProject?.role, 'member');
  const canManageProject = projectRoleAllows(selectedProject?.role, 'admin');
  const requestedIssueId = searchParams.get('issue');

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
    let cancelled = false;
    setLoading(true);
    setError(null);
    listPmsProjects(token)
      .then(res => {
        if (cancelled) return;
        setProjects((current) => (isSameListCollection(current, res.items) ? current : res.items));
        setSelectedProjectId((current) => {
          if (routeProjectId && res.items.some((project) => project.id === routeProjectId)) {
            return current === routeProjectId ? current : routeProjectId;
          }
          if (current && res.items.some((project) => project.id === current)) {
            return current;
          }
          return res.items[0]?.id || '';
        });
      })
      .catch(err => {
        if (cancelled) return;
        setError(getErrorMessage(err, '프로젝트를 불러오지 못했습니다.'));
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

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

      return current.project_id === selectedProjectId ? current : null;
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
        setSelectedProjectId(detail.issue.project_id);
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
    return (
      <div className="h-full flex flex-col relative">
        <header className="bg-clickup-bg border-b border-clickup-border px-8 pt-6 transition-colors">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-8 h-8 bg-clickup-purple rounded flex items-center justify-center text-white">
              <Layout size={20} />
            </div>
            <div>
              <h1 className="app-text-title-lg text-clickup-text">PMS Overview</h1>
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
  if (!selectedProjectId && !loading) {
    return (
      <div className="app-text-body flex h-full items-center justify-center text-gray-500">
        No lists found.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-clickup-bg border-b border-clickup-border px-8 pt-6 transition-colors">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-clickup-purple rounded flex items-center justify-center text-white">
              <Layout size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <Link to="/pms" className="app-text-title-lg text-gray-500 transition-colors hover:text-clickup-text">PMS</Link>
                {selectedProject?.team_name ? (
                  <>
                    <span className="app-text-title-md text-gray-400">/</span>
                    <span className="app-text-title-lg text-gray-500">{selectedProject.team_name}</span>
                  </>
                ) : null}
                <span className="app-text-title-md text-gray-400">/</span>
                <h1 className="app-text-title-lg flex items-center gap-2 text-clickup-text">
                  <FolderKanban size={18} className="text-blue-400" />
                  {selectedProject?.name || projectName}
                  <Star size={16} className="text-gray-600 cursor-pointer hover:text-yellow-500 ml-2" />
                </h1>
              </div>
              <div className="app-text-caption flex items-center gap-2 text-gray-500">
                <Lock size={10} />
                <span>{selectedProject?.folder_name ? `Folder: ${selectedProject.folder_name}` : 'Root List'}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Project Selector */}
            {projects.length > 1 && (
              <select
                value={selectedProjectId}
                onChange={e => {
                  clearSelectedIssue();
                  navigate(`/tool/pms-list-${e.target.value}`);
                }}
                className="app-text-body-sm min-h-10 rounded-md border border-clickup-border bg-clickup-sidebar px-3 text-clickup-text focus:border-clickup-purple focus:outline-none"
              >
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            )}
            <div className="app-text-body-sm flex min-h-10 items-center gap-2 rounded-md border border-clickup-border bg-clickup-sidebar px-3 text-clickup-text">
              <Search size={14} className="text-gray-500" />
              <input
                type="text"
                placeholder="Search..."
                value={filterParams.q ?? ''}
                onChange={e => setFilterParams(prev => ({ ...prev, q: e.target.value || undefined }))}
                className="w-32 bg-transparent text-inherit focus:outline-none"
              />
            </div>
            {selectedProjectId && (
              <button
                onClick={() => { if (token) void exportProjectCsv(token, selectedProjectId); }}
                className="flex h-10 w-10 items-center justify-center rounded border border-clickup-border text-gray-500 transition-colors hover:bg-clickup-hover dark:text-gray-400"
                title="Export CSV"
              >
                <Download size={16} />
              </button>
            )}
            {canManageProject ? (
              <button
                onClick={() => setSettingsOpen(true)}
                className="flex h-10 w-10 items-center justify-center rounded border border-clickup-border text-gray-500 transition-colors hover:bg-clickup-hover dark:text-gray-400"
              >
                <Settings size={16} />
              </button>
            ) : null}
            {canEditProject ? (
              <button
                onClick={() => setIsNewTaskModalOpen(true)}
                className="app-text-body-sm flex min-h-10 items-center gap-2 rounded-md bg-clickup-purple px-4 font-semibold text-white shadow-lg shadow-purple-500/20"
              >
                <Plus size={16} />
                <span>New Task</span>
              </button>
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
                activeTab === tab ? 'text-clickup-text' : 'text-gray-500 hover:text-clickup-text'
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
                <motion.div layoutId="activeTab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-clickup-purple" />
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
            <Loader2 size={24} className="animate-spin text-clickup-purple" />
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
              className="relative z-10 my-6 mx-auto w-[80%] bg-clickup-bg border border-clickup-border rounded-xl shadow-2xl overflow-hidden flex flex-col"
            >
              <TaskDetail
                issue={selectedIssue}
                members={members}
                milestones={milestones}
                projectLabels={labels}
                projectStatuses={projectStatuses}
                spaceName={selectedProject?.team_name}
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
    </div>
  );
};
