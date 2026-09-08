import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import {
  Archive,
  ArrowUpDown,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  Layout,
  MoreHorizontal,
  Plus,
} from 'lucide-react';
import { AnimatePresence, LazyMotion, domAnimation, m } from 'motion/react';
import type * as React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { DocsHubItem } from '@/src/app-modules/docs/public-api';
import { cn } from '@/src/lib/utils';
import type { PmsTaskList } from '../api/pms-api';
import { taskListRoleAllows } from '../api/pms-permissions';
import {
  resolveFlatDropZone,
  type FlatDropZone,
} from '../api/pms-sidebar-reorder';
import { FolderAddPopover } from './FolderAddPopover';
import { FolderContextMenu } from './FolderContextMenu';
import { SortableDocLink } from './SortableDocLink';
import { SortableListLink } from './SortableListLink';
import { sortSpaceDocs, type FolderWithLists } from './space-tree-model';
import { SpaceAddPopover } from './SpaceAddPopover';
import { SpaceContextMenu } from './SpaceContextMenu';

type SpaceItemProps = {
  spaceId: string;
  name: string;
  iconColor: string;
  rootLists: PmsTaskList[];
  archivedLists: PmsTaskList[];
  folders: FolderWithLists[];
  expanded: boolean;
  onToggle: () => void;
  onNavigate: () => void;
  onAddList: () => void;
  onAddListToFolder: (folderId: string) => void;
  onAddFolder: () => void;
  onOpenDocs: () => void;
  onMoveFolder: (folderId: string, direction: 'up' | 'down') => void;
  onRenameFolder: (folderId: string, currentName: string) => void;
  onDeleteFolder: (folderId: string) => void;
  onRenameList: (listId: string, currentName: string) => void;
  onDeleteList: (listId: string, currentName: string) => void;
  onArchiveList: (listId: string, currentName: string) => void;
  onRestoreList: (listId: string, currentName: string) => void;
  onOpenListSettings: (listId: string) => void;
  onRenameSpace: (newName: string) => void;
  onDeleteSpace: () => void;
  onManageMembers: () => void;
  onOpenOrderEditor: () => void;
  spaceDocs: DocsHubItem[];
  onRenameDoc: (docId: string, newTitle: string) => void;
  onDeleteDoc: (docId: string) => void;
  onReorderList: (
    activeListId: string,
    overListId: string,
    zone: FlatDropZone,
  ) => Promise<void>;
  onReorderDoc: (
    activeDocId: string,
    overDocId: string,
    zone: FlatDropZone,
  ) => Promise<void>;
  activeNavItemId: string;

  canCreateSpaceContent: boolean;
  canManageSpace: boolean;
  canManageCollections: boolean;
};

type SpaceTreeDragKind = 'list' | 'doc';
type SpaceTreeDropIndicator = {
  overId: string;
  zone: FlatDropZone;
} | null;

export function SpaceItem(props: SpaceItemProps) {
  return useSpaceItemContent(props);
}

