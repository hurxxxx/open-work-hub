import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { useConfirm } from '@open-work-hub/ui/feedback/confirm-dialog';
import { usePrompt } from '@open-work-hub/ui/feedback/prompt-dialog';
import {
  ArrowUpDown,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  FolderKanban,
  Layout,
  List as ListIcon,
  MoreHorizontal,
  Plus,
  Star,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { teamRoleAllows } from '@/src/platform/auth/auth-api';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import {
  listDocsHub,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';
import {
  deleteSpace,
  listFolders,
  listPmsTaskLists,
  listSpaceMembers,
  listSpaces,
  updateSpace,
  type PmsSpace,
  type PmsSpaceMember,
} from '../api/pms-api';
import { initials } from './pms-constants';
import { CreateTaskListModal } from './CreateTaskListModal';
import { SpaceMembersModal } from './SpaceMembersModal';
import { SpaceContextMenu } from '../sidebar/SpaceContextMenu';
import { SpaceOrderEditorModal } from '../sidebar/SpaceOrderEditorModal';
import type { SpaceOrderSavePayload } from '../sidebar/space-order-editor-model';
import {
  buildSpaceOrderChanges,
  persistSpaceOrderChanges,
} from '../sidebar/space-order-persistence';
import {
  buildSpaceOverviewCollections,
  buildSpaceOverviewLoadSuccess,
  SPACE_OVERVIEW_INITIAL_STATE,
  spaceOverviewReducer,
} from './space-overview-model';
import {
  buildPmsSpaceDocsToolPath,
  buildPmsTaskListToolPath,
} from './pms-view-route';
import { PmsSpaceToolTabs } from './PmsSpaceToolTabs';
import { PmsCenteredLoadingState } from './PmsCenteredStateBlock';
import {
  PMS_SPACE_CHANGED_EVENT,
  PMS_SPACE_ORDER_CHANGED_EVENT,
  PMS_TASK_LIST_CHANGED_EVENT,
  dispatchPmsSpaceChanged,
  dispatchPmsSpaceOrderChanged,
  type PmsSpaceChangedDetail,
  type PmsSpaceOrderChangedDetail,
  type PmsTaskListChangedDetail,
} from './pms-events';

const AVATAR_COLORS = [
  'bg-rose-500',
  'bg-pink-500',
  'bg-fuchsia-500',
  'bg-purple-500',
  'bg-violet-500',
  'bg-indigo-500',
  'bg-blue-500',
  'bg-sky-500',
  'bg-cyan-500',
  'bg-teal-500',
  'bg-emerald-500',
  'bg-green-500',
  'bg-amber-500',
  'bg-orange-500',
];

function avatarColor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        'rounded-lg border border-app-border bg-app-surface',
        className,
      )}
    >
      {children}
    </section>
  );
}

function RecentItemIcon({ kind }: { kind: 'doc' | 'folder' | 'list' }) {
  if (kind === 'doc') return <FileText size={14} className="text-sky-500" />;
  if (kind === 'folder')
    return <FolderOpen size={14} className="text-app-warning" />;
  return <ListIcon size={14} className="text-app-accent" />;
}

interface SpaceOverviewViewProps {
  spaceId: string;
  spaceName?: string | null;
  workspaceSlug?: string | null;
}

export const SpaceOverviewView = (props: SpaceOverviewViewProps) => (
  <SpaceOverviewViewSession
    key={`${props.spaceId}:${props.workspaceSlug ?? ''}`}
    {...props}
  />
);

function SpaceOverviewViewSession(props: SpaceOverviewViewProps) {
  return useSpaceOverviewViewElement(props);
}

