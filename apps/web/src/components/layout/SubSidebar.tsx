import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation, useNavigate } from 'react-router-dom';
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
  applyFlatReorder,
  computeFlatDropTarget,
  resolveFlatDropZone,
  type FlatDropZone,
} from '@/src/domains/pms/pms-sidebar-reorder';
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Calendar,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Plus,
  Layout,
  Loader2,
  List as ListIcon,
  FolderOpen,
  FileText,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Sparkles,
  Trash2,
  Users,
} from 'lucide-react';
import { InlineNotice, useConfirm, usePrompt } from '@aidoo/ui';
import { cn } from '@/src/lib/utils';
import { NAV_ITEMS, APP_BAR_ITEMS } from '@/src/constants';
import { hasAdminSectionAccess, type AdminSection } from '@/src/domains/admin/admin-permissions';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { hasWorkspaceMembership, teamRoleAllows } from '@/src/domains/auth/auth-api';
import {
  CONVERSATIONS_UPDATED_EVENT,
  deleteConversation,
  listConversations,
  type ConversationSummary,
} from '@/src/domains/ai/conversations-api';
import { AiConversationsSection } from './AiConversationsSection';
import {
  createNativeDoc,
  deleteDocsItem,
  getDocsItemPrimaryContainerId,
  getDocsItemPrimaryContainerSortOrder,
  listDocsHub,
  listFavoriteDocs,
  listRecentPages,
  updateDocContainer,
  updateDocsItem,
  withDocsItemPrimaryContainerSortOrder,
  type DocsHubItem,
  type FavoriteDocItem,
  type RecentPageItem,
} from '@/src/domains/docs/docs-api';
import { listPmsTaskLists, listFolders, updateFolder, deleteFolder, listSpaces, updateSpace, deleteSpace, reorderPmsTaskLists, updatePmsTaskList, type PmsFolder, type PmsTaskList, type PmsSpace } from '@/src/domains/pms/pms-api';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
  resolveNavItemHref,
  type WorkspaceAppId,
} from '@/src/domains/workspaces/workspace-utils';
import type {
  WorkspaceBootstrapApp,
  WorkspaceBootstrapNavItem,
} from '@/src/domains/workspaces/workspaces-api';
import type { NavItem } from '@/src/constants';
import { CreateTaskListModal } from '@/src/components/views/PMSView/CreateTaskListModal';
import { CreateSpaceModal } from '@/src/components/views/PMSView/CreateSpaceModal';
import { SpaceMembersModal } from '@/src/components/views/PMSView/SpaceMembersModal';
import { CreateFolderModal } from '@/src/components/views/PMSView/CreateFolderModal';
import { SpaceOrderEditorModal } from './SpaceOrderEditorModal';
import { buildSidebarCategories } from './sub-sidebar-categories';

const SPACE_COLORS = [
  'bg-emerald-500',
  'bg-blue-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-violet-500',
];

function upsertList(lists: PmsTaskList[], item: PmsTaskList): PmsTaskList[] {
  return [item, ...lists.filter((current) => current.id !== item.id)].sort(
    (left, right) => right.updated_at.localeCompare(left.updated_at),
  );
}

function upsertSpace(spaces: PmsSpace[], space: PmsSpace): PmsSpace[] {
  return [space, ...spaces.filter((item) => item.id !== space.id)].sort(
    (left, right) => left.name.localeCompare(right.name, 'ko'),
  );
}

function getSpaceDocSpaceId(doc: DocsHubItem): string {
  return getDocsItemPrimaryContainerId(doc, 'pms', 'space') ?? '';
}

function getSpaceDocSortOrder(doc: DocsHubItem): number {
  return getDocsItemPrimaryContainerSortOrder(doc);
}

