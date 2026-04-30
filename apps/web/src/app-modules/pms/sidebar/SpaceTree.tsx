import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import type * as React from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
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
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  ChevronRight,
  Layout,
  List as ListIcon,
  FolderOpen,
  FileText,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  Users,
} from 'lucide-react';

import { cn } from '@/src/lib/utils';
import {
  resolveFlatDropZone,
  type FlatDropZone,
} from '@/src/domains/pms/pms-sidebar-reorder';
import {
  getDocsItemPrimaryContainerId,
  getDocsItemPrimaryContainerSortOrder,
  type DocsHubItem,
} from '@/src/domains/docs/docs-api';
import type { PmsFolder, PmsTaskList } from '@/src/domains/pms/pms-api';

export const SPACE_COLORS = [
  'bg-emerald-500',
  'bg-blue-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-violet-500',
];

export function getSpaceDocSpaceId(doc: DocsHubItem): string {
  return getDocsItemPrimaryContainerId(doc, 'pms', 'space') ?? '';
}

export function getSpaceDocSortOrder(doc: DocsHubItem): number {
  return getDocsItemPrimaryContainerSortOrder(doc);
}

export function sortSpaceDocs(items: DocsHubItem[]): DocsHubItem[] {
  return [...items].sort(
    (left, right) => getSpaceDocSortOrder(left) - getSpaceDocSortOrder(right)
      || left.title.localeCompare(right.title, 'ko'),
  );
}