function useSpaceOverviewViewElement({
  spaceId,
  spaceName,
  workspaceSlug,
}: SpaceOverviewViewProps) {
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const navigate = useNavigate();
  const pmsRootPath = resolveDefaultWorkspaceAppPath(user, 'pms');
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();
  const [spaceMenuOpen, setSpaceMenuOpen] = useState(false);
  const [spaceOrderEditorOpen, setSpaceOrderEditorOpen] = useState(false);
  const spaceMenuButtonRef = useRef<HTMLButtonElement>(null);
  const [state, dispatch] = useReducer(
    spaceOverviewReducer,
    SPACE_OVERVIEW_INITIAL_STATE,
  );
  const {
    lists,
    folders,
    spaceDocs,
    members,
    spaceMeta,
    loading,
    createListOpen,
    membersModalOpen,
    collapsedFolderIds,
    refreshSeq,
  } = state;

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    dispatch({ type: 'loadStart' });

    Promise.all([
      listPmsTaskLists(token, spaceId, workspaceSlug),
      listFolders(token, spaceId, workspaceSlug),
      listDocsHub(token, {
        view: 'all',
        space_id: spaceId,
        page_size: 200,
        sort_by: 'target_sort_order',
        sort_dir: 'asc',
      }).catch(() => ({
        items: [] as DocsHubItem[],
        total: 0,
        page: 1,
        page_size: 200,
      })),
      listSpaceMembers(token, spaceId, workspaceSlug).catch(() => ({
        items: [] as PmsSpaceMember[],
        total: 0,
        page: 1,
        page_size: 50,
      })),
      listSpaces(token, workspaceSlug).catch(() => [] as PmsSpace[]),
    ])
      .then(([listRes, folderRes, docsRes, memberRes, spaces]) => {
        if (cancelled) return;
        dispatch(
          buildSpaceOverviewLoadSuccess({
            lists: listRes.items,
            folders: folderRes.items,
            spaceDocs: docsRes.items,
            members: memberRes.items,
            spaces,
            spaceId,
            locale,
          }),
        );
      })
      .finally(() => {
        if (!cancelled) dispatch({ type: 'loadDone' });
      });

    return () => {
      cancelled = true;
    };
  }, [spaceId, token, workspaceSlug, refreshSeq, locale]);

  const canManageMembers =
    spaceMeta?.current_user_role === 'owner' ||
    spaceMeta?.current_user_role === 'admin';
  const canEditSpaceOrder = teamRoleAllows(
    spaceMeta?.current_user_role,
    'member',
  );
  const fallbackSpaceName = t('pms.spaceOverview.fallbackSpaceName');
  const displaySpaceName = spaceMeta?.name ?? spaceName ?? fallbackSpaceName;

  useEffect(() => {
    const handleSpaceChanged = (event: Event) => {
      const detail = (event as CustomEvent<PmsSpaceChangedDetail>).detail;
      if (!detail) return;
      if (detail.type === 'updated' && detail.space.id === spaceId) {
        dispatch({ type: 'setSpaceMeta', spaceMeta: detail.space });
      }
      if (detail.type === 'deleted' && detail.spaceId === spaceId) {
        navigate(
          workspaceSlug
            ? buildWorkspaceAppPath(workspaceSlug, 'pms')
            : pmsRootPath,
        );
      }
    };

    window.addEventListener(PMS_SPACE_CHANGED_EVENT, handleSpaceChanged);
    return () => {
      window.removeEventListener(PMS_SPACE_CHANGED_EVENT, handleSpaceChanged);
    };
  }, [navigate, pmsRootPath, spaceId, workspaceSlug]);

  useEffect(() => {
    const handleTaskListChanged = (event: Event) => {
      const detail = (event as CustomEvent<PmsTaskListChangedDetail>).detail;
      if (!detail) return;
      dispatch({
        type: 'taskListChanged',
        change: detail,
        locale,
        spaceId,
      });
    };

    window.addEventListener(PMS_TASK_LIST_CHANGED_EVENT, handleTaskListChanged);
    return () => {
      window.removeEventListener(
        PMS_TASK_LIST_CHANGED_EVENT,
        handleTaskListChanged,
      );
    };
  }, [locale, spaceId]);

  useEffect(() => {
    const handleSpaceOrderChanged = (event: Event) => {
      const detail = (event as CustomEvent<PmsSpaceOrderChangedDetail>).detail;
      if (!detail || detail.spaceId !== spaceId) return;
      dispatch({
        type: 'applyOrderChanges',
        listChanges: detail.listChanges,
        docChanges: detail.docChanges,
        locale,
      });
    };

    window.addEventListener(
      PMS_SPACE_ORDER_CHANGED_EVENT,
      handleSpaceOrderChanged,
    );
    return () => {
      window.removeEventListener(
        PMS_SPACE_ORDER_CHANGED_EVENT,
        handleSpaceOrderChanged,
      );
    };
  }, [locale, spaceId]);

  const handleSaveSpaceOrder = useCallback(
    async (payload: SpaceOrderSavePayload) => {
      if (!token || !canEditSpaceOrder) return;
      const changes = buildSpaceOrderChanges({
        currentDocs: spaceDocs,
        currentLists: lists,
        payload,
      });
      if (changes.listChanges.length === 0 && changes.docChanges.length === 0) {
        return;
      }

      try {
        await persistSpaceOrderChanges({ changes, spaceId, token });
        dispatchPmsSpaceOrderChanged({ spaceId, ...changes });
      } catch (error) {
        throw new Error(
          error instanceof Error && error.message
            ? error.message
            : t('pms.orderEditor.saveFailed'),
        );
      }
    },
    [canEditSpaceOrder, lists, spaceDocs, spaceId, t, token],
  );

  const handleRenameSpace = useCallback(async () => {
    if (!token || !canManageMembers) return;
    const newName = await prompt({
      title: t('pms.sidebar.renameSpace'),
      defaultValue: displaySpaceName,
      placeholder: t('pms.spaceName'),
      submitLabel: t('common:actions.save'),
      cancelLabel: t('common:actions.cancel'),
    });
    const trimmedName = newName?.trim() ?? '';
    if (!trimmedName || trimmedName === displaySpaceName) return;
    try {
      const updated = await updateSpace(token, spaceId, { name: trimmedName });
      dispatch({ type: 'setSpaceMeta', spaceMeta: updated });
      dispatchPmsSpaceChanged({ type: 'updated', space: updated });
    } catch {
      /* keep the previous name visible */
    }
  }, [canManageMembers, displaySpaceName, prompt, spaceId, t, token]);

  const handleDeleteSpace = useCallback(async () => {
    if (!token || !canManageMembers) return;
    const confirmed = await confirm({
      title: t('pms.sidebar.deleteSpace'),
      description: t('pms.sidebar.deleteSpaceDescription'),
      confirmLabel: t('pms.sidebar.moveToTrash'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!confirmed) return;
    try {
      await deleteSpace(token, spaceId);
      dispatchPmsSpaceChanged({ type: 'deleted', spaceId });
      navigate(
        workspaceSlug
          ? buildWorkspaceAppPath(workspaceSlug, 'pms')
          : pmsRootPath,
      );
    } catch {
      /* stay on the current space if deletion fails */
    }
  }, [
    canManageMembers,
    confirm,
    navigate,
    pmsRootPath,
    spaceId,
    t,
    token,
    workspaceSlug,
  ]);

  const { allFoldersCollapsed, listsByFolder, recentItems, rootLists } =
    useMemo(
      () =>
        buildSpaceOverviewCollections({
          collapsedFolderIds,
          fallbackSpaceName,
          folders,
          lists,
          spaceDocs,
          spaceName: displaySpaceName,
        }),
      [
        collapsedFolderIds,
        displaySpaceName,
        fallbackSpaceName,
        folders,
        lists,
        spaceDocs,
      ],
    );

  const toggleFolder = (folderId: string) => {
    dispatch({ type: 'toggleFolder', folderId });
  };

  if (loading) {
    return <PmsCenteredLoadingState />;
  }

  return (
    <div className="flex h-full min-w-0 flex-col bg-app-bg">
      <header className="border-b border-app-border bg-app-bg px-4 pt-3 lg:px-5">
        <div className="flex min-w-0 items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex size-6 shrink-0 items-center justify-center rounded bg-app-accent text-app-accent-fg">
              <Layout size={14} />
            </div>
            <h1 className="app-text-title-sm truncate text-app-ink">
              {displaySpaceName}
            </h1>
            <button
              className="flex size-7 shrink-0 items-center justify-center rounded text-app-ink/45 hover:bg-app-surface-hover hover:text-yellow-500"
              title={t('pms.actions.favorite')}
              type="button"
            >
              <Star size={14} />
            </button>
            <button
              ref={spaceMenuButtonRef}
              className="flex size-7 shrink-0 items-center justify-center rounded text-app-ink/45 hover:bg-app-surface-hover hover:text-app-ink"
              onClick={() => setSpaceMenuOpen((current) => !current)}
              title={t('pms.spaceOverview.manageSpace')}
              type="button"
              aria-label={t('pms.spaceOverview.manageSpace')}
            >
              <MoreHorizontal size={14} />
            </button>
            {canEditSpaceOrder ? (
              <button
                aria-label={t('pms.orderEditor.title', {
                  spaceName: displaySpaceName,
                })}
                className="app-text-control-sm inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-app-border px-2 text-app-ink/60 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                onClick={() => setSpaceOrderEditorOpen(true)}
                title={t('pms.orderEditor.listsDescription')}
                type="button"
              >
                <ArrowUpDown aria-hidden="true" size={13} />
                <span className="hidden sm:inline">
                  {t('pms.orderEditor.openAction')}
                </span>
              </button>
            ) : null}
          </div>
          <button
            className="app-text-control-sm rounded-md bg-app-ink px-3 py-1.5 text-app-bg transition-colors hover:bg-app-ink/90"
            onClick={() => dispatch({ type: 'setCreateListOpen', open: true })}
            type="button"
          >
            {t('pms.spaceOverview.newList')}
          </button>
        </div>

        <PmsSpaceToolTabs
          activeTab="overview"
          className="mt-3"
          spaceId={spaceId}
          workspaceSlug={workspaceSlug}
        />
      </header>

      <SpaceContextMenu
        open={spaceMenuOpen}
        anchorRef={spaceMenuButtonRef}
        onClose={() => setSpaceMenuOpen(false)}
        onManageMembers={() =>
          dispatch({ type: 'setMembersModalOpen', open: true })
        }
        canManage={canManageMembers}
        onRename={canManageMembers ? handleRenameSpace : undefined}
        onDelete={canManageMembers ? handleDeleteSpace : undefined}
      />

      <main className="flex-1 overflow-y-auto p-4 custom-scrollbar lg:p-5">
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-3">
            <Card>
              <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
                <h2 className="app-text-title-sm text-app-ink">
                  {t('pms.spaceOverview.recent')}
                </h2>
                <MoreHorizontal size={14} className="text-app-ink/35" />
              </div>
              <div className="space-y-1 p-3">
                {recentItems.map((item) => (
                  <button
                    key={`${item.kind}-${item.id}`}
                    className="flex w-full min-w-0 items-center gap-2 rounded-md p-2 text-left hover:bg-app-surface-hover"
                    onClick={() => {
                      if (item.kind === 'list') {
                        navigate(
                          buildPmsTaskListToolPath({
                            taskListId: item.id,
                            workspaceSlug,
                          }),
                        );
                      }
                      if (item.kind === 'doc')
                        navigate(
                          buildPmsSpaceDocsToolPath({
                            docId: item.id,
                            spaceId,
                            workspaceSlug,
                          }),
                        );
                    }}
                    type="button"
                  >
                    <RecentItemIcon kind={item.kind} />
                    <span className="app-text-body-sm min-w-0 flex-1 truncate text-app-ink">
                      {item.name}
                    </span>
                    {item.context ? (
                      <span className="app-text-caption max-w-[8rem] truncate text-app-ink/40">
                        {item.context}
                      </span>
                    ) : null}
                  </button>
                ))}
                {recentItems.length === 0 ? (
                  <p className="app-text-body-sm p-2 text-app-ink/40">
                    {t('pms.spaceOverview.noRecent')}
                  </p>
                ) : null}
              </div>
            </Card>

            <Card>
              <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
                <h2 className="app-text-title-sm text-app-ink">
                  {t('pms.spaceOverview.docs')}
                </h2>
                <button
                  className="app-text-caption text-app-ink/50 hover:text-app-accent"
                  onClick={() =>
                    navigate(
                      buildPmsSpaceDocsToolPath({ spaceId, workspaceSlug }),
                    )
                  }
                  type="button"
                >
                  {t('pms.spaceOverview.viewAll')}
                </button>
              </div>
              <div className="space-y-1 p-3">
                {spaceDocs.slice(0, 6).map((doc) => (
                  <button
                    key={doc.id}
                    onClick={() =>
                      navigate(
                        buildPmsSpaceDocsToolPath({
                          docId: doc.id,
                          spaceId,
                          workspaceSlug,
                        }),
                      )
                    }
                    className="flex w-full min-w-0 items-center gap-2 rounded-md p-2 text-left hover:bg-app-surface-hover"
                    type="button"
                  >
                    <FileText size={14} className="shrink-0 text-sky-500" />
                    <span className="app-text-body-sm min-w-0 flex-1 truncate text-app-ink">
                      {doc.title}
                    </span>
                  </button>
                ))}
                {spaceDocs.length === 0 ? (
                  <p className="app-text-body-sm p-2 text-app-ink/40">
                    {t('pms.spaceOverview.noDocCollections')}
                  </p>
                ) : null}
              </div>
            </Card>

            <Card>
              <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
                <h2 className="app-text-title-sm text-app-ink">
                  {t('pms.spaceOverview.membersCount', {
                    count: members.length,
                  })}
                </h2>
                <button
                  className="app-text-caption text-app-ink/50 hover:text-app-accent"
                  onClick={() =>
                    dispatch({ type: 'setMembersModalOpen', open: true })
                  }
                  type="button"
                >
                  {canManageMembers
                    ? t('pms.spaceMembers.titleSuffix')
                    : t('pms.spaceOverview.viewAll')}
                </button>
              </div>
              <div className="flex flex-wrap gap-2 p-4">
                {members.slice(0, 12).map((member) => (
                  <button
                    key={member.user_id}
                    title={`${member.full_name} · ${member.email}`}
                    className="inline-flex min-w-0 items-center gap-2 rounded-full border border-app-border bg-app-surface-sidebar py-1 pl-1 pr-3"
                    onClick={() =>
                      dispatch({ type: 'setMembersModalOpen', open: true })
                    }
                    type="button"
                  >
                    <div
                      className={`flex size-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white ${avatarColor(member.user_id)}`}
                    >
                      {initials(member.full_name)}
                    </div>
                    <span className="app-text-caption max-w-[8rem] truncate text-app-ink">
                      {member.full_name}
                    </span>
                  </button>
                ))}
                {members.length === 0 ? (
                  <p className="app-text-body-sm text-app-ink/40">
                    {t('pms.spaceMembers.noMembers')}
                  </p>
                ) : null}
                {members.length > 12 ? (
                  <button
                    type="button"
                    onClick={() =>
                      dispatch({ type: 'setMembersModalOpen', open: true })
                    }
                    className="app-text-caption inline-flex items-center rounded-full border border-dashed border-app-border px-3 py-1 text-app-ink/60 hover:border-app-accent hover:text-app-accent"
                  >
                    {t('pms.spaceOverview.moreMembers', {
                      count: members.length - 12,
                    })}
                  </button>
                ) : null}
              </div>
            </Card>
          </div>

          <Card>
            <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
              <h2 className="app-text-title-sm flex items-center gap-2 text-app-ink">
                <FolderOpen size={16} className="text-app-warning" />
                {t('pms.spaceOverview.folders')}
              </h2>
              {folders.length > 0 ? (
                <button
                  className="app-text-caption text-app-ink/50 hover:text-app-accent"
                  onClick={() =>
                    dispatch({
                      type: 'setAllFoldersCollapsed',
                      folderIds: folders.map((folder) => folder.id),
                      collapsed: !allFoldersCollapsed,
                    })
                  }
                  type="button"
                >
                  {allFoldersCollapsed
                    ? t('pms.spaceOverview.expandAll')
                    : t('pms.spaceOverview.collapseAll')}
                </button>
              ) : null}
            </div>
            <div className="divide-y divide-app-border">
              {folders.map((folder) => {
                const folderLists = listsByFolder.get(folder.id) ?? [];
                const collapsed = collapsedFolderIds.has(folder.id);
                return (
                  <div key={folder.id}>
                    <button
                      className="flex w-full min-w-0 items-center gap-2 px-4 py-3 text-left hover:bg-app-surface-hover"
                      onClick={() => toggleFolder(folder.id)}
                      type="button"
                    >
                      {collapsed ? (
                        <ChevronRight
                          size={14}
                          className="shrink-0 text-app-ink/40"
                        />
                      ) : (
                        <ChevronDown
                          size={14}
                          className="shrink-0 text-app-ink/40"
                        />
                      )}
                      <FolderOpen
                        size={15}
                        className="shrink-0 text-app-warning"
                      />
                      <span className="app-text-body-sm min-w-0 flex-1 truncate font-medium text-app-ink">
                        {folder.name}
                      </span>
                      <span className="app-text-caption shrink-0 text-app-ink/40">
                        {t('pms.spaceOverview.folderListCount', {
                          count: folderLists.length,
                        })}
                      </span>
                    </button>
                    {!collapsed ? (
                      <div className="space-y-1 pb-2 pl-10 pr-4">
                        {folderLists.map((list) => (
                          <button
                            key={list.id}
                            className="flex w-full min-w-0 items-center gap-2 rounded-md p-2 text-left hover:bg-app-surface-hover"
                            onClick={() =>
                              navigate(
                                buildPmsTaskListToolPath({
                                  taskListId: list.id,
                                  workspaceSlug,
                                }),
                              )
                            }
                            type="button"
                          >
                            <ListIcon
                              size={14}
                              className="shrink-0 text-app-accent"
                            />
                            <span className="app-text-body-sm min-w-0 flex-1 truncate text-app-ink">
                              {list.name}
                            </span>
                            <span className="app-text-caption shrink-0 text-app-ink/40">
                              {t('pms.spaceOverview.taskCount', {
                                count: list.task_count,
                              })}
                            </span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
              {folders.length === 0 ? (
                <p className="app-text-body-sm p-4 text-app-ink/40">
                  {t('pms.spaceOverview.noFolders')}
                </p>
              ) : null}
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
              <h2 className="app-text-title-sm flex items-center gap-2 text-app-ink">
                <FolderKanban size={16} className="text-app-accent" />
                {t('pms.spaceOverview.lists')}
              </h2>
              <button
                className="app-text-caption inline-flex items-center gap-1 text-app-ink/50 hover:text-app-accent"
                onClick={() =>
                  dispatch({ type: 'setCreateListOpen', open: true })
                }
                type="button"
              >
                <Plus size={13} />
                {t('pms.spaceOverview.newList')}
              </button>
            </div>
            <div className="divide-y divide-app-border">
              {[...rootLists, ...lists.filter((list) => list.folder_id)].map(
                (list) => (
                  <button
                    key={list.id}
                    onClick={() =>
                      navigate(
                        buildPmsTaskListToolPath({
                          taskListId: list.id,
                          workspaceSlug,
                        }),
                      )
                    }
                    className="grid w-full min-w-0 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-4 px-4 py-3 text-left hover:bg-app-surface-hover"
                    type="button"
                  >
                    <div className="min-w-0">
                      <div className="app-text-body-sm truncate font-medium text-app-ink">
                        {list.name}
                      </div>
                      <div className="app-text-caption truncate text-app-ink/40">
                        {list.folder_name ?? displaySpaceName}
                      </div>
                    </div>
                    <span className="app-text-caption text-app-ink/45">
                      {t('pms.spaceOverview.taskCount', {
                        count: list.task_count,
                      })}
                    </span>
                    <span className="app-text-caption text-app-ink/45">
                      {Math.round(list.progress * 100)}%
                    </span>
                  </button>
                ),
              )}
              {lists.length === 0 ? (
                <p className="app-text-body-sm p-4 text-app-ink/40">
                  {t('pms.overviewPage.noLists')}
                </p>
              ) : null}
            </div>
          </Card>
        </div>
      </main>

      <CreateTaskListModal
        isOpen={createListOpen}
        onClose={() => dispatch({ type: 'setCreateListOpen', open: false })}
        teamId={spaceId}
        onCreated={(taskList) => {
          dispatch({ type: 'addList', list: taskList, locale });
          navigate(
            buildPmsTaskListToolPath({
              taskListId: taskList.id,
              workspaceSlug,
            }),
          );
        }}
      />

      <SpaceMembersModal
        isOpen={membersModalOpen}
        onClose={() => dispatch({ type: 'setMembersModalOpen', open: false })}
        spaceId={spaceId}
        spaceName={displaySpaceName}
        workspaceSlug={workspaceSlug}
        canManage={canManageMembers}
        currentUserRole={spaceMeta?.current_user_role ?? null}
        onChanged={() => dispatch({ type: 'membersChanged' })}
      />
      <SpaceOrderEditorModal
        isOpen={spaceOrderEditorOpen && canEditSpaceOrder}
        onClose={() => setSpaceOrderEditorOpen(false)}
        spaceName={displaySpaceName}
        folders={folders}
        lists={lists}
        docs={spaceDocs}
        onSave={handleSaveSpaceOrder}
      />
      {promptDialog}
      {confirmDialog}
    </div>
  );
}