function sortSpaceDocs(items: DocsHubItem[]): DocsHubItem[] {
  return [...items].sort(
    (left, right) => getSpaceDocSortOrder(left) - getSpaceDocSortOrder(right)
      || left.title.localeCompare(right.title, 'ko'),
  );
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function isDefined<T>(value: T | null): value is T {
  return value !== null;
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

type FolderWithLists = {
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

const SpaceItem = ({
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

export const SubSidebar = ({
  activeAppId,
  activeNavItemId,
  currentWorkspaceSlug,
  workspaceApps,
  workspaceNavItems,
}: {
  activeAppId: string;
  activeNavItemId: string;
  currentWorkspaceSlug: string | null;
  workspaceApps: WorkspaceBootstrapApp[];
  workspaceNavItems: WorkspaceBootstrapNavItem[];
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();
  const isSpaceDocs = /^\/tool\/pms-space-[0-9a-f-]+-docs/.test(location.pathname);
  const isDocEditor = !isSpaceDocs && (
    location.pathname.match(/^\/tool\/[^/]+\/[^/]+$/)
    || location.pathname.match(/^\/w\/[^/]+\/docs\/[^/]+$/)
    || location.pathname.match(/^\/docs\/shared\/[^/]+$/)
  );
  const canReadTeams = hasWorkspaceMembership(user, currentWorkspaceSlug);
  const canWriteTeams = hasWorkspaceMembership(user, currentWorkspaceSlug);
  const pmsRootPath = resolveDefaultWorkspaceAppPath(user, 'pms');
  const meetingRootPath = resolveDefaultWorkspaceAppPath(user, 'meeting');
  const canManageSpace = useCallback(
    (team: PmsSpace) => teamRoleAllows(team.current_user_role, 'admin'),
    [],
  );

  const [expandedCategories, setExpandedCategories] = useState<string[]>([]);
  // Recent chat conversations for the AI sidebar. Fetched once on workspace
  // switch + refetched any time the user starts/selects a thread, so the
  // "최근 대화" list stays current without a manual refresh. Kept local to
  // the sidebar — AIView is the source of truth for the active thread.
  const [aiConversations, setAiConversations] = useState<ConversationSummary[]>(
    [],
  );
  const [aiConversationsError, setAiConversationsError] = useState<
    string | null
  >(null);
  const [pmsLists, setPmsTaskLists] = useState<PmsTaskList[]>([]);
  const [pmsFolders, setPmsFolders] = useState<PmsFolder[]>([]);
  const [pmsTeams, setPmsTeams] = useState<PmsSpace[]>([]);
  const [pmsLoading, setPmsLoading] = useState(false);
  const [pmsError, setPmsError] = useState<string | null>(null);
  const [createTaskListOpen, setCreateTaskListOpen] = useState(false);
  const [createTaskListTeamId, setCreateTaskListTeamId] = useState<string | null>(null);
  const [createTaskListFolderId, setCreateTaskListFolderId] = useState<string | null>(null);
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [manageMembersSpace, setManageMembersSpace] = useState<{
    id: string;
    name: string;
    canManage: boolean;
    currentUserRole: string | null;
  } | null>(null);
  const [orderEditorSpace, setOrderEditorSpace] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [createMenuOpen, setCreateMenuOpen] = useState(false);
  const createMenuRef = useRef<HTMLDivElement>(null);
  const [expandedSpaces, setExpandedSpaces] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!createMenuOpen) return;
    function handler(event: MouseEvent) {
      if (createMenuRef.current && !createMenuRef.current.contains(event.target as Node)) {
        setCreateMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [createMenuOpen]);

  // Reset the menu when switching apps so it doesn't stay open across navigation.
  useEffect(() => {
    setCreateMenuOpen(false);
  }, [activeAppId]);
  const [docsFavorites, setDocsFavorites] = useState<FavoriteDocItem[]>([]);
  const [docsRecentPages, setDocsRecentPages] = useState<RecentPageItem[]>([]);

  // Resizable sidebar width (persisted in localStorage)
  const SIDEBAR_MIN_WIDTH = 180;
  const SIDEBAR_MAX_WIDTH = 480;
  const SIDEBAR_DEFAULT_WIDTH = 240;
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return SIDEBAR_DEFAULT_WIDTH;
    const saved = window.localStorage.getItem('aidoo:sub-sidebar-width');
    const parsed = saved ? parseInt(saved, 10) : NaN;
    if (Number.isFinite(parsed) && parsed >= SIDEBAR_MIN_WIDTH && parsed <= SIDEBAR_MAX_WIDTH) {
      return parsed;
    }
    return SIDEBAR_DEFAULT_WIDTH;
  });
  const [isResizing, setIsResizing] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem('aidoo:sub-sidebar-collapsed') === '1';
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem('aidoo:sub-sidebar-collapsed', isCollapsed ? '1' : '0');
  }, [isCollapsed]);

  useEffect(() => {
    if (!isResizing) return;
    const handleMouseMove = (e: MouseEvent) => {
      // SubSidebar starts after the AppBar (w-16 = 64px)
      const newWidth = Math.min(
        SIDEBAR_MAX_WIDTH,
        Math.max(SIDEBAR_MIN_WIDTH, e.clientX - 64),
      );
      setSidebarWidth(newWidth);
    };
    const handleMouseUp = () => {
      setIsResizing(false);
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizing]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem('aidoo:sub-sidebar-width', String(sidebarWidth));
  }, [sidebarWidth]);

  const knownSpaceIdsRef = useRef(new Set<string>());
  const navItemRegistry = useMemo(
    () => new Map(NAV_ITEMS.map((item) => [item.id, item])),
    [],
  );
  const workspaceAppRegistry = useMemo(
    () => new Map(workspaceApps.map((item) => [item.app_id, item])),
    [workspaceApps],
  );

  const filteredItems = useMemo(
    () => {
      if (activeAppId !== 'settings') {
        return workspaceNavItems
          .filter((item) => item.app_id === activeAppId)
          .map((item) => {
            const localItem = navItemRegistry.get(item.id);
            if (!localItem) {
              return null;
            }
            const nextItem: NavItem = {
              ...localItem,
              title: item.title,
              category: item.category,
            };
            if (item.path_suffix !== undefined && item.path_suffix !== null) {
              nextItem.pathSuffix = item.path_suffix;
            }
            if (item.absolute_path !== undefined && item.absolute_path !== null) {
              nextItem.absolutePath = item.absolute_path;
            }
            if (item.link_app_id !== undefined && item.link_app_id !== null) {
              nextItem.linkAppId = item.link_app_id as NavItem['linkAppId'];
            }
            return nextItem;
          })
          .filter(isDefined);
      }

      const items = NAV_ITEMS.filter((item) => item.appId === activeAppId);
      const sectionByItemId: Partial<Record<string, AdminSection>> = {
        'settings-general': 'general',
        'settings-people': 'people',
        'settings-workspaces': 'workspaces',
        'settings-security': 'security',
        'settings-audit': 'audit',
      };

      return items.filter((item) => {
        const section = sectionByItemId[item.id];
        return section ? hasAdminSectionAccess(user?.system_roles ?? [], section) : false;
      });
    },
    [activeAppId, navItemRegistry, user?.system_roles, workspaceNavItems],
  );
  const categories = useMemo(
    () => buildSidebarCategories(
      filteredItems.map((item) => item.category),
      activeAppId,
      canReadTeams,
    ),
    [activeAppId, canReadTeams, filteredItems],
  );

  useEffect(() => {
    setExpandedCategories(categories);
  }, [categories]);

  useEffect(() => {
    if (activeAppId !== 'pms' || !token) return;
    let cancelled = false;

    setPmsLoading(true);
    setPmsError(null);

    const listRequest = listPmsTaskLists(token)
      .then((response) => {
        if (cancelled) return;
        setPmsTaskLists(response.items);
      });

    const folderRequest = listFolders(token)
      .then((response) => {
        if (cancelled) return;
        setPmsFolders(response.items);
      })
      .catch(() => {
        if (cancelled) return;
        setPmsFolders([]);
      });

    const teamRequest = canReadTeams
      ? listSpaces(token)
          .then((teams) => {
            if (cancelled) return;
            setPmsTeams(Array.isArray(teams) ? teams : []);
          })
          .catch(() => {
            if (cancelled) return;
            setPmsTeams([]);
          })
      : Promise.resolve().then(() => {
          if (cancelled) return;
          setPmsTeams([]);
        });

    Promise.allSettled([listRequest, folderRequest, teamRequest]).finally(() => {
      if (!cancelled) {
        setPmsLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [activeAppId, canReadTeams, token]);

  // Monotonic counter that AIView's `CONVERSATIONS_UPDATED_EVENT` bumps
  // after every persisted turn. `location.search` alone doesn't cover
  // follow-up replies to the currently open conversation — `?c=` stays
  // the same while the server's `updated_at` moves, so the sidebar's
  // recency ordering would otherwise go stale until reload.
  const [aiConversationsRefreshKey, setAiConversationsRefreshKey] = useState(0);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handler = () => {
      setAiConversationsRefreshKey((prev) => prev + 1);
    };
    window.addEventListener(CONVERSATIONS_UPDATED_EVENT, handler);
    return () => {
      window.removeEventListener(CONVERSATIONS_UPDATED_EVENT, handler);
    };
  }, []);

  // Fetch recent AI conversations for the "최근 대화" sidebar section. Refires
  // when the URL search changes (new `?c=` attached) OR when the refresh
  // key bumps from a same-thread reply, so the list stays in sync without
  // a full reload.
  useEffect(() => {
    if (activeAppId !== 'ai' || !token || !currentWorkspaceSlug) {
      setAiConversations([]);
      setAiConversationsError(null);
      return;
    }
    let cancelled = false;
    listConversations(token, { limit: 20 })
      .then((response) => {
        if (cancelled) return;
        setAiConversations(response.items);
        setAiConversationsError(null);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setAiConversations([]);
        setAiConversationsError(
          error instanceof Error
            ? error.message
            : '대화 목록을 불러오지 못했습니다.',
        );
      });
    return () => {
      cancelled = true;
    };
  }, [
    activeAppId,
    aiConversationsRefreshKey,
    currentWorkspaceSlug,
    location.search,
    token,
  ]);

  // Fetch docs sidebar data (favorites + recent pages)
  useEffect(() => {
    if (activeAppId !== 'docs' || !token) return;
    let cancelled = false;
    listFavoriteDocs(token)
      .then((items) => { if (!cancelled) setDocsFavorites(items); })
      .catch(() => { if (!cancelled) setDocsFavorites([]); });
    listRecentPages(token, 5)
      .then((items) => { if (!cancelled) setDocsRecentPages(items); })
      .catch(() => { if (!cancelled) setDocsRecentPages([]); });
    return () => { cancelled = true; };
  }, [activeAppId, token]);

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) => (
      prev.includes(category) ? prev.filter((current) => current !== category) : [...prev, category]
    ));
  };

  const toggleSpace = (spaceId: string) => {
    setExpandedSpaces((prev) => {
      const next = new Set(prev);
      if (next.has(spaceId)) next.delete(spaceId);
      else next.add(spaceId);
      return next;
    });
  };

  const openCreateTaskList = (teamId: string | null) => {
    setCreateTaskListTeamId(teamId);
    setCreateTaskListFolderId(null);
    setCreateTaskListOpen(true);
  };

  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [createFolderTeamId, setCreateFolderTeamId] = useState<string | null>(null);

  const openCreateFolder = (teamId: string) => {
    setCreateFolderTeamId(teamId);
    setCreateFolderOpen(true);
  };

  const handleCreateDoc = useCallback(async (spaceId: string) => {
    if (!token) return;
    const title = await prompt({ title: 'New Document', placeholder: 'Document name', defaultValue: '' });
    if (!title) return;
    try {
      const doc = await createNativeDoc(token, {
        title,
        source_app: 'pms',
        source_kind: 'manual',
        primary_container: {
          app: 'pms',
          type: 'space',
          id: spaceId,
        },
      });
      setSpaceDocsMap((prev) => {
        const next = new Map(prev);
        next.set(spaceId, sortSpaceDocs([...(next.get(spaceId) ?? []), doc]));
        return next;
      });
      navigate(`/tool/pms-space-${spaceId}-docs-${doc.id}`);
    } catch { /* ignore */ }
  }, [navigate, prompt, token]);

  const [spaceDocsMap, setSpaceDocsMap] = useState<Map<string, DocsHubItem[]>>(new Map());

  useEffect(() => {
    if (!token) return;
    for (const team of pmsTeams) {
      if (!teamRoleAllows(team.current_user_role, 'viewer')) {
        continue;
      }
      listDocsHub(token, {
        view: 'all',
        container_app: 'pms',
        container_type: 'space',
        container_id: team.id,
        page_size: 200,
        sort_by: 'container_sort_order',
        sort_dir: 'asc',
      })
        .then((res) => setSpaceDocsMap((prev) => new Map(prev).set(team.id, sortSpaceDocs(res.items))))
        .catch(() => undefined);
    }
  }, [token, pmsTeams]);

  const handleRenameDoc = useCallback(async (docId: string, newTitle: string) => {
    if (!token) return;
    try {
      const updated = await updateDocsItem(token, docId, { title: newTitle });
      const teamId = getSpaceDocSpaceId(updated);
      if (!teamId) return;
      setSpaceDocsMap((prev) => {
        const next = new Map(prev);
        const docs = next.get(teamId) ?? [];
        next.set(teamId, sortSpaceDocs(docs.map((d) => (d.id === updated.id ? updated : d))));
        return next;
      });
    } catch { /* ignore */ }
  }, [token]);

  const handleDeleteDoc = useCallback(async (docId: string) => {
    if (!token) return;
    if (!await confirm({ title: 'Delete Collection', description: 'Move this document collection and all its pages to Trash?', confirmLabel: 'Move to Trash', variant: 'danger' })) return;
    const deletedTeamId = [...spaceDocsMap.entries()].find(([, docs]) => docs.some((doc) => doc.id === docId))?.[0] ?? null;
    try {
      await deleteDocsItem(token, docId);
      setSpaceDocsMap((prev) => {
        const next = new Map(prev);
        for (const [teamId, docs] of next) {
          next.set(teamId, docs.filter((d) => d.id !== docId));
        }
        return next;
      });
      if (deletedTeamId && activeNavItemId === `pms-space-${deletedTeamId}-docs-${docId}`) {
        navigate(`/tool/pms-space-${deletedTeamId}-docs`);
      }
    } catch { /* ignore */ }
  }, [activeNavItemId, navigate, spaceDocsMap, token]);

  const handleSaveSpaceOrder = useCallback(
    async (
      spaceId: string,
      payload: {
        lists: Array<{
          id: string;
          name: string;
          folder_id: string | null;
          sort_order: number;
          issue_count: number;
        }>;
        docs: Array<{
          id: string;
          title: string;
          sort_order: number;
        }>;
      },
    ) => {
      if (!token) return;
      const currentLists = pmsLists.filter((list) => list.team_id === spaceId);
      const currentDocs = spaceDocsMap.get(spaceId) ?? [];
      const listChanges = payload.lists
        .filter((item) => {
          const current = currentLists.find((list) => list.id === item.id);
          return current && ((current.folder_id ?? null) !== item.folder_id || current.sort_order !== item.sort_order);
        })
        .map((item) => ({
          id: item.id,
          folder_id: item.folder_id,
          sort_order: item.sort_order,
        }));
      const docChanges = payload.docs
        .filter((item) => {
          const current = currentDocs.find((doc) => doc.id === item.id);
          return current && getSpaceDocSortOrder(current) !== item.sort_order;
        })
        .map((item) => ({
          id: item.id,
          sort_order: item.sort_order,
        }));

      if (listChanges.length === 0 && docChanges.length === 0) return;

      const nextListMap = new Map(payload.lists.map((item) => [item.id, item]));
      const nextDocMap = new Map(payload.docs.map((item) => [item.id, item]));
      const listSnapshot = pmsLists;
      const docSnapshot = spaceDocsMap;

      setPmsTaskLists((current) => current.map((list) => {
        const next = nextListMap.get(list.id);
        return next ? { ...list, folder_id: next.folder_id, sort_order: next.sort_order } : list;
      }));
      setSpaceDocsMap((current) => {
        const next = new Map(current);
        const docs = (next.get(spaceId) ?? []).map((doc) => {
          const updated = nextDocMap.get(doc.id);
          return updated ? withDocsItemPrimaryContainerSortOrder(doc, updated.sort_order) : doc;
        });
        next.set(spaceId, sortSpaceDocs(docs));
        return next;
      });

      try {
        await Promise.all([
          listChanges.length > 0
            ? reorderPmsTaskLists(token, spaceId, { items: listChanges })
            : Promise.resolve(),
          docChanges.length > 0
            ? Promise.all(
              docChanges.map((item) => updateDocContainer(token, item.id, {
                app: 'pms',
                type: 'space',
                id: spaceId,
                sort_order: item.sort_order,
              })),
            ).then(() => undefined)
            : Promise.resolve(),
        ]);
      } catch (error) {
        setPmsTaskLists(listSnapshot);
        setSpaceDocsMap(docSnapshot);
        throw new Error(getErrorMessage(error, '순서를 저장하지 못했습니다.'));
      }
    },
    [pmsLists, spaceDocsMap, token],
  );

  const handleRenameFolder = useCallback(async (folderId: string, currentName: string) => {
    if (!token) return;
    const newName = await prompt({ title: 'Rename Folder', defaultValue: currentName, placeholder: 'Folder name' });
    if (!newName || newName === currentName) return;
    try {
      const updated = await updateFolder(token, folderId, { name: newName });
      setPmsFolders((current) => current.map((f) => (f.id === updated.id ? updated : f)));
    } catch { /* ignore */ }
  }, [token]);

  const handleReorderDoc = useCallback(
    async (spaceId: string, activeDocId: string, overDocId: string, zone: FlatDropZone) => {
      if (!token) return;
      setPmsError(null);
      const docsInSpace = spaceDocsMap.get(spaceId) ?? [];
      const items = docsInSpace.map((doc) => ({
        id: doc.id,
        parent_id: getSpaceDocSpaceId(doc),
        sort_order: getSpaceDocSortOrder(doc),
        name: doc.title,
      }));
      const target = computeFlatDropTarget(items, overDocId, zone);
      if (!target) return;
      const result = applyFlatReorder(items, activeDocId, target, { allowCrossParent: false });
      if (!result) return;
      const patchMap = new Map(result.nextItems.map((item) => [item.id, item]));
      const snapshot = spaceDocsMap;
      setSpaceDocsMap((prev) => {
        const next = new Map(prev);
        const docs = (next.get(spaceId) ?? []).map((doc) => {
          const p = patchMap.get(doc.id);
          return p ? withDocsItemPrimaryContainerSortOrder(doc, p.sort_order) : doc;
        });
        next.set(spaceId, sortSpaceDocs(docs));
        return next;
      });
      try {
        await Promise.all(
          result.patches.map((patch) => updateDocContainer(token, patch.id, {
            app: 'pms',
            type: 'space',
            id: spaceId,
            sort_order: patch.sort_order,
          })),
        );
      } catch (error) {
        setSpaceDocsMap(snapshot);
        setPmsError(getErrorMessage(error, '문서 순서를 변경하지 못했습니다.'));
      }
    },
    [spaceDocsMap, token],
  );

  const handleReorderList = useCallback(
    async (spaceId: string, activeListId: string, overListId: string, zone: FlatDropZone) => {
      if (!token) return;
      setPmsError(null);
      const listsInSpace = pmsLists.filter((list) => list.team_id === spaceId);
      const items = listsInSpace.map((list) => ({
        id: list.id,
        parent_id: list.folder_id ?? null,
        sort_order: list.sort_order,
        name: list.name,
      }));
      const target = computeFlatDropTarget(items, overListId, zone);
      if (!target) return;
      const result = applyFlatReorder(items, activeListId, target);
      if (!result) return;
      const patchMap = new Map(result.nextItems.map((item) => [item.id, item]));
      const snapshot = pmsLists;
      setPmsTaskLists((current) => current.map((list) => {
        const next = patchMap.get(list.id);
        if (!next) return list;
        return { ...list, sort_order: next.sort_order, folder_id: next.parent_id };
      }));
      try {
        await Promise.all(
          result.patches.map((patch) => updatePmsTaskList(token, patch.id, {
            folder_id: patch.parent_id,
            sort_order: patch.sort_order,
          })),
        );
      } catch (error) {
        setPmsTaskLists(snapshot);
        setPmsError(getErrorMessage(error, '리스트 순서를 변경하지 못했습니다.'));
      }
    },
    [pmsLists, token],
  );

  const handleMoveFolder = useCallback(async (spaceId: string, folderId: string, direction: 'up' | 'down') => {
    if (!token) return;
    setPmsError(null);

    const orderedFolders = pmsFolders
      .filter((folder) => folder.team_id === spaceId)
      .slice()
      .sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name, 'ko'));
    const currentIndex = orderedFolders.findIndex((folder) => folder.id === folderId);
    if (currentIndex < 0) return;

    const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= orderedFolders.length) return;

    const nextOrder = [...orderedFolders];
    const [movedFolder] = nextOrder.splice(currentIndex, 1);
    nextOrder.splice(targetIndex, 0, movedFolder);

    const updates = nextOrder
      .map((folder, index) => ({ folder, sort_order: index }))
      .filter(({ folder, sort_order }) => folder.sort_order !== sort_order);

    if (updates.length === 0) return;

    try {
      const updatedFolders = new Map<string, PmsFolder>();
      for (const { folder, sort_order } of updates) {
        const updated = await updateFolder(token, folder.id, { sort_order });
        updatedFolders.set(updated.id, updated);
      }
      setPmsFolders((current) => current.map((folder) => updatedFolders.get(folder.id) ?? folder));
    } catch (error) {
      setPmsError(getErrorMessage(error, '폴더 순서를 변경하지 못했습니다.'));
    }
  }, [pmsFolders, token]);

  const handleDeleteFolder = useCallback(async (folderId: string) => {
    if (!token) return;
    if (!await confirm({ title: 'Delete Folder', description: 'Delete this folder? Lists inside will be moved to the space root.', confirmLabel: 'Delete', variant: 'danger' })) return;
    try {
      await deleteFolder(token, folderId);
      setPmsFolders((current) => current.filter((f) => f.id !== folderId));
      if (token) listPmsTaskLists(token).then((res) => setPmsTaskLists(res.items)).catch(() => undefined);
    } catch { /* ignore */ }
  }, [token]);

  const handleRenameSpace = useCallback(async (spaceId: string, newName: string) => {
    if (!token) return;
    try {
      const updated = await updateSpace(token, spaceId, { name: newName });
      setPmsTeams((current) => current.map((t) => (t.id === updated.id ? updated : t)));
    } catch { /* ignore */ }
  }, [token]);

  const handleDeleteSpace = useCallback(async (spaceId: string) => {
    if (!token) return;
    if (!await confirm({ title: 'Delete Space', description: 'Move this space and its contents to Trash?', confirmLabel: 'Move to Trash', variant: 'danger' })) return;
    setPmsError(null);
    try {
      await deleteSpace(token, spaceId);
      const activeListInSpace = pmsLists.some((list) => (
        list.team_id === spaceId && activeNavItemId === `pms-list-${list.id}`
      ));
      const activeSpaceRoute = activeNavItemId === `pms-space-${spaceId}`
        || activeNavItemId.startsWith(`pms-space-${spaceId}-docs`);

      setPmsTeams((current) => current.filter((t) => t.id !== spaceId));
      setPmsTaskLists((current) => current.filter((l) => l.team_id !== spaceId));
      setPmsFolders((current) => current.filter((f) => f.team_id !== spaceId));
      setSpaceDocsMap((current) => {
        const next = new Map(current);
        next.delete(spaceId);
        return next;
      });
      knownSpaceIdsRef.current.delete(spaceId);
      setExpandedSpaces((current) => {
        const next = new Set(current);
        next.delete(spaceId);
        return next;
      });

      if (activeSpaceRoute || activeListInSpace) {
        navigate(currentWorkspaceSlug ? buildWorkspaceAppPath(currentWorkspaceSlug, 'pms') : pmsRootPath);
      }
    } catch (error) {
      setPmsError(getErrorMessage(error, '스페이스를 휴지통으로 옮기지 못했습니다.'));
    }
  }, [activeNavItemId, currentWorkspaceSlug, navigate, pmsLists, pmsRootPath, token]);

  const groupedSpaces = useMemo(() => {
    type SpaceGroup = {
      team: PmsSpace;
      rootLists: PmsTaskList[];
      folders: Map<string, FolderWithLists>;
    };

    const folderMap = new Map(pmsFolders.map((folder) => [folder.id, folder]));
    const spaces = new Map<string, SpaceGroup>();

    // Preserve the full PmsSpace object (including ``current_user_role``)
    // so downstream code can evaluate permissions via ``canManageSpace``.
    // Earlier this collector only copied ``{id, name}`` which silently
    // stripped the role and made the "+ / …" context menu disappear for
    // every space, even for its owner.
    for (const team of pmsTeams) {
      spaces.set(team.id, {
        team,
        rootLists: [],
        folders: new Map(),
      });
    }

    function ensureGroup(teamId: string, fallbackName: string): SpaceGroup {
      const existing = spaces.get(teamId);
      if (existing) return existing;
      const placeholder: PmsSpace = {
        id: teamId,
        workspace_id: '',
        workspace_key: '',
        key: '',
        name: fallbackName,
        description: '',
        member_count: 0,
        current_user_role: null,
        created_at: '',
        updated_at: '',
      };
      const created: SpaceGroup = {
        team: placeholder,
        rootLists: [],
        folders: new Map<string, FolderWithLists>(),
      };
      spaces.set(teamId, created);
      return created;
    }

    for (const list of pmsLists) {
      if (!list.team_id) {
        continue;
      }

      const current = ensureGroup(list.team_id, list.team_name ?? 'Untitled Space');
      if (list.folder_id && folderMap.has(list.folder_id)) {
        const folder = folderMap.get(list.folder_id);
        if (folder) {
          const folderEntry = current.folders.get(folder.id) ?? { folder, lists: [] };
          folderEntry.lists.push(list);
          current.folders.set(folder.id, folderEntry);
        } else {
          current.rootLists.push(list);
        }
      } else {
        current.rootLists.push(list);
      }
    }

    for (const folder of pmsFolders) {
      if (!folder.team_id) continue;
      const current = ensureGroup(folder.team_id, 'Untitled Space');
      if (!current.folders.has(folder.id)) {
        current.folders.set(folder.id, { folder, lists: [] });
      }
    }

    const sortByOrderThenName = (left: PmsTaskList, right: PmsTaskList) =>
      left.sort_order - right.sort_order || left.name.localeCompare(right.name, 'ko');

    return Array.from(spaces.values())
      .map((space) => ({
        ...space.team,
        rootLists: [...space.rootLists].sort(sortByOrderThenName),
        folders: Array.from(space.folders.values())
          .map((entry) => ({
            folder: entry.folder,
            lists: [...entry.lists].sort(sortByOrderThenName),
          }))
          .sort((left, right) => left.folder.sort_order - right.folder.sort_order || left.folder.name.localeCompare(right.folder.name, 'ko')),
      }))
      .sort((left, right) => left.name.localeCompare(right.name, 'ko'));
  }, [pmsFolders, pmsLists, pmsTeams]);

  useEffect(() => {
    setExpandedSpaces((current) => {
      const next = new Set(current);
      for (const space of groupedSpaces) {
        if (!knownSpaceIdsRef.current.has(space.id)) {
          knownSpaceIdsRef.current.add(space.id);
          next.add(space.id);
        }
      }
      return next;
    });
  }, [groupedSpaces]);

  if (activeAppId === 'home' || activeAppId === 'profile' || isDocEditor) return null;

  const renderPmsSpaces = () => {
    const isExpanded = expandedCategories.includes('Spaces');

    return (
      <div className="space-y-1">
        <div className="w-full flex items-center justify-between px-3 py-1">
          <button
            onClick={() => toggleCategory('Spaces')}
            className="sidebar-section-label sidebar-section-header group/section flex items-center gap-1"
          >
            {isExpanded ? (
              <ChevronDown size={11} className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white" />
            ) : (
              <ChevronRight size={11} className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white" />
            )}
            <span>Spaces</span>
          </button>
          {canWriteTeams && (
            <button
              onClick={() => setCreateSpaceOpen(true)}
              className="p-1 hover:bg-app-surface-hover rounded text-gray-600 dark:text-gray-300 hover:text-app-ink dark:hover:text-white transition-colors"
              title="Create Space"
            >
              <Plus size={12} />
            </button>
          )}
        </div>

        <AnimatePresence initial={false}>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden space-y-1"
            >
              {pmsLoading ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 size={14} className="animate-spin text-gray-500 dark:text-gray-400" />
                </div>
              ) : (
                <>
                  {pmsError ? (
                    <div className="px-2">
                      <InlineNotice tone="danger">{pmsError}</InlineNotice>
                    </div>
                  ) : null}
                  {groupedSpaces.map((space, index) => {
                    const spaceCanCreate = teamRoleAllows(space.current_user_role, 'member');
                    const spaceCanManage = canManageSpace(space);
                    return (
                      <SpaceItem
                        key={space.id}
                        spaceId={space.id}
                        name={space.name}
                        iconColor={SPACE_COLORS[index % SPACE_COLORS.length]}
                        rootLists={space.rootLists}
                        folders={space.folders}
                        expanded={expandedSpaces.has(space.id)}
                        onToggle={() => toggleSpace(space.id)}
                        onNavigate={() => navigate(`/tool/pms-space-${space.id}`)}
                        onAddList={() => openCreateTaskList(space.id)}
                        onAddListToFolder={(folderId) => { setCreateTaskListTeamId(space.id); setCreateTaskListFolderId(folderId); setCreateTaskListOpen(true); }}
                        onAddFolder={() => openCreateFolder(space.id)}
                        onOpenDocs={() => { void handleCreateDoc(space.id); }}
                        onMoveFolder={(folderId, direction) => { void handleMoveFolder(space.id, folderId, direction); }}
                        onRenameFolder={(folderId, currentName) => { void handleRenameFolder(folderId, currentName); }}
                        onDeleteFolder={(folderId) => { void handleDeleteFolder(folderId); }}
                        onRenameSpace={(newName) => { void handleRenameSpace(space.id, newName); }}
                        onDeleteSpace={() => { void handleDeleteSpace(space.id); }}
                        onManageMembers={() => {
                              setManageMembersSpace({
                                id: space.id,
                                name: space.name,
                                canManage: spaceCanManage,
                                currentUserRole: space.current_user_role,
                              });
                        }}
                        onOpenOrderEditor={() => {
                          setOrderEditorSpace({ id: space.id, name: space.name });
                        }}
                        spaceDocs={spaceDocsMap.get(space.id) ?? []}
                        onRenameDoc={(pageId, newTitle) => { void handleRenameDoc(pageId, newTitle); }}
                        onDeleteDoc={(pageId) => { void handleDeleteDoc(pageId); }}
                        onReorderList={(activeListId, overListId, zone) => handleReorderList(space.id, activeListId, overListId, zone)}
                        onReorderDoc={(activeDocId, overDocId, zone) => handleReorderDoc(space.id, activeDocId, overDocId, zone)}
                        activeNavItemId={activeNavItemId}
                        canCreateSpaceContent={spaceCanCreate}
                        canManageSpace={spaceCanManage}
                        canManageCollections={teamRoleAllows(space.current_user_role, 'admin')}
                      />
                    );
                  })}

                  {canWriteTeams && (
                    <button
                      onClick={() => setCreateSpaceOpen(true)}
                      className="sidebar-submenu-item ml-1 w-full"
                    >
                      <Plus size={13} />
                      <span className="sidebar-submenu-label">New Space</span>
                    </button>
                  )}
                </>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  };

  if (activeAppId === 'home') {
    return null;
  }

  return (
    <>
      {confirmDialog}
      {promptDialog}
      <SpaceOrderEditorModal
        isOpen={orderEditorSpace !== null}
        onClose={() => setOrderEditorSpace(null)}
        spaceName={orderEditorSpace?.name ?? ''}
        folders={pmsFolders.filter((folder) => folder.team_id === orderEditorSpace?.id)}
        lists={pmsLists.filter((list) => list.team_id === orderEditorSpace?.id)}
        docs={orderEditorSpace ? (spaceDocsMap.get(orderEditorSpace.id) ?? []) : []}
        onSave={async (payload) => {
          if (!orderEditorSpace) return;
          await handleSaveSpaceOrder(orderEditorSpace.id, payload);
        }}
      />
      {isCollapsed ? (
        <div className="relative h-full w-10 shrink-0 border-r border-app-border bg-app-surface-sidebar flex flex-col items-center pt-4">
          <button
            type="button"
            onClick={() => setIsCollapsed(false)}
            title="서브 메뉴 펼치기"
            aria-label="서브 메뉴 펼치기"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-accent/15 hover:text-app-accent hover:border-app-accent/40"
          >
            <PanelLeftOpen size={18} />
          </button>
        </div>
      ) : (
      <div
        className="relative h-full bg-app-surface-sidebar border-r border-app-border flex flex-col overflow-hidden shrink-0"
        style={{ width: `${sidebarWidth}px` }}
      >
        <div className="flex items-center justify-between p-4 border-b border-app-border">
          <h2 className="app-text-overline text-gray-600 dark:text-gray-300">
            {activeAppId === 'settings'
              ? 'All settings'
              : workspaceAppRegistry.get(activeAppId)?.title
                ?? APP_BAR_ITEMS.find((item) => item.id === activeAppId)?.title}
          </h2>
          <div className="flex items-center gap-1.5">
          {(activeAppId === 'pms' || activeAppId === 'docs' || activeAppId === 'planner' || activeAppId === 'ai' || activeAppId === 'meeting') ? (
            <div ref={createMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setCreateMenuOpen((open) => !open)}
                title="Create"
                className="flex h-8 w-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-surface-hover"
              >
                <Plus size={16} />
              </button>
              {createMenuOpen ? (
                <div className="absolute right-0 top-full mt-1 z-30 w-52 rounded-lg border border-app-border bg-app-surface py-1 shadow-xl">
                  <div className="app-text-overline px-3 pt-1.5 pb-1 text-gray-500">Create</div>
                  {activeAppId === 'pms' ? (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          setCreateMenuOpen(false);
                          window.dispatchEvent(new CustomEvent('pms:create-task'));
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <CheckSquare size={14} className="text-gray-500" />
                        <span>Task</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setCreateMenuOpen(false);
                          setCreateSpaceOpen(true);
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <Layout size={14} className="text-gray-500" />
                        <span>Space</span>
                      </button>
                    </>
                  ) : null}
                  {activeAppId === 'docs' ? (
                    <button
                      type="button"
                      onClick={() => {
                        setCreateMenuOpen(false);
                        window.dispatchEvent(new CustomEvent('docs:create'));
                      }}
                      className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                    >
                      <FileText size={14} className="text-gray-500" />
                      <span>Doc</span>
                    </button>
                  ) : null}
                  {activeAppId === 'planner' ? (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          setCreateMenuOpen(false);
                          window.dispatchEvent(new CustomEvent('planner:create-event'));
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <Calendar size={14} className="text-gray-500" />
                        <span>Event</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setCreateMenuOpen(false);
                          window.dispatchEvent(new CustomEvent('planner:create-meeting'));
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <Users size={14} className="text-gray-500" />
                        <span>Meeting</span>
                      </button>
                    </>
                  ) : null}
                  {activeAppId === 'ai' ? (
                    <button
                      type="button"
                        onClick={() => {
                          setCreateMenuOpen(false);
                          navigate('/tool/search');
                        }}
                      className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                    >
                      <Sparkles size={14} className="text-gray-500" />
                      <span>Ask AI</span>
                    </button>
                  ) : null}
                  {activeAppId === 'meeting' ? (
                    <button
                      type="button"
                      onClick={() => {
                        setCreateMenuOpen(false);
                        if (window.location.pathname.includes('/meeting')) {
                          window.dispatchEvent(new CustomEvent('meeting:create-event'));
                        } else {
                          navigate(currentWorkspaceSlug ? buildWorkspaceAppPath(currentWorkspaceSlug, 'meeting') : meetingRootPath);
                          // Defer the dispatch until after the route mounts.
                          setTimeout(() => {
                            window.dispatchEvent(new CustomEvent('meeting:create-event'));
                          }, 50);
                        }
                      }}
                      className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                    >
                      <Users size={14} className="text-gray-500" />
                      <span>Meeting</span>
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setIsCollapsed(true)}
            title="서브 메뉴 접기"
            aria-label="서브 메뉴 접기"
            className="flex h-8 w-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-accent/15 hover:text-app-accent hover:border-app-accent/40"
          >
            <PanelLeftClose size={16} />
          </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-4 px-2 space-y-6 custom-scrollbar">
          {activeAppId === 'ai' && currentWorkspaceSlug ? (
            <AiConversationsSection
              conversations={aiConversations}
              error={aiConversationsError}
              activeConversationId={
                new URLSearchParams(location.search).get('c')
              }
              workspaceSlug={currentWorkspaceSlug}
              onSelect={(conversationId) => {
                navigate(
                  `${buildWorkspaceAppPath(
                    currentWorkspaceSlug,
                    'ai',
                  )}?c=${encodeURIComponent(conversationId)}`,
                );
              }}
              onNewConversation={() => {
                navigate(buildWorkspaceAppPath(currentWorkspaceSlug, 'ai'));
              }}
              onDelete={async (conversationId) => {
                if (!token) return;
                const confirmed = await confirm({
                  title: '대화 삭제',
                  description:
                    '이 대화를 삭제하면 목록에서 숨겨집니다. 복구는 관리자만 가능합니다.',
                  confirmLabel: '삭제',
                  variant: 'danger',
                });
                if (!confirmed) return;
                await deleteConversation(token, conversationId);
                setAiConversations((current) =>
                  current.filter((item) => item.id !== conversationId),
                );
                // If the currently open thread is the one we just deleted,
                // fall back to the empty state so the user isn't staring at
                // stale history.
                const activeId = new URLSearchParams(location.search).get('c');
                if (activeId === conversationId) {
                  navigate(buildWorkspaceAppPath(currentWorkspaceSlug, 'ai'));
                }
              }}
            />
          ) : null}
          {categories.map((category) => {
            if (activeAppId === 'pms' && category === 'Spaces') {
              return <div key={category}>{renderPmsSpaces()}</div>;
            }

            return (
              <div key={category} className="space-y-1">
                <button
                  onClick={() => toggleCategory(category)}
                  className="sidebar-section-label sidebar-section-header group/section flex w-full items-center gap-1 px-3 py-1"
                >
                  {expandedCategories.includes(category) ? (
                    <ChevronDown size={11} className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white" />
                  ) : (
                    <ChevronRight size={11} className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white" />
                  )}
                  <span>{category}</span>
                </button>

                <AnimatePresence initial={false}>
                  {expandedCategories.includes(category) && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      {filteredItems.filter((item) => item.category === category).map((item) => {
                        if (activeAppId === 'pms' && category === 'Personal') {
                          if (item.id === 'pms-tasks') {
                            const subTasks = filteredItems.filter((entry) => entry.category === 'Personal' && entry.id.startsWith('pms-tasks-'));
                            const isMyTasksActive = activeNavItemId === 'pms-tasks' || activeNavItemId.startsWith('pms-tasks-');
                            return (
                              <div key={item.id} className="space-y-1">
                                <div className={cn('sidebar-submenu-group ml-1 cursor-default', isMyTasksActive && 'sidebar-submenu-item-active')}>
                                  <item.icon size={16} className={cn('text-gray-500 dark:text-gray-400', isMyTasksActive && 'text-app-accent')} />
                                  <span className="sidebar-submenu-label">{item.title}</span>
                                </div>
                                <div className="ml-6 border-l border-app-border pl-2 space-y-1">
                                  {subTasks.map((sub) => (
                                    <Link
                                      key={sub.id}
                                      to={`/tool/${sub.id}`}
                                      className={cn('sidebar-submenu-item', activeNavItemId === sub.id && 'sidebar-submenu-item-active')}
                                    >
                                      <sub.icon size={14} className="text-gray-500 dark:text-gray-400" />
                                      <span className="sidebar-submenu-label">{sub.title}</span>
                                    </Link>
                                  ))}
                                </div>
                              </div>
                            );
                          }
                          if (item.id.startsWith('pms-tasks-')) return null;
                        }

                        return (
                          <Link
                            key={item.id}
                            to={resolveNavItemHref(item, currentWorkspaceSlug, user)}
                            className={cn('sidebar-submenu-item ml-1', activeNavItemId === item.id && 'sidebar-submenu-item-active')}
                          >
                            <item.icon size={16} className="text-gray-500 dark:text-gray-400" />
                            <span className="sidebar-submenu-label">{item.title}</span>
                          </Link>
                        );
                      })}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}

          {/* Docs sidebar extras: Favorites + Recent Pages */}
          {activeAppId === 'docs' && (
            <>
              <div className="space-y-1 pt-2 border-t border-app-border mt-2">
                <span className="sidebar-section-label block px-3 py-1 text-gray-500">Favorites</span>
                {docsFavorites.length > 0 ? (
                  docsFavorites.map((fav) => (
                    (() => {
                      const docPath = currentWorkspaceSlug
                        ? buildWorkspaceAppPath(currentWorkspaceSlug, 'docs', `/${fav.id}`)
                        : resolveDefaultWorkspaceAppPath(user, 'docs', `/${fav.id}`);
                      return (
                        <Link
                          key={fav.id}
                          to={docPath}
                          className={cn('sidebar-submenu-item ml-1', location.pathname === docPath && 'sidebar-submenu-item-active')}
                        >
                          <FileText size={14} className="text-yellow-500" />
                          <span className="sidebar-submenu-label truncate">{fav.title}</span>
                        </Link>
                      );
                    })()
                  ))
                ) : (
                  <div className="px-3 py-2 text-center">
                    <span className="app-text-micro text-gray-600">Star a Doc to see it here</span>
                  </div>
                )}
              </div>

              <div className="space-y-1 pt-2 border-t border-app-border mt-2">
                <span className="sidebar-section-label block px-3 py-1 text-gray-500">Recent Pages</span>
                {docsRecentPages.length > 0 ? (
                  docsRecentPages.map((rp) => (
                    (() => {
                      const docPath = currentWorkspaceSlug
                        ? buildWorkspaceAppPath(currentWorkspaceSlug, 'docs', `/${rp.doc_id}`)
                        : resolveDefaultWorkspaceAppPath(user, 'docs', `/${rp.doc_id}`);
                      return (
                        <Link
                          key={rp.page_id}
                          to={docPath}
                          className="sidebar-submenu-item ml-1"
                        >
                          <FileText size={14} className="text-gray-500" />
                          <span className="sidebar-submenu-label truncate">{rp.page_title}</span>
                        </Link>
                      );
                    })()
                  ))
                ) : (
                  <div className="px-3 py-2 text-center">
                    <span className="app-text-micro text-gray-600">No recent pages</span>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Resize handle */}
        <div
          onMouseDown={(e) => { e.preventDefault(); setIsResizing(true); }}
          className={cn(
            'absolute right-0 top-0 h-full w-1 cursor-col-resize transition-colors hover:bg-app-accent/30',
            isResizing && 'bg-app-accent/50',
          )}
          title="Drag to resize"
        />
      </div>
      )}

      <CreateTaskListModal
        isOpen={createTaskListOpen}
        onClose={() => setCreateTaskListOpen(false)}
        teamId={createTaskListTeamId}
        folderId={createTaskListFolderId}
        onCreated={(list) => {
          setPmsTaskLists((current) => upsertList(current, list));
          const teamId = list.team_id;
          if (teamId) {
            knownSpaceIdsRef.current.add(teamId);
            setExpandedSpaces((current) => {
              const next = new Set(current);
              next.add(teamId);
              return next;
            });
          }
          navigate(`/tool/pms-list-${list.id}`);
        }}
      />

      <CreateSpaceModal
        isOpen={createSpaceOpen}
        onClose={() => setCreateSpaceOpen(false)}
        onCreated={(space) => {
          knownSpaceIdsRef.current.add(space.id);
          setPmsTeams((current) => upsertSpace(current, space));
          setExpandedSpaces((current) => new Set(current).add(space.id));
        }}
      />

      <SpaceMembersModal
        isOpen={manageMembersSpace !== null}
        onClose={() => setManageMembersSpace(null)}
        spaceId={manageMembersSpace?.id ?? null}
        spaceName={manageMembersSpace?.name ?? ''}
        canManage={manageMembersSpace?.canManage ?? false}
        currentUserRole={manageMembersSpace?.currentUserRole ?? null}
        onChanged={() => {
          if (token) {
            listSpaces(token)
              .then((teams) => {
                if (Array.isArray(teams)) setPmsTeams(teams);
              })
              .catch(() => undefined);
          }
        }}
      />

      {createFolderTeamId && (
        <CreateFolderModal
          isOpen={createFolderOpen}
          onClose={() => setCreateFolderOpen(false)}
          teamId={createFolderTeamId}
          onCreated={(folder) => {
            setPmsFolders((current) => [...current, folder]);
            if (token) {
              listPmsTaskLists(token).then((res) => setPmsTaskLists(res.items)).catch(() => undefined);
            }
          }}
        />
      )}
    </>
  );
};