function useSpaceTreeReorderDnd({
  folders,
  onReorderDoc,
  onReorderList,
  rootLists,
  spaceDocs,
}: Pick<
  SpaceItemProps,
  'folders' | 'onReorderDoc' | 'onReorderList' | 'rootLists' | 'spaceDocs'
>) {
  const [dropIndicator, setDropIndicator] =
    useState<SpaceTreeDropIndicator>(null);
  const dragPointerYRef = useRef<number>(0);
  const dndSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  const allListsInSpace = useMemo(() => {
    const out: PmsTaskList[] = [...rootLists];
    for (const folder of folders) out.push(...folder.lists);
    return out;
  }, [folders, rootLists]);
  const sortableItemIds = useMemo(
    () => [
      ...allListsInSpace.map((list) => list.id),
      ...spaceDocs.map((doc) => doc.id),
    ],
    [allListsInSpace, spaceDocs],
  );
  const handleDragPointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      dragPointerYRef.current = event.clientY;
    },
    [],
  );
  const handleDragStart = useCallback(() => {
    setDropIndicator(null);
  }, []);
  const handleDragCancel = useCallback(() => {
    setDropIndicator(null);
  }, []);
  const handleDragOver = useCallback((event: DragOverEvent) => {
    const { active, over } = event;
    if (!over || !active || over.id === active.id) {
      setDropIndicator(null);
      return;
    }
    const activeKind = active.data.current?.kind as
      | SpaceTreeDragKind
      | undefined;
    const overKind = over.data.current?.kind as SpaceTreeDragKind | undefined;
    if (!activeKind || !overKind || activeKind !== overKind) {
      setDropIndicator(null);
      return;
    }
    const overRect = over.rect;
    if (!overRect) return;
    const pointerY = dragPointerYRef.current;
    const pointerWithinRow =
      pointerY >= overRect.top && pointerY <= overRect.top + overRect.height;
    let zone: FlatDropZone;
    if (pointerWithinRow) {
      zone = resolveFlatDropZone(pointerY, {
        top: overRect.top,
        height: overRect.height,
      });
    } else {
      const activeRect =
        active.rect?.current?.translated ??
        active.rect?.current?.initial ??
        null;
      if (!activeRect) return;
      zone = overRect.top < activeRect.top ? 'before' : 'after';
    }
    setDropIndicator((current) =>
      current && current.overId === over.id && current.zone === zone
        ? current
        : { overId: String(over.id), zone },
    );
  }, []);
  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const indicator = dropIndicator;
      setDropIndicator(null);
      if (!indicator) return;
      const activeId = String(event.active.id);
      if (activeId === indicator.overId) return;
      const activeKind = event.active.data.current?.kind as
        | SpaceTreeDragKind
        | undefined;
      const overKind = event.over?.data.current?.kind as
        | SpaceTreeDragKind
        | undefined;
      if (!activeKind || activeKind !== overKind) return;
      if (activeKind === 'list') {
        await onReorderList(activeId, indicator.overId, indicator.zone);
      } else {
        await onReorderDoc(activeId, indicator.overId, indicator.zone);
      }
    },
    [dropIndicator, onReorderDoc, onReorderList],
  );

  return {
    dndSensors,
    dropIndicator,
    handleDragCancel,
    handleDragEnd,
    handleDragOver,
    handleDragPointerMove,
    handleDragStart,
    sortableItemIds,
  };
}

