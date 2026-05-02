import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, Link, useSearchParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'motion/react';
import {
  Layout,
  Star,
  Lock,
  Settings,
  Plus,
  PencilRuler,
  List as ListIcon,
  Grid,
  Calendar,
  Activity,
  Table,
  Loader2,
  Download,
  ChevronDown,
  MoreHorizontal,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  getWorkspaceBySlug,
  getCurrentOrLastWorkspaceSlug,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import {
  getPmsTaskList,
  listPmsTaskLists,
  listSpaces,
  listSpaceMembers,
  listTaskListIssues,
  listTaskListMilestones,
  listTaskListLabels,
  listTaskListStatuses,
  getIssueDetail,
  updateIssue,
  exportTaskListCsv,
  type IssueFilterParams,
  type PmsTaskList,
  type PmsIssue,
  type PmsTaskListMember,
  type PmsSpace,
  type PmsMilestone,
  type PmsLabel,
  type PmsTaskListStatus,
} from '../api/pms-api';
import {
  createDefaultIssueFilterParams,
  reconcileSelectedIssueIds,
} from '../api/pms-filters';

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
import { TaskListSettingsPanel } from './TaskListSettingsPanel';
import { CreateSpaceModal } from './CreateSpaceModal';
import { FilterBar } from './FilterBar';
import { BulkActionBar } from './BulkActionBar';
import { SpaceDocsView } from './SpaceDocsView';
import { SpaceWhiteboardsView } from './SpaceWhiteboardsView';
import { SpaceOverviewView } from './SpaceOverviewView';
import { taskListRoleAllows } from '../api/pms-permissions';
import { WhiteboardContextSlotPanel } from '@/src/app-modules/whiteboard/public-api';

type PmsViewTab = 'List' | 'Board' | 'Calendar' | 'Gantt' | 'Table' | 'Whiteboard';

const PMS_VIEW_TAB_LABEL_KEYS: Record<PmsViewTab, string> = {
  List: 'pms.viewTabs.list',
  Board: 'pms.viewTabs.board',
  Calendar: 'pms.viewTabs.calendar',
  Gantt: 'pms.viewTabs.gantt',
  Table: 'pms.viewTabs.table',
  Whiteboard: 'pms.viewTabs.whiteboard',
};

function isSameListCollection(left: PmsTaskList[], right: PmsTaskList[]): boolean {
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
  const { t } = useTranslation('apps');
  const { toolId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { token, user } = useAuth();
  const pmsRoot = resolveDefaultWorkspaceAppPath(user, 'pms');
  const currentWorkspaceSlug = getWorkspaceBySlug(user, searchParams.get('workspace'))?.slug
    ?? getCurrentOrLastWorkspaceSlug();
  const [activeTab, setActiveTab] = useState<PmsViewTab>('List');
  const [selectedIssue, setSelectedIssue] = useState<PmsIssue | null>(null);
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);

  const [taskLists, setTaskLists] = useState<PmsTaskList[]>([]);
  const [spaces, setSpaces] = useState<PmsSpace[]>([]);
  const [selectedTaskListId, setSelectedTaskListId] = useState<string>('');
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [members, setMembers] = useState<PmsTaskListMember[]>([]);
  const [milestones, setMilestones] = useState<PmsMilestone[]>([]);
  const [labels, setLabels] = useState<PmsLabel[]>([]);
  const [taskListStatuses, setTaskListStatuses] = useState<PmsTaskListStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterParams, setFilterParams] = useState<IssueFilterParams>(createDefaultIssueFilterParams());
  const [selectedIssueIds, setSelectedIssueIds] = useState<Set<string>>(new Set());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [taskListSwitcherOpen, setTaskListSwitcherOpen] = useState(false);
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);


  const taskListSwitcherRef = useRef<HTMLDivElement>(null);
  const mobileMoreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!taskListSwitcherOpen) return;
    function onClick(e: MouseEvent) {
      if (taskListSwitcherRef.current && !taskListSwitcherRef.current.contains(e.target as Node)) {
        setTaskListSwitcherOpen(false);
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [taskListSwitcherOpen]);

  useEffect(() => {
    if (!mobileMoreOpen) return;
    function onClick(e: MouseEvent) {
      if (mobileMoreRef.current && !mobileMoreRef.current.contains(e.target as Node)) {
        setMobileMoreOpen(false);
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [mobileMoreOpen]);

  const createTaskRequested = searchParams.get('create') === '1';
  const isAssignedTasksView = toolId === 'pms-tasks' || toolId === 'pms-tasks-assigned';
  const isTodayView = toolId === 'pms-tasks-today';
  const isPersonalView = toolId === 'pms-tasks-personal';
  const routeTaskListId = toolId?.startsWith('pms-list-')
    ? toolId.replace('pms-list-', '')
    : null;
  const spaceDocsMatch = toolId?.match(/^pms-space-([0-9a-f-]+)-docs(?:-([0-9a-f-]+))?$/);
  const spaceDocsSpaceId = spaceDocsMatch?.[1] ?? null;
  const spaceDocsDocId = spaceDocsMatch?.[2] ?? null;
  const spaceWhiteboardsMatch = toolId?.match(/^pms-space-([0-9a-f-]+)-whiteboards(?:-([0-9a-f-]+))?$/);
  const spaceWhiteboardsSpaceId = spaceWhiteboardsMatch?.[1] ?? null;
  const spaceWhiteboardsWhiteboardId = spaceWhiteboardsMatch?.[2] ?? null;
  const spaceOverviewId = (
    toolId
    && /^pms-space-.+$/.test(toolId)
    && !spaceDocsMatch
    && !spaceWhiteboardsMatch
  ) ? toolId.replace('pms-space-', '') : null;
  const isOverviewRoute = !toolId && !createTaskRequested && !isNewTaskModalOpen;
  const selectedTaskList = taskLists.find((taskList) => taskList.id === selectedTaskListId);
  const taskListName = selectedTaskList?.name || 'List';
  const canEditTaskList = taskListRoleAllows(selectedTaskList?.role, 'member');
  const canManageTaskList = taskListRoleAllows(selectedTaskList?.role, 'admin');
  const requestedIssueId = searchParams.get('issue');
  const selectedTaskListWhiteboardContext = useMemo(
    () => (selectedTaskListId ? { app: 'pms', type: 'task_list', id: selectedTaskListId } : null),
    [selectedTaskListId],
  );
  const viewTabs = ['List', 'Board', 'Calendar', 'Gantt', 'Table', 'Whiteboard'] as const satisfies readonly PmsViewTab[];
  const mobilePrimaryTabs = ['List', 'Board', 'Calendar'] as const satisfies readonly PmsViewTab[];
  const mobileMoreTabs = ['Gantt', 'Table', 'Whiteboard'] as const satisfies readonly PmsViewTab[];
  const mobileMoreActive = mobileMoreTabs.includes(activeTab as (typeof mobileMoreTabs)[number]);

  const selectViewTab = (tab: typeof activeTab) => {
    setActiveTab(tab);
    setMobileMoreOpen(false);
    const nextParams = new URLSearchParams(searchParams);
    if (tab === 'Whiteboard') {
      nextParams.set('tab', 'whiteboard');
    } else {
      nextParams.delete('tab');
    }
    setSearchParams(nextParams, { replace: true });
  };

  useEffect(() => {
    if (searchParams.get('tab') === 'whiteboard') {
      setActiveTab('Whiteboard');
    }
  }, [searchParams]);

  // Listen for the SubSidebar header "+" button (and any future quick-create
  // entry points) so they can pop the New Task modal without needing a
  // direct ref into this component. Only respond when a list is selected
  // and the user can edit it — otherwise the modal would mount without a
  // valid taskListId.
  const newTaskTriggerRef = useRef<{ enabled: boolean }>({ enabled: false });
  newTaskTriggerRef.current.enabled = Boolean(selectedTaskListId && canEditTaskList);
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

  // Keep the task list catalog in sync with the route so newly created lists open immediately.
  useEffect(() => {
    if (!token) return;
    const activeToken = token;
    let cancelled = false;

    async function loadTaskLists() {
      setLoading(true);
      setError(null);

      try {
        const [response, spaceItems] = await Promise.all([
          listPmsTaskLists(activeToken, undefined, currentWorkspaceSlug),
          listSpaces(activeToken, currentWorkspaceSlug),
        ]);
        if (cancelled) {
          return;
        }

        setSpaces(spaceItems);
        let nextTaskLists = response.items;
        let requestedTaskListResolved = false;

        if (routeTaskListId) {
          requestedTaskListResolved = response.items.some((taskList) => taskList.id === routeTaskListId);
          if (!requestedTaskListResolved) {
            const requestedTaskList = await getPmsTaskList(activeToken, routeTaskListId);
            if (cancelled) {
              return;
            }
            nextTaskLists = [...response.items, requestedTaskList];
            requestedTaskListResolved = true;
          }
        }

        setTaskLists((current) => (isSameListCollection(current, nextTaskLists) ? current : nextTaskLists));
        setSelectedTaskListId((current) => {
          if (routeTaskListId) {
            return requestedTaskListResolved ? routeTaskListId : '';
          }
          if (createTaskRequested) {
            if (
              current
              && nextTaskLists.some(
                (taskList) => taskList.id === current && taskListRoleAllows(taskList.role, 'member'),
              )
            ) {
              return current;
            }
            return nextTaskLists.find((taskList) => taskListRoleAllows(taskList.role, 'member'))?.id ?? '';
          }
          if (current && nextTaskLists.some((taskList) => taskList.id === current)) {
            return current;
          }
          return nextTaskLists[0]?.id || '';
        });
      } catch (err) {
        if (cancelled) {
          return;
        }
        setSelectedTaskListId('');
        setError(getErrorMessage(err, t('pms.errors.listLoadFailed')));
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadTaskLists();

    return () => {
      cancelled = true;
    };
  }, [createTaskRequested, currentWorkspaceSlug, getErrorMessage, routeTaskListId, token]);

  const reloadIssues = useCallback(async () => {
    if (!token || !selectedTaskListId) return;

    try {
      setError(null);
      const res = await listTaskListIssues(token, selectedTaskListId, filterParams);
      applyIssueCollection(res.items);
    } catch (err) {
      setError(getErrorMessage(err, t('pms.errors.issueLoadFailed')));
    }
  }, [applyIssueCollection, getErrorMessage, filterParams, selectedTaskListId, token]);

  // Load issues, members, milestones, labels, and statuses when the selected list changes.
  useEffect(() => {
    if (!token || !selectedTaskListId) return;
    let cancelled = false;
    const selectedList = taskLists.find((taskList) => taskList.id === selectedTaskListId);
    const selectedSpaceId = selectedList?.team_id;
    setLoading(true);
    setError(null);
    Promise.all([
      listTaskListIssues(token, selectedTaskListId, filterParams),
      selectedSpaceId
        ? listSpaceMembers(token, selectedSpaceId, currentWorkspaceSlug)
        : Promise.resolve({ items: [], total: 0, page: 1, page_size: 20 }),
      listTaskListMilestones(token, selectedTaskListId),
      listTaskListLabels(token, selectedTaskListId),
      listTaskListStatuses(token, selectedTaskListId),
    ])
      .then(([issueRes, memberRes, milestoneRes, labelRes, statusRes]) => {
        if (cancelled) return;
        applyIssueCollection(issueRes.items);
        setMembers(memberRes.items);
        setMilestones(milestoneRes.items);
        setLabels(labelRes.items);
        setTaskListStatuses(statusRes.items);
      })
      .catch(err => {
        if (cancelled) return;
        setError(getErrorMessage(err, t('pms.errors.listDataFailed')));
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [applyIssueCollection, currentWorkspaceSlug, getErrorMessage, taskLists, token, selectedTaskListId, filterParams]);

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

      return current.list_id === selectedTaskListId ? current : null;
    });
    setSelectedIssueIds(new Set());
    setFilterParams(createDefaultIssueFilterParams());
  }, [selectedTaskListId]);

  useEffect(() => {
    if (!token || !requestedIssueId) {
      return;
    }

    let cancelled = false;
    setError(null);
    setActiveTab('List');
    setSelectedIssueIds(new Set());

    getIssueDetail(token, requestedIssueId, currentWorkspaceSlug)
      .then((detail) => {
        if (cancelled) {
          return;
        }

        setFilterParams(
          createDefaultIssueFilterParams({
            archived_state: detail.issue.archived ? 'archived' : 'active',
          }),
        );
        setSelectedTaskListId(detail.issue.list_id);
        setSelectedIssue(detail.issue);
      })
      .catch((caughtError) => {
        if (cancelled) {
          return;
        }

        setError(getErrorMessage(caughtError, t('pms.errors.requestedIssueFailed')));
      });

    return () => {
      cancelled = true;
    };
  }, [currentWorkspaceSlug, getErrorMessage, requestedIssueId, token]);

  useEffect(() => {
    if (!createTaskRequested || loading) {
      return;
    }

    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('create');

    if (!selectedTaskListId || !canEditTaskList) {
      setError(t('pms.errors.createTaskNoList'));
      setSearchParams(nextParams, { replace: true });
      return;
    }

    setIsNewTaskModalOpen(true);
    setSearchParams(nextParams, { replace: true });
  }, [canEditTaskList, createTaskRequested, loading, searchParams, selectedTaskListId, setSearchParams]);

  if (isAssignedTasksView) return <AssignedToMeView />;
  if (isTodayView) return <TodayOverdueView />;
  if (isPersonalView) return <PersonalListView />;
  if (spaceDocsSpaceId) {
    const spaceName = taskLists.find((taskList) => taskList.team_id === spaceDocsSpaceId)?.team_name ?? null;
    return <SpaceDocsView spaceId={spaceDocsSpaceId} spaceName={spaceName} docId={spaceDocsDocId} />;
  }
  if (spaceWhiteboardsSpaceId) {
    const spaceName = taskLists.find((taskList) => taskList.team_id === spaceWhiteboardsSpaceId)?.team_name ?? null;
    return (
      <SpaceWhiteboardsView
        spaceId={spaceWhiteboardsSpaceId}
        spaceName={spaceName}
        whiteboardId={spaceWhiteboardsWhiteboardId}
      />
    );
  }
  if (spaceOverviewId) {
    const spaceName = taskLists.find((taskList) => taskList.team_id === spaceOverviewId)?.team_name ?? null;
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
              <h1 className="app-text-title-lg text-app-ink">{t('pms.noSpacesTitle')}</h1>
              <p className="app-text-body mt-3 text-app-ink/60">
                {t('pms.noSpacesDescription')}
              </p>
              <div className="mt-6 flex justify-center">
                <button
                  className="app-text-control-sm rounded-lg bg-app-accent px-4 py-2 text-app-bg transition-colors hover:bg-app-accent/90"
                  onClick={() => setCreateSpaceOpen(true)}
                  type="button"
                >
                  {t('pms.createSpace')}
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
              <h1 className="app-text-title-lg text-app-ink">{t('pms.overview')}</h1>
              <div className="app-text-caption flex items-center gap-2 text-gray-500">
                <Lock size={10} />
                <span>{t('pms.spacesListsDocs')}</span>
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
  if (error && !loading && !selectedTaskListId) {
    return (
      <div className="app-text-body flex h-full items-center justify-center text-red-400">
        {error}
      </div>
    );
  }
  if (!selectedTaskListId && !loading) {
    return (
      <div className="app-text-body flex h-full items-center justify-center text-gray-500">
        No lists found.
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-w-0 flex-col">
      <header className="border-b border-app-border bg-app-bg px-4 pt-4 transition-colors lg:px-6 lg:pt-3">
        {/* Row 1: breadcrumb */}
        <nav className="app-text-caption mb-1.5 hidden min-w-0 items-center gap-1.5 text-gray-500 lg:flex">
          <Link to={currentWorkspaceSlug ? `/w/${encodeURIComponent(currentWorkspaceSlug)}/pms` : pmsRoot} className="hover:text-app-ink transition-colors shrink-0">PMS</Link>
          {selectedTaskList?.team_name ? (
            <>
              <span className="text-gray-600 shrink-0">/</span>
              <span className="truncate max-w-[160px]">{selectedTaskList.team_name}</span>
            </>
          ) : null}
          {selectedTaskList?.folder_name ? (
            <>
              <span className="text-gray-600 shrink-0">/</span>
              <span className="truncate max-w-[160px]">{selectedTaskList.folder_name}</span>
            </>
          ) : null}
        </nav>

        {/* Row 2: title + actions */}
        <div className="mb-3 flex min-w-0 items-start justify-between gap-3 lg:items-center lg:gap-4">
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-app-accent text-app-bg lg:h-7 lg:w-7">
              <Layout size={16} />
            </div>
            <div className="min-w-0">
              <h1 className="app-text-title-md min-w-0 truncate text-app-ink">
                {selectedTaskList?.name || taskListName}
              </h1>
              {selectedTaskList?.team_name ? (
                <p className="app-text-caption mt-0.5 truncate text-app-ink/45 lg:hidden">
                  {selectedTaskList.team_name}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              className="shrink-0 text-gray-600 hover:text-yellow-500 transition-colors"
              title={t('pms.actions.favorite')}
            >
              <Star size={14} />
            </button>
            {taskLists.length > 1 && (
              <div ref={taskListSwitcherRef} className="relative shrink-0">
                <button
                  type="button"
                  onClick={() => setTaskListSwitcherOpen((open) => !open)}
                  className="flex h-7 w-7 items-center justify-center rounded text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                  title={t('pms.actions.switchList')}
                >
                  <ChevronDown size={14} />
                </button>
                {taskListSwitcherOpen && (
                  <div className="absolute top-full left-0 mt-1 z-30 min-w-[220px] max-h-72 overflow-y-auto custom-scrollbar bg-app-bg border border-app-border rounded-lg shadow-xl py-1">
                    {taskLists.map((taskList) => (
                      <button
                        key={taskList.id}
                        type="button"
                        onClick={() => {
                          setTaskListSwitcherOpen(false);
                          clearSelectedIssue();
                          navigate(`/tool/pms-list-${taskList.id}`);
                        }}
                        className={cn(
                          'app-text-body-sm w-full px-3 py-1.5 text-left hover:bg-app-surface-hover truncate',
                          taskList.id === selectedTaskListId ? 'text-app-accent font-medium' : 'text-app-ink'
                        )}
                      >
                        {taskList.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {selectedTaskListId && (
              <button
                onClick={() => { if (token) void exportTaskListCsv(token, selectedTaskListId); }}
                className="flex h-8 w-8 items-center justify-center rounded text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                title={t('pms.actions.exportCsv')}
              >
                <Download size={15} />
              </button>
            )}
            {canManageTaskList ? (
              <button
                onClick={() => setSettingsOpen(true)}
                className="flex h-8 w-8 items-center justify-center rounded text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                title={t('pms.actions.settings')}
              >
                <Settings size={15} />
              </button>
            ) : null}
            {canEditTaskList ? (
              <>
                <div className="w-px h-5 bg-app-border mx-1" />
                <button
                  onClick={() => setIsNewTaskModalOpen(true)}
                  className="app-text-body-sm flex h-9 w-9 items-center justify-center gap-1.5 rounded-md bg-app-accent font-semibold text-app-accent-fg shadow-sm sm:w-auto sm:px-3 lg:h-8"
                  aria-label={t('pms.newTask')}
                >
                  <Plus size={14} />
                  <span className="hidden sm:inline">{t('pms.newTask')}</span>
                </button>
              </>
            ) : null}
          </div>
        </div>

        <div className="hidden items-center gap-6 lg:flex">
          {viewTabs.map(tab => (
            <button
              key={tab}
              onClick={() => selectViewTab(tab)}
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
                {tab === 'Whiteboard' && <PencilRuler size={14} />}
                {t(PMS_VIEW_TAB_LABEL_KEYS[tab])}
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

        <div className="flex items-center gap-1 pb-3 lg:hidden">
          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
            {mobilePrimaryTabs.map(tab => (
              <button
                key={tab}
                onClick={() => selectViewTab(tab)}
                className={cn(
                  'app-text-control-sm flex shrink-0 items-center gap-1.5 rounded-md border px-3 py-2 transition-colors',
                  activeTab === tab
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover hover:text-app-ink',
                )}
              >
                {tab === 'List' && <ListIcon size={14} />}
                {tab === 'Board' && <Grid size={14} />}
                {tab === 'Calendar' && <Calendar size={14} />}
                {t(PMS_VIEW_TAB_LABEL_KEYS[tab])}
              </button>
            ))}
          </div>

          <div ref={mobileMoreRef} className="relative shrink-0">
            <button
              type="button"
              onClick={() => setMobileMoreOpen((open) => !open)}
              className={cn(
                'app-text-control-sm flex items-center gap-1.5 rounded-md border px-3 py-2 transition-colors',
                mobileMoreActive
                  ? 'border-app-accent bg-app-accent/10 text-app-accent'
                  : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover hover:text-app-ink',
              )}
            >
              <MoreHorizontal size={14} />
              {t('pms.actions.more')}
            </button>
            {mobileMoreOpen ? (
              <div className="absolute right-0 top-full z-30 mt-1 w-44 rounded-lg border border-app-border bg-app-bg py-1 shadow-xl">
                {mobileMoreTabs.map(tab => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => selectViewTab(tab)}
                    className={cn(
                      'app-text-body-sm flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-app-surface-hover',
                      activeTab === tab ? 'text-app-accent' : 'text-app-ink',
                    )}
                  >
                    {tab === 'Gantt' && <Activity size={14} />}
                    {tab === 'Table' && <Table size={14} />}
                    {tab === 'Whiteboard' && <PencilRuler size={14} />}
                    {t(PMS_VIEW_TAB_LABEL_KEYS[tab])}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {selectedTaskListId && activeTab !== 'Whiteboard' && (
        <FilterBar
          taskListId={selectedTaskListId}
          filterParams={filterParams}
          setFilterParams={setFilterParams}
          members={members}
          milestones={milestones}
          labels={labels}
          taskListStatuses={taskListStatuses}
        />
      )}

      <main className={cn(
        'flex-1 custom-scrollbar',
        activeTab === 'Whiteboard' ? 'overflow-hidden p-2 lg:p-4' : 'overflow-y-auto p-4 lg:p-8',
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
                <ListView issues={issues} onSelectIssue={setSelectedIssue} selectedIds={selectedIssueIds} onToggleSelect={toggleIssueSelection} taskListStatuses={taskListStatuses} />
              </motion.div>
            )}
            {activeTab === 'Board' && (
              <motion.div key="board" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <BoardView issues={issues} onSelectIssue={setSelectedIssue} onUpdateIssue={handleUpdateIssue} selectedIds={selectedIssueIds} onToggleSelect={toggleIssueSelection} taskListStatuses={taskListStatuses} />
              </motion.div>
            )}
            {activeTab === 'Calendar' && (
              <motion.div key="calendar" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <CalendarView issues={issues} taskListStatuses={taskListStatuses} />
              </motion.div>
            )}
            {activeTab === 'Gantt' && (
              <motion.div key="gantt" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <GanttView issues={issues} taskListStatuses={taskListStatuses} />
              </motion.div>
            )}
            {activeTab === 'Table' && (
              <motion.div key="table" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <TableView issues={issues} onSelectIssue={setSelectedIssue} selectedIds={selectedIssueIds} onToggleSelect={toggleIssueSelection} taskListStatuses={taskListStatuses} />
              </motion.div>
            )}
            {activeTab === 'Whiteboard' && selectedTaskListWhiteboardContext && (
              <motion.div key="whiteboard" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="flex h-full min-h-0">
                <WhiteboardContextSlotPanel
                  context={selectedTaskListWhiteboardContext}
                  workspaceSlug={currentWorkspaceSlug}
                  defaultTitle={`${taskListName} Whiteboard`}
                  canEditContext={canEditTaskList}
                  className="min-h-[calc(100vh-220px)] w-full overflow-hidden"
                  editorClassName="min-h-[calc(100vh-220px)]"
                />
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
              className="relative z-10 flex h-full w-full flex-col overflow-hidden border-app-border bg-app-bg shadow-2xl lg:my-6 lg:mx-auto lg:h-auto lg:w-[80%] lg:rounded-xl lg:border"
            >
              <TaskDetail
                issue={selectedIssue}
                members={members}
                milestones={milestones}
                taskListLabels={labels}
                taskListStatuses={taskListStatuses}
                spaceName={selectedTaskList?.team_name}
                canEdit={canEditTaskList}
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
            taskListId={selectedTaskListId}
            onCreated={reloadIssues}
            taskListStatuses={taskListStatuses}
            canCreate={canEditTaskList}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {settingsOpen && selectedTaskListId && (
          <TaskListSettingsPanel
            taskListId={selectedTaskListId}
            teamId={selectedTaskList?.team_id ?? null}
            currentUserRole={selectedTaskList?.role ?? null}
            onClose={() => setSettingsOpen(false)}
            onLabelsChanged={(updated) => setLabels(updated)}
            onStatusesChanged={(updated) => setTaskListStatuses(updated)}
          />
        )}
      </AnimatePresence>

      {selectedIssueIds.size > 0 && selectedTaskListId && (
        <BulkActionBar
          taskListId={selectedTaskListId}
          selectedIds={selectedIssueIds}
          totalCount={issues.length}
          onSelectAll={() => setSelectedIssueIds(new Set(issues.map(i => i.id)))}
          onDeselectAll={() => setSelectedIssueIds(new Set())}
          onDone={handleBulkDone}
          members={members}
          labels={labels}
          taskListStatuses={taskListStatuses}
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