const SpaceAddPopover = ({
  open,
  anchorRef,
  onClose,
  onCreateList,
  onCreateFolder,
  onOpenDocs,
}: {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onCreateList: () => void;
  onCreateFolder: () => void;
  onOpenDocs: () => void;
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    setPos({ top: rect.top, left: rect.right + 4 });
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[9999] w-52 bg-app-bg border border-app-border rounded-lg shadow-xl py-1"
    >
      <div className="app-text-overline px-3 py-1.5 text-gray-500">
        Create
      </div>
      <button
        onClick={() => { onCreateList(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <ListIcon size={16} className="text-gray-400" />
        <div className="text-left">
          <div className="app-text-control-sm text-app-ink">List</div>
          <div className="app-text-micro text-app-ink/40">Track tasks, lists, people & more</div>
        </div>
      </button>
      <button
        onClick={() => { onCreateFolder(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <FolderOpen size={16} className="text-gray-400" />
        <div className="text-left">
          <div className="app-text-control-sm text-app-ink">Folder</div>
          <div className="app-text-micro text-app-ink/40">Group Lists, Docs & more</div>
        </div>
      </button>
      <button
        onClick={() => { onOpenDocs(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <FileText size={16} className="text-gray-400" />
        <div className="text-left">
          <div className="app-text-control-sm text-app-ink">Doc</div>
          <div className="app-text-micro text-app-ink/40">Write and organize documents</div>
        </div>
      </button>
    </div>,
    document.body,
  );
};

const FolderAddPopover = ({
  open,
  anchorRef,
  onClose,
  onCreateList,
  onCreateDoc,
}: {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onCreateList: () => void;
  onCreateDoc: () => void;
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    setPos({ top: rect.top, left: rect.right + 4 });
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[9999] w-48 bg-app-bg border border-app-border rounded-lg shadow-xl py-1"
    >
      <div className="app-text-overline px-3 py-1.5 text-gray-500">
        Create
      </div>
      <button
        onClick={() => { onCreateList(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <ListIcon size={14} className="text-gray-400" />
        <div className="app-text-control-sm text-app-ink">List</div>
      </button>
      <button
        onClick={() => { onCreateDoc(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <FileText size={14} className="text-gray-400" />
        <div className="app-text-control-sm text-app-ink">Doc</div>
      </button>
    </div>,
    document.body,
  );
};

const FolderContextMenu = ({
  open,
  anchorRef,
  onClose,
  onMoveUp,
  onMoveDown,
  canMoveUp = false,
  canMoveDown = false,
  onRename,
  onDelete,
}: {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  canMoveUp?: boolean;
  canMoveDown?: boolean;
  onRename: () => void;
  onDelete: () => void;
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    setPos({ top: rect.top, left: rect.right + 4 });
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[9999] w-44 bg-app-bg border border-app-border rounded-lg shadow-xl py-1"
    >
      {onMoveUp ? (
        <button
          onClick={() => { onMoveUp(); onClose(); }}
          disabled={!canMoveUp}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowUp size={14} className="text-gray-400" />
          <span className="app-text-control-sm text-app-ink">Move Up</span>
        </button>
      ) : null}
      {onMoveDown ? (
        <button
          onClick={() => { onMoveDown(); onClose(); }}
          disabled={!canMoveDown}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowDown size={14} className="text-gray-400" />
          <span className="app-text-control-sm text-app-ink">Move Down</span>
        </button>
      ) : null}
      <button
        onClick={() => { onRename(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <Pencil size={14} className="text-gray-400" />
        <span className="app-text-control-sm text-app-ink">Rename</span>
      </button>
      <button
        onClick={() => { onDelete(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <Trash2 size={14} className="text-red-400" />
        <span className="app-text-control-sm text-red-400">Delete</span>
      </button>
    </div>,
    document.body,
  );
};

const SpaceContextMenu = ({
  open,
  anchorRef,
  onClose,
  onRename,
  onManageMembers,
  canManage,
  onDelete,
}: {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onRename: () => void;
  onManageMembers: () => void;
  canManage: boolean;
  onDelete: () => void;
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    setPos({ top: rect.top, left: rect.right + 4 });
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[9999] w-44 bg-app-bg border border-app-border rounded-lg shadow-xl py-1"
    >
      <button
        onClick={() => { onRename(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <Pencil size={14} className="text-gray-400" />
        <span className="app-text-control-sm text-app-ink">Rename</span>
      </button>
      <button
        onClick={() => { onManageMembers(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <Users size={14} className="text-gray-400" />
        <span className="app-text-control-sm text-app-ink">
          {canManage ? '멤버 관리' : '멤버 보기'}
        </span>
      </button>
      <button
        onClick={() => { onDelete(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <Trash2 size={14} className="text-red-400" />
        <span className="app-text-control-sm text-red-400">Delete</span>
      </button>
    </div>,
    document.body,
  );
};

export type FolderWithLists = {
  folder: PmsFolder;
  lists: PmsTaskList[];
};

function useSuppressClickAfterDrag(isDragging: boolean) {
  const justDraggedRef = useRef(false);
  useEffect(() => {
    if (isDragging) {
      justDraggedRef.current = true;
      return;
    }
    if (!justDraggedRef.current) return;
    const timer = setTimeout(() => {
      justDraggedRef.current = false;
    }, 150);
    return () => clearTimeout(timer);
  }, [isDragging]);
  return useCallback((event: React.MouseEvent) => {
    if (justDraggedRef.current) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, []);
}

const SortableListLink = ({
  list,
  activeNavItemId,
  canDrag,
  dropZone,
}: {
  list: PmsTaskList;
  activeNavItemId: string;
  canDrag: boolean;
  dropZone: FlatDropZone | null;
}) => {
  const navigate = useNavigate();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: list.id,
    disabled: !canDrag,
    data: { kind: 'list', parentId: list.folder_id ?? null },
  });
  const suppressClick = useSuppressClickAfterDrag(isDragging);
  const handleClick = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    suppressClick(event);
    if (event.defaultPrevented) return;
    navigate(`/tool/pms-list-${list.id}`);
  }, [list.id, navigate, suppressClick]);
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn('relative', isDragging && 'opacity-30', canDrag && 'touch-none')}
    >
      {dropZone === 'before' ? (
        <div className="pointer-events-none absolute inset-x-1 top-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
      <button
        type="button"
        onClick={handleClick}
        className={cn(
          'sidebar-submenu-item w-full text-left',
          activeNavItemId === `pms-list-${list.id}` && 'sidebar-submenu-item-active',
        )}
      >
        <ListIcon size={13} className="text-gray-500 shrink-0" />
        <span className="sidebar-submenu-label">{list.name}</span>
        <span className="sidebar-submenu-meta">({list.issue_count})</span>
      </button>
      {dropZone === 'after' ? (
        <div className="pointer-events-none absolute inset-x-1 bottom-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
    </div>
  );
};

const SortableDocLink = ({
  doc,
  spaceId,
  activeNavItemId,
  canDrag,
  canManageCollections,
  dropZone,
  isRenaming,
  docRenameValue,
  docRenameInputRef,
  docMenuBtnRefs,
  isMenuOpen,
  onRenameValueChange,
  onCommitRename,
  onCancelRename,
  onBeginRename,
  onDelete,
  onToggleMenu,
  onCloseMenu,
}: {
  doc: DocsHubItem;
  spaceId: string;
  activeNavItemId: string;
  canDrag: boolean;
  canManageCollections: boolean;
  dropZone: FlatDropZone | null;
  isRenaming: boolean;
  docRenameValue: string;
  docRenameInputRef: React.RefObject<HTMLInputElement | null>;
  docMenuBtnRefs: React.MutableRefObject<Map<string, HTMLButtonElement>>;
  isMenuOpen: boolean;
  onRenameValueChange: (value: string) => void;
  onCommitRename: () => void;
  onCancelRename: () => void;
  onBeginRename: () => void;
  onDelete: () => void;
  onToggleMenu: () => void;
  onCloseMenu: () => void;
}) => {
  const navigate = useNavigate();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: doc.id,
    disabled: !canDrag || isRenaming,
    data: { kind: 'doc', parentId: getSpaceDocSpaceId(doc) },
  });
  const suppressClick = useSuppressClickAfterDrag(isDragging);
  const style = { transform: CSS.Transform.toString(transform), transition };
  const docNavId = `pms-space-${spaceId}-docs-${doc.id}`;
  const handleClick = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    suppressClick(event);
    if (event.defaultPrevented) return;
    navigate(`/tool/${docNavId}`);
  }, [docNavId, navigate, suppressClick]);
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn('group/doc relative flex items-center', isDragging && 'opacity-30', canDrag && !isRenaming && 'touch-none')}
    >
      {dropZone === 'before' ? (
        <div className="pointer-events-none absolute inset-x-1 top-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
      {isRenaming ? (
        <div className="sidebar-submenu-item flex-1 min-w-0">
          <FileText size={13} className="text-gray-500 shrink-0" />
          <input
            ref={docRenameInputRef}
            value={docRenameValue}
            onChange={(e) => onRenameValueChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onCommitRename();
              else if (e.key === 'Escape') onCancelRename();
            }}
            onBlur={onCommitRename}
            className="app-text-body-sm flex-1 min-w-0 rounded border border-blue-500 bg-transparent px-1 py-0.5 text-app-ink outline-none"
            autoFocus
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={handleClick}
          className={cn('sidebar-submenu-item flex-1 min-w-0 text-left', activeNavItemId === docNavId && 'sidebar-submenu-item-active')}
        >
          <FileText size={13} className="text-gray-500 shrink-0" />
          <span className="sidebar-submenu-label">{doc.title || 'Untitled'}</span>
        </button>
      )}
      {canManageCollections && !isRenaming ? (
        <>
          <div className={cn('items-center gap-0.5 pr-1 shrink-0', isMenuOpen ? 'flex' : 'hidden group-hover/doc:flex')}>
            <button
              ref={(el) => { if (el) docMenuBtnRefs.current.set(doc.id, el); }}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                onToggleMenu();
              }}
              className="p-0.5 hover:bg-app-surface-hover rounded text-gray-600 dark:text-gray-300 hover:text-app-ink dark:hover:text-white transition-colors"
              title="Doc options"
            >
              <MoreHorizontal size={12} />
            </button>
          </div>
          <FolderContextMenu
            open={isMenuOpen}
            anchorRef={{ current: docMenuBtnRefs.current.get(doc.id) ?? null }}
            onClose={onCloseMenu}
            onRename={onBeginRename}
            onDelete={onDelete}
          />
        </>
      ) : null}
      {dropZone === 'after' ? (
        <div className="pointer-events-none absolute inset-x-1 bottom-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
    </div>
  );
};

export const SpaceItem = ({
  spaceId,
  name,
  iconColor,
  rootLists,
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
}: {
  spaceId: string;
  name: string;
  iconColor: string;
  rootLists: PmsTaskList[];
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
  onRenameSpace: (newName: string) => void;
  onDeleteSpace: () => void;
  onManageMembers: () => void;
  onOpenOrderEditor: () => void;
  spaceDocs: DocsHubItem[];
  onRenameDoc: (docId: string, newTitle: string) => void;
  onDeleteDoc: (docId: string) => void;
  onReorderList: (activeListId: string, overListId: string, zone: FlatDropZone) => Promise<void>;
  onReorderDoc: (activeDocId: string, overDocId: string, zone: FlatDropZone) => Promise<void>;
  activeNavItemId: string;
  canCreateSpaceContent: boolean;
  canManageSpace: boolean;
  canManageCollections: boolean;
}) => {
  const [addPopoverOpen, setAddPopoverOpen] = useState(false);
  const [spaceMenuOpen, setSpaceMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(name);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const addBtnRef = useRef<HTMLButtonElement>(null);
  const spaceMenuBtnRef = useRef<HTMLButtonElement>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    () => new Set(folders.map((f) => f.folder.id)),
  );
  const [folderPopoverOpen, setFolderPopoverOpen] = useState<string | null>(null);
  const [folderMenuOpen, setFolderMenuOpen] = useState<string | null>(null);
  const folderMenuBtnRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const folderAddBtnRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const [docMenuOpen, setDocMenuOpen] = useState<string | null>(null);
  const docMenuBtnRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const [renamingDocId, setRenamingDocId] = useState<string | null>(null);
  const [docRenameValue, setDocRenameValue] = useState('');
  const docRenameInputRef = useRef<HTMLInputElement>(null);


  const spaceOverviewToolId = `pms-space-${spaceId}`;
  const spaceActive = activeNavItemId === spaceOverviewToolId
    || activeNavItemId.startsWith(`pms-space-${spaceId}-docs-`)
    || rootLists.some((list) => activeNavItemId === `pms-list-${list.id}`)
    || folders.some(({ lists }) => lists.some((list) => activeNavItemId === `pms-list-${list.id}`));

  const rootListsOrdered = useMemo(
    () => [...rootLists].sort(
      (left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name, 'ko'),
    ),
    [rootLists],
  );
  const rootDocsOrdered = useMemo(
    () => sortSpaceDocs(spaceDocs),
    [spaceDocs],
  );

  useEffect(() => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      for (const { folder } of folders) {
        if (!prev.has(folder.id)) next.add(folder.id);
      }
      return next.size === prev.size ? prev : next;
    });
  }, [folders]);

  const toggleFolder = (folderId: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) next.delete(folderId);
      else next.add(folderId);
      return next;
    });
  };

  const [dropIndicator, setDropIndicator] = useState<{ overId: string; zone: FlatDropZone } | null>(null);
  const dragPointerYRef = useRef<number>(0);
  const dndSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const handleDragPointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    dragPointerYRef.current = event.clientY;
  }, []);
  const allListsInSpace = useMemo(() => {
    const out: PmsTaskList[] = [...rootLists];
    for (const folder of folders) out.push(...folder.lists);
    return out;
  }, [folders, rootLists]);
  const sortableItemIds = useMemo(
    () => [...allListsInSpace.map((list) => list.id), ...spaceDocs.map((doc) => doc.id)],
    [allListsInSpace, spaceDocs],
  );
  const handleDragStart = useCallback(() => {
    setDropIndicator(null);
  }, []);
  const handleDragOver = useCallback((event: DragOverEvent) => {
    const { active, over } = event;
    if (!over || !active || over.id === active.id) {
      setDropIndicator(null);
      return;
    }
    const activeKind = active.data.current?.kind as 'list' | 'doc' | undefined;
    const overKind = over.data.current?.kind as 'list' | 'doc' | undefined;
    if (!activeKind || !overKind || activeKind !== overKind) {
      setDropIndicator(null);
      return;
    }
    const overRect = over.rect;
    if (!overRect) return;
    const pointerY = dragPointerYRef.current;
    const pointerWithinRow = pointerY >= overRect.top && pointerY <= overRect.top + overRect.height;
    let zone: FlatDropZone;
    if (pointerWithinRow) {
      zone = resolveFlatDropZone(pointerY, { top: overRect.top, height: overRect.height });
    } else {
      const activeRect = active.rect?.current?.translated ?? active.rect?.current?.initial ?? null;
      if (!activeRect) return;
      zone = overRect.top < activeRect.top ? 'before' : 'after';
    }
    setDropIndicator((current) => (
      current && current.overId === over.id && current.zone === zone
        ? current
        : { overId: String(over.id), zone }
    ));
  }, []);
  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const indicator = dropIndicator;
    setDropIndicator(null);
    if (!indicator) return;
    const activeId = String(event.active.id);
    if (activeId === indicator.overId) return;
    const activeKind = event.active.data.current?.kind as 'list' | 'doc' | undefined;
    const overKind = event.over?.data.current?.kind as 'list' | 'doc' | undefined;
    if (!activeKind || activeKind !== overKind) return;
    if (activeKind === 'list') {
      await onReorderList(activeId, indicator.overId, indicator.zone);
    } else {
      await onReorderDoc(activeId, indicator.overId, indicator.zone);
    }
  }, [dropIndicator, onReorderDoc, onReorderList]);

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
            onClick={onToggle}
            className={cn(
              'ml-1 flex h-7 w-6 shrink-0 items-center justify-center rounded transition-colors',
              spaceActive ? 'text-app-ink/50' : 'text-gray-600 dark:text-gray-300 hover:text-app-ink dark:hover:text-white',
            )}
            title={expanded ? 'Collapse Space' : 'Expand Space'}
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>

          {renaming ? (
            <div className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pl-0.5 pr-2">
              <div className={cn('h-5 w-5 shrink-0 rounded flex items-center justify-center', iconColor)}>
                <Layout size={12} className="text-white" />
              </div>
              <input
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
                autoFocus
              />
            </div>
          ) : (
            <button
              onClick={() => { if (!expanded) onToggle(); onNavigate(); }}
              className={cn(
                'flex min-w-0 flex-1 items-center gap-2 py-1.5 pl-0.5 pr-2 text-left',
                spaceActive ? 'text-app-ink' : 'text-gray-600 dark:text-gray-300 group-hover:text-app-ink dark:group-hover:text-white',
              )}
            >
              <div className={cn('h-5 w-5 shrink-0 rounded flex items-center justify-center', iconColor)}>
                <Layout size={12} className="text-white" />
              </div>
              <span className={cn('app-text-control-sm truncate', spaceActive && 'font-medium')}>{name}</span>
            </button>
          )}
        </div>

        {canCreateSpaceContent || canManageSpace ? (
          <>
            <div className={cn('items-center gap-0.5 pr-1 shrink-0', addPopoverOpen || spaceMenuOpen ? 'flex' : 'hidden group-hover:flex')}>
              {canCreateSpaceContent ? (
                <button
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onOpenOrderEditor();
                  }}
                  className="p-0.5 hover:bg-app-surface-hover rounded text-gray-600 dark:text-gray-300 hover:text-app-ink dark:hover:text-white transition-colors"
                  title="순서 편집"
                >
                  <ArrowUpDown size={14} />
                </button>
              ) : null}
              {canManageSpace ? (
                <button
                  ref={spaceMenuBtnRef}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    setSpaceMenuOpen((current) => !current);
                  }}
                  className="p-0.5 hover:bg-app-surface-hover rounded text-gray-600 dark:text-gray-300 hover:text-app-ink dark:hover:text-white transition-colors"
                  title="More"
                >
                  <MoreHorizontal size={14} />
                </button>
              ) : null}
              {canCreateSpaceContent ? (
                <button
                  ref={addBtnRef}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    setAddPopoverOpen((current) => !current);
                  }}
                  className="p-0.5 hover:bg-app-surface-hover rounded text-gray-600 dark:text-gray-300 hover:text-app-ink dark:hover:text-white transition-colors"
                  title="Add"
                >
                  <Plus size={14} />
                </button>
              ) : null}
            </div>

            <SpaceContextMenu
              open={spaceMenuOpen}
              anchorRef={spaceMenuBtnRef}
              onClose={() => setSpaceMenuOpen(false)}
              onRename={() => { setRenameValue(name); setRenaming(true); }}
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

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
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
              onDragCancel={() => setDropIndicator(null)}
            >
              <SortableContext items={sortableItemIds} strategy={verticalListSortingStrategy}>
                <div
                  className="ml-4 pl-3 border-l border-app-border space-y-1"
                  onPointerMove={handleDragPointerMove}
                >
              {folders.map(({ folder, lists }, folderIndex) => {
                const isFolderExpanded = expandedFolders.has(folder.id);
                const isFolderPopoverOpen = folderPopoverOpen === folder.id;
                const isFolderMenuOpen = folderMenuOpen === folder.id;
                const hasAnyPopup = isFolderPopoverOpen || isFolderMenuOpen;
                const canMoveUp = folderIndex > 0;
                const canMoveDown = folderIndex < folders.length - 1;
                return (
                  <div key={folder.id}>
                    <div className="group/folder flex items-center">
                      <button
                        onClick={() => toggleFolder(folder.id)}
                        className="sidebar-submenu-item flex-1 min-w-0"
                      >
                        <span className="relative flex h-[13px] w-[13px] shrink-0 items-center justify-center text-gray-500">
                          <FolderOpen size={13} className="transition-opacity group-hover/folder:opacity-0" />
                          <span className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover/folder:opacity-100">
                            {isFolderExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                          </span>
                        </span>
                        <span className="sidebar-submenu-label">{folder.name}</span>
                      </button>
                      {canCreateSpaceContent || canManageSpace ? (
                        <>
                          <div className={cn('items-center gap-0.5 pr-1 shrink-0', hasAnyPopup ? 'flex' : 'hidden group-hover/folder:flex')}>
                            {canManageSpace ? (
                              <button
                                ref={(el) => { if (el) folderMenuBtnRefs.current.set(folder.id, el); }}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setFolderMenuOpen((current) => (current === folder.id ? null : folder.id));
                                }}
                                className="p-0.5 hover:bg-app-surface-hover rounded text-gray-600 dark:text-gray-300 hover:text-app-ink dark:hover:text-white transition-colors"
                                title="Folder options"
                              >
                                <MoreHorizontal size={12} />
                              </button>
                            ) : null}
                            {canCreateSpaceContent ? (
                              <button
                                ref={(el) => { if (el) folderAddBtnRefs.current.set(folder.id, el); }}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setFolderPopoverOpen((current) => (current === folder.id ? null : folder.id));
                                }}
                                className="p-0.5 hover:bg-app-surface-hover rounded text-gray-600 dark:text-gray-300 hover:text-app-ink dark:hover:text-white transition-colors"
                                title="Add to folder"
                              >
                                <Plus size={12} />
                              </button>
                            ) : null}
                          </div>
                          <FolderAddPopover
                            open={isFolderPopoverOpen}
                            anchorRef={{ current: folderAddBtnRefs.current.get(folder.id) ?? null }}
                            onClose={() => setFolderPopoverOpen(null)}
                            onCreateList={() => onAddListToFolder(folder.id)}
                            onCreateDoc={onOpenDocs}
                          />
                          <FolderContextMenu
                            open={isFolderMenuOpen}
                            anchorRef={{ current: folderMenuBtnRefs.current.get(folder.id) ?? null }}
                            onClose={() => setFolderMenuOpen(null)}
                            onMoveUp={() => onMoveFolder(folder.id, 'up')}
                            onMoveDown={() => onMoveFolder(folder.id, 'down')}
                            canMoveUp={canMoveUp}
                            canMoveDown={canMoveDown}
                            onRename={() => onRenameFolder(folder.id, folder.name)}
                            onDelete={() => onDeleteFolder(folder.id)}
                          />
                        </>
                      ) : null}
                    </div>
                    <AnimatePresence initial={false}>
                      {isFolderExpanded && (
                        <motion.div
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
                                dropZone={dropIndicator && dropIndicator.overId === list.id ? dropIndicator.zone : null}
                              />
                            ))}
                          </div>
                        </motion.div>
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
                  dropZone={dropIndicator && dropIndicator.overId === list.id ? dropIndicator.zone : null}
                />
              ))}

              {rootDocsOrdered.map((doc) => (
                <SortableDocLink
                  key={`doc-${doc.id}`}
                  doc={doc}
                  spaceId={spaceId}
                  activeNavItemId={activeNavItemId}
                  canDrag={false}
                  canManageCollections={canManageCollections}
                  dropZone={dropIndicator && dropIndicator.overId === doc.id ? dropIndicator.zone : null}
                  isRenaming={renamingDocId === doc.id}
                  docRenameValue={docRenameValue}
                  docRenameInputRef={docRenameInputRef}
                  docMenuBtnRefs={docMenuBtnRefs}
                  isMenuOpen={docMenuOpen === doc.id}
                  onRenameValueChange={setDocRenameValue}
                  onCommitRename={() => {
                    const trimmed = docRenameValue.trim();
                    if (trimmed && trimmed !== doc.title) onRenameDoc(doc.id, trimmed);
                    setRenamingDocId(null);
                  }}
                  onCancelRename={() => setRenamingDocId(null)}
                  onBeginRename={() => { setDocRenameValue(doc.title); setRenamingDocId(doc.id); }}
                  onDelete={() => onDeleteDoc(doc.id)}
                  onToggleMenu={() => setDocMenuOpen((c) => (c === doc.id ? null : doc.id))}
                  onCloseMenu={() => setDocMenuOpen(null)}
                />
              ))}
                </div>
              </SortableContext>
            </DndContext>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