function useSpaceItemContent({
  spaceId,
  name,
  iconColor,
  rootLists,
  archivedLists,
  folders,
  expanded,
  onToggle,
  onNavigate,
  onAddList,
  onAddListToFolder,
  onAddFolder,
  onOpenDocs,
  onMoveFolder,
  onRenameFolder,
  onDeleteFolder,
  onRenameList,
  onDeleteList,
  onArchiveList,
  onRestoreList,
  onOpenListSettings,
  onRenameSpace,
  onDeleteSpace,
  onManageMembers,
  onOpenOrderEditor,
  spaceDocs,
  onRenameDoc,
  onDeleteDoc,
  onReorderList,
  onReorderDoc,
  activeNavItemId,
  canCreateSpaceContent,
  canManageSpace,
  canManageCollections,
}: SpaceItemProps) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const [addPopoverOpen, setAddPopoverOpen] = useState(false);
  const [spaceMenuOpen, setSpaceMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState({
    sourceName: '',
    value: '',
  });
  const renameInputRef = useRef<HTMLInputElement>(null);
  const addBtnRef = useRef<HTMLButtonElement>(null);
  const spaceMenuBtnRef = useRef<HTMLButtonElement>(null);
  const [collapsedFolderIds, setCollapsedFolderIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [folderPopoverOpen, setFolderPopoverOpen] = useState<string | null>(
    null,
  );
  const [folderMenuOpen, setFolderMenuOpen] = useState<string | null>(null);
  const folderMenuBtnRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const folderAddBtnRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const [listMenuOpen, setListMenuOpen] = useState<string | null>(null);
  const [archivedListsExpanded, setArchivedListsExpanded] = useState(false);
  const listMenuBtnRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const [docMenuOpen, setDocMenuOpen] = useState<string | null>(null);
  const docMenuBtnRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const [renamingDocId, setRenamingDocId] = useState<string | null>(null);
  const [docRenameValue, setDocRenameValue] = useState('');
  const docRenameInputRef = useRef<HTMLInputElement>(null);
  const {
    dndSensors,
    dropIndicator,
    handleDragCancel,
    handleDragEnd,
    handleDragOver,
    handleDragPointerMove,
    handleDragStart,
    sortableItemIds,
  } = useSpaceTreeReorderDnd({
    folders,
    onReorderDoc,
    onReorderList,
    rootLists,
    spaceDocs,
  });

  if (!renaming && renameDraft.sourceName !== name) {
    setRenameDraft({ sourceName: name, value: name });
  }

  const renameValue = renameDraft.value;
  const setRenameValue = useCallback((value: string) => {
    setRenameDraft((current) => ({ ...current, value }));
  }, []);

  const spaceOverviewToolId = `pms-space-${spaceId}`;
  const spaceActive =
    activeNavItemId === spaceOverviewToolId ||
    activeNavItemId.startsWith(`pms-space-${spaceId}-docs`) ||
    activeNavItemId.startsWith(`pms-space-${spaceId}-whiteboards`) ||
    rootLists.some((list) => activeNavItemId === `pms-list-${list.id}`) ||
    folders.some(({ lists }) =>
      lists.some((list) => activeNavItemId === `pms-list-${list.id}`),
    ) ||
    archivedLists.some((list) => activeNavItemId === `pms-list-${list.id}`);

  useEffect(() => {
    if (
      archivedLists.some((list) => activeNavItemId === `pms-list-${list.id}`)
    ) {
      setArchivedListsExpanded(true);
    }
  }, [activeNavItemId, archivedLists]);

  const rootListsOrdered = useMemo(
    () =>
      Array.from(rootLists).sort(
        (left, right) =>
          left.sort_order - right.sort_order ||
          left.name.localeCompare(right.name, locale),
      ),
    [rootLists, locale],
  );
  const rootDocsOrdered = useMemo(
    () => sortSpaceDocs(spaceDocs, locale),
    [spaceDocs, locale],
  );

  const expandedFolders = useMemo(() => {
    const next = new Set<string>();
    for (const { folder } of folders) {
      if (!collapsedFolderIds.has(folder.id)) {
        next.add(folder.id);
      }
    }
    return next;
  }, [collapsedFolderIds, folders]);

  const toggleFolder = (folderId: string) => {
    setCollapsedFolderIds((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) next.delete(folderId);
      else next.add(folderId);
      return next;
    });
  };

  return (
    <div className="space-y-0.5">
      <div className="group relative flex items-center gap-1">
        <div
          className={cn(
            'flex min-w-0 flex-1 items-center gap-1 rounded-md transition-colors',
            spaceActive ? 'bg-app-surface-hover' : 'hover:bg-app-surface-hover',
          )}
        >
          <button
            type="button"
            aria-label={
              expanded
                ? t('pms.spaceTree.collapseSpace')
                : t('pms.spaceTree.expandSpace')
            }
            onClick={onToggle}
            className={cn(
              'ml-1 flex h-7 w-6 shrink-0 items-center justify-center rounded transition-colors',
              spaceActive
                ? 'text-app-ink/50'
                : 'text-app-ink/70 dark:text-app-ink/80 hover:text-app-ink dark:hover:text-white',
            )}
            title={
              expanded
                ? t('pms.spaceTree.collapseSpace')
                : t('pms.spaceTree.expandSpace')
            }
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>

          {renaming ? (
            <div className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pl-0.5 pr-2">
              <div
                className={cn(
                  'flex size-5 shrink-0 items-center justify-center rounded',
                  iconColor,
                )}
              >
                <Layout size={12} className="text-white" />
              </div>
              <input
                aria-label={t('common:actions.rename')}
                ref={renameInputRef}
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const trimmed = renameValue.trim();
                    if (trimmed && trimmed !== name) onRenameSpace(trimmed);
                    setRenaming(false);
                  } else if (e.key === 'Escape') {
                    setRenameValue(name);
                    setRenaming(false);
                  }
                }}
                onBlur={() => {
                  const trimmed = renameValue.trim();
                  if (trimmed && trimmed !== name) onRenameSpace(trimmed);
                  setRenaming(false);
                }}
                className="app-text-control-sm flex-1 min-w-0 rounded border border-blue-500 bg-transparent px-1 py-0.5 text-app-ink outline-none"
              />
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                if (!expanded) onToggle();
                onNavigate();
              }}
              className={cn(
                'flex min-w-0 flex-1 items-center gap-2 py-1.5 pl-0.5 pr-2 text-left',
                spaceActive
                  ? 'text-app-ink'
                  : 'text-app-ink/70 dark:text-app-ink/80 group-hover:text-app-ink dark:group-hover:text-white',
              )}
            >
              <div
                className={cn(
                  'flex size-5 shrink-0 items-center justify-center rounded',
                  iconColor,
                )}
              >
                <Layout size={12} className="text-white" />
              </div>
              <span
                className={cn(
                  'app-text-control-sm truncate',
                  spaceActive && 'font-medium',
                )}
              >
                {name}
              </span>
            </button>
          )}
        </div>

        {canCreateSpaceContent || canManageSpace ? (
          <>
            <div
              className={cn(
                'items-center gap-0.5 pr-1 shrink-0',
                addPopoverOpen || spaceMenuOpen
                  ? 'flex'
                  : 'hidden group-hover:flex',
              )}
            >
              {canCreateSpaceContent ? (
                <button
                  type="button"
                  aria-label={t('pms.orderEditor.title', { spaceName: name })}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onOpenOrderEditor();
                  }}
                  className="p-0.5 hover:bg-app-surface-hover rounded text-app-ink/70 dark:text-app-ink/80 hover:text-app-ink dark:hover:text-white transition-colors"
                  title={t('pms.orderEditor.title', { spaceName: name })}
                >
                  <ArrowUpDown size={14} />
                </button>
              ) : null}
              {canManageSpace ? (
                <button
                  type="button"
                  aria-label={t('pms.taskDetail.moreOptions')}
                  ref={spaceMenuBtnRef}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    setSpaceMenuOpen((current) => !current);
                  }}
                  className="p-0.5 hover:bg-app-surface-hover rounded text-app-ink/70 dark:text-app-ink/80 hover:text-app-ink dark:hover:text-white transition-colors"
                  title={t('pms.taskDetail.moreOptions')}
                >
                  <MoreHorizontal size={14} />
                </button>
              ) : null}
              {canCreateSpaceContent ? (
                <button
                  type="button"
                  aria-label={t('common:actions.add')}
                  ref={addBtnRef}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    setAddPopoverOpen((current) => !current);
                  }}
                  className="p-0.5 hover:bg-app-surface-hover rounded text-app-ink/70 dark:text-app-ink/80 hover:text-app-ink dark:hover:text-white transition-colors"
                  title={t('common:actions.add')}
                >
                  <Plus size={14} />
                </button>
              ) : null}
            </div>

            <SpaceContextMenu
              open={spaceMenuOpen}
              anchorRef={spaceMenuBtnRef}
              onClose={() => setSpaceMenuOpen(false)}
              onRename={() => {
                setRenameValue(name);
                setRenaming(true);
              }}
              onManageMembers={onManageMembers}
              canManage={canManageSpace}
              onDelete={onDeleteSpace}
            />
            <SpaceAddPopover
              open={addPopoverOpen}
              anchorRef={addBtnRef}
              onClose={() => setAddPopoverOpen(false)}
              onCreateList={onAddList}
              onCreateFolder={onAddFolder}
              onOpenDocs={onOpenDocs}
            />
          </>
        ) : null}
      </div>

      <LazyMotion features={domAnimation}>
        <AnimatePresence initial={false}>
          {expanded && (
            <m.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <DndContext
                sensors={dndSensors}
                collisionDetection={closestCenter}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragEnd={handleDragEnd}
                onDragCancel={handleDragCancel}
              >
                <SortableContext
                  items={sortableItemIds}
                  strategy={verticalListSortingStrategy}
                >
                  <div
                    className="ml-4 pl-3 border-l border-app-border space-y-1"
                    onPointerMove={handleDragPointerMove}
                  >
                    {folders.map(({ folder, lists }, folderIndex) => {
                      const isFolderExpanded = expandedFolders.has(folder.id);
                      const isFolderPopoverOpen =
                        folderPopoverOpen === folder.id;
                      const isFolderMenuOpen = folderMenuOpen === folder.id;
                      const hasAnyPopup =
                        isFolderPopoverOpen || isFolderMenuOpen;
                      const canMoveUp = folderIndex > 0;
                      const canMoveDown = folderIndex < folders.length - 1;
                      return (
                        <div key={folder.id}>
                          <div className="group/folder flex items-center">
                            <button
                              type="button"
                              aria-label={
                                isFolderExpanded
                                  ? t('pms.spaceTree.collapseSpace')
                                  : t('pms.spaceTree.expandSpace')
                              }
                              onClick={() => toggleFolder(folder.id)}
                              className="sidebar-submenu-item flex-1 min-w-0"
                            >
                              <span className="relative flex size-[13px] shrink-0 items-center justify-center text-app-ink/55">
                                <FolderOpen
                                  size={13}
                                  className="transition-opacity group-hover/folder:opacity-0"
                                />
                                <span className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover/folder:opacity-100">
                                  {isFolderExpanded ? (
                                    <ChevronDown size={13} />
                                  ) : (
                                    <ChevronRight size={13} />
                                  )}
                                </span>
                              </span>
                              <span className="sidebar-submenu-label">
                                {folder.name}
                              </span>
                            </button>
                            {canCreateSpaceContent || canManageSpace ? (
                              <>
                                <div
                                  className={cn(
                                    'items-center gap-0.5 pr-1 shrink-0',
                                    hasAnyPopup
                                      ? 'flex'
                                      : 'hidden group-hover/folder:flex',
                                  )}
                                >
                                  {canManageSpace ? (
                                    <button
                                      type="button"
                                      aria-label={t(
                                        'pms.spaceTree.folderOptions',
                                      )}
                                      ref={(el) => {
                                        if (el)
                                          folderMenuBtnRefs.current.set(
                                            folder.id,
                                            el,
                                          );
                                      }}
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        setFolderMenuOpen((current) =>
                                          current === folder.id
                                            ? null
                                            : folder.id,
                                        );
                                      }}
                                      className="p-0.5 hover:bg-app-surface-hover rounded text-app-ink/70 dark:text-app-ink/80 hover:text-app-ink dark:hover:text-white transition-colors"
                                      title={t('pms.spaceTree.folderOptions')}
                                    >
                                      <MoreHorizontal size={12} />
                                    </button>
                                  ) : null}
                                  {canCreateSpaceContent ? (
                                    <button
                                      type="button"
                                      aria-label={t(
                                        'pms.spaceTree.addToFolder',
                                      )}
                                      ref={(el) => {
                                        if (el)
                                          folderAddBtnRefs.current.set(
                                            folder.id,
                                            el,
                                          );
                                      }}
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        setFolderPopoverOpen((current) =>
                                          current === folder.id
                                            ? null
                                            : folder.id,
                                        );
                                      }}
                                      className="p-0.5 hover:bg-app-surface-hover rounded text-app-ink/70 dark:text-app-ink/80 hover:text-app-ink dark:hover:text-white transition-colors"
                                      title={t('pms.spaceTree.addToFolder')}
                                    >
                                      <Plus size={12} />
                                    </button>
                                  ) : null}
                                </div>
                                <FolderAddPopover
                                  open={isFolderPopoverOpen}
                                  anchorRef={{
                                    current:
                                      folderAddBtnRefs.current.get(folder.id) ??
                                      null,
                                  }}
                                  onClose={() => setFolderPopoverOpen(null)}
                                  onCreateList={() =>
                                    onAddListToFolder(folder.id)
                                  }
                                  onCreateDoc={onOpenDocs}
                                />
                                <FolderContextMenu
                                  open={isFolderMenuOpen}
                                  anchorRef={{
                                    current:
                                      folderMenuBtnRefs.current.get(
                                        folder.id,
                                      ) ?? null,
                                  }}
                                  onClose={() => setFolderMenuOpen(null)}
                                  onMoveUp={() => onMoveFolder(folder.id, 'up')}
                                  onMoveDown={() =>
                                    onMoveFolder(folder.id, 'down')
                                  }
                                  canMoveUp={canMoveUp}
                                  canMoveDown={canMoveDown}
                                  onRename={() =>
                                    onRenameFolder(folder.id, folder.name)
                                  }
                                  onDelete={() => onDeleteFolder(folder.id)}
                                />
                              </>
                            ) : null}
                          </div>
                          <AnimatePresence initial={false}>
                            {isFolderExpanded && (
                              <m.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                className="overflow-hidden"
                              >
                                <div className="ml-4 space-y-0.5">
                                  {lists.map((list) => (
                                    <SortableListLink
                                      key={list.id}
                                      list={list}
                                      activeNavItemId={activeNavItemId}
                                      canDrag={false}
                                      dropZone={
                                        dropIndicator &&
                                        dropIndicator.overId === list.id
                                          ? dropIndicator.zone
                                          : null
                                      }
                                      menu={{
                                        buttonRefs: listMenuBtnRefs,
                                        isOpen: listMenuOpen === list.id,
                                        onClose: () => setListMenuOpen(null),
                                        onToggle: () =>
                                          setListMenuOpen((current) =>
                                            current === list.id
                                              ? null
                                              : list.id,
                                          ),
                                      }}
                                      onArchive={
                                        taskListRoleAllows(list.role, 'admin')
                                          ? () =>
                                              onArchiveList(list.id, list.name)
                                          : undefined
                                      }
                                      onSettings={
                                        taskListRoleAllows(list.role, 'admin')
                                          ? () => onOpenListSettings(list.id)
                                          : undefined
                                      }
                                      onRename={
                                        taskListRoleAllows(list.role, 'admin')
                                          ? () =>
                                              onRenameList(list.id, list.name)
                                          : undefined
                                      }
                                    />
                                  ))}
                                </div>
                              </m.div>
                            )}
                          </AnimatePresence>
                        </div>
                      );
                    })}

                    {rootListsOrdered.map((list) => (
                      <SortableListLink
                        key={`list-${list.id}`}
                        list={list}
                        activeNavItemId={activeNavItemId}
                        canDrag={false}
                        dropZone={
                          dropIndicator && dropIndicator.overId === list.id
                            ? dropIndicator.zone
                            : null
                        }
                        menu={{
                          buttonRefs: listMenuBtnRefs,
                          isOpen: listMenuOpen === list.id,
                          onClose: () => setListMenuOpen(null),
                          onToggle: () =>
                            setListMenuOpen((current) =>
                              current === list.id ? null : list.id,
                            ),
                        }}
                        onArchive={
                          taskListRoleAllows(list.role, 'admin')
                            ? () => onArchiveList(list.id, list.name)
                            : undefined
                        }
                        onSettings={
                          taskListRoleAllows(list.role, 'admin')
                            ? () => onOpenListSettings(list.id)
                            : undefined
                        }
                        onRename={
                          taskListRoleAllows(list.role, 'admin')
                            ? () => onRenameList(list.id, list.name)
                            : undefined
                        }
                      />
                    ))}

                    {rootDocsOrdered.map((doc) => (
                      <SortableDocLink
                        key={`doc-${doc.id}`}
                        doc={doc}
                        spaceId={spaceId}
                        activeNavItemId={activeNavItemId}
                        dropZone={
                          dropIndicator && dropIndicator.overId === doc.id
                            ? dropIndicator.zone
                            : null
                        }
                        menu={{
                          buttonRefs: docMenuBtnRefs,
                          isOpen: docMenuOpen === doc.id,
                          onClose: () => setDocMenuOpen(null),
                          onToggle: () =>
                            setDocMenuOpen((current) =>
                              current === doc.id ? null : doc.id,
                            ),
                        }}
                        onDelete={() => onDeleteDoc(doc.id)}
                        permissions={{
                          canDrag: false,
                          canManageCollections,
                        }}
                        rename={{
                          inputRef: docRenameInputRef,
                          isRenaming: renamingDocId === doc.id,
                          onBegin: () => {
                            setDocRenameValue(doc.title);
                            setRenamingDocId(doc.id);
                          },
                          onCancel: () => setRenamingDocId(null),
                          onCommit: () => {
                            const trimmed = docRenameValue.trim();
                            if (trimmed && trimmed !== doc.title) {
                              onRenameDoc(doc.id, trimmed);
                            }
                            setRenamingDocId(null);
                          },
                          onValueChange: setDocRenameValue,
                          value: docRenameValue,
                        }}
                      />
                    ))}

                    {archivedLists.length > 0 ? (
                      <div className="pt-1">
                        <button
                          type="button"
                          aria-expanded={archivedListsExpanded}
                          onClick={() =>
                            setArchivedListsExpanded((current) => !current)
                          }
                          className="sidebar-submenu-item w-full text-app-ink/60"
                        >
                          {archivedListsExpanded ? (
                            <ChevronDown size={13} />
                          ) : (
                            <ChevronRight size={13} />
                          )}
                          <Archive size={13} />
                          <span className="sidebar-submenu-label">
                            {t('pms.archive.groupLabel', {
                              count: archivedLists.length,
                            })}
                          </span>
                        </button>
                        {archivedListsExpanded ? (
                          <div className="ml-4 space-y-0.5">
                            {archivedLists.map((list) => (
                              <SortableListLink
                                key={`archived-list-${list.id}`}
                                list={list}
                                activeNavItemId={activeNavItemId}
                                canDrag={false}
                                dropZone={null}
                                menu={{
                                  buttonRefs: listMenuBtnRefs,
                                  isOpen: listMenuOpen === list.id,
                                  onClose: () => setListMenuOpen(null),
                                  onToggle: () =>
                                    setListMenuOpen((current) =>
                                      current === list.id ? null : list.id,
                                    ),
                                }}
                                onRestore={
                                  taskListRoleAllows(list.role, 'admin')
                                    ? () => onRestoreList(list.id, list.name)
                                    : undefined
                                }
                                onDelete={
                                  taskListRoleAllows(list.role, 'admin')
                                    ? () => onDeleteList(list.id, list.name)
                                    : undefined
                                }
                              />
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </SortableContext>
              </DndContext>
            </m.div>
          )}
        </AnimatePresence>
      </LazyMotion>
    </div>
  );
}
