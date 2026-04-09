import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Plus,
  Layout,
  Loader2,
  List as ListIcon,
  FolderOpen,
  FileText,
  MoreHorizontal,
  Pencil,
  Trash2,
} from 'lucide-react';
import { InlineNotice, useConfirm, usePrompt } from '@aidoo/ui';
import { cn } from '@/src/lib/utils';
import { NAV_ITEMS, APP_BAR_ITEMS } from '@/src/constants';
import { hasAdminSectionAccess, type AdminSection } from '@/src/domains/admin/admin-permissions';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { hasAppAccess, teamRoleAllows } from '@/src/domains/auth/auth-api';
import { listFavoriteDocs, listRecentPages, type FavoriteDocItem, type RecentPageItem } from '@/src/domains/docs/docs-api';
import { listPmsLists, listFolders, listSpaceDocs, createSpaceDoc, updateSpaceDoc, deleteSpaceDoc, updateFolder, deleteFolder, listSpaces, updateSpace, deleteSpace, type PmsFolder, type PmsList, type PmsSpace, type PmsSpaceDoc } from '@/src/domains/pms/pms-api';
import { CreateProjectModal } from '@/src/components/views/PMSView/CreateProjectModal';
import { CreateSpaceModal } from '@/src/components/views/PMSView/CreateSpaceModal';
import { CreateFolderModal } from '@/src/components/views/PMSView/CreateFolderModal';
import { buildSidebarCategories } from './sub-sidebar-categories';

const SPACE_COLORS = [
  'bg-emerald-500',
  'bg-blue-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-violet-500',
];

function upsertList(lists: PmsList[], item: PmsList): PmsList[] {
  return [item, ...lists.filter((current) => current.id !== item.id)].sort(
    (left, right) => right.updated_at.localeCompare(left.updated_at),
  );
}

function upsertSpace(spaces: PmsSpace[], space: PmsSpace): PmsSpace[] {
  return [space, ...spaces.filter((item) => item.id !== space.id)].sort(
    (left, right) => left.name.localeCompare(right.name, 'ko'),
  );
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
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
      className="fixed z-[9999] w-52 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1"
    >
      <div className="app-text-overline px-3 py-1.5 text-gray-500">
        Create
      </div>
      <button
        onClick={() => { onCreateList(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
      >
        <ListIcon size={16} className="text-gray-400" />
        <div className="text-left">
          <div className="app-text-control-sm text-clickup-text">List</div>
          <div className="app-text-micro text-clickup-text/40">Track tasks, projects, people & more</div>
        </div>
      </button>
      <button
        onClick={() => { onCreateFolder(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
      >
        <FolderOpen size={16} className="text-gray-400" />
        <div className="text-left">
          <div className="app-text-control-sm text-clickup-text">Folder</div>
          <div className="app-text-micro text-clickup-text/40">Group Lists, Docs & more</div>
        </div>
      </button>
      <button
        onClick={() => { onOpenDocs(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
      >
        <FileText size={16} className="text-gray-400" />
        <div className="text-left">
          <div className="app-text-control-sm text-clickup-text">Doc</div>
          <div className="app-text-micro text-clickup-text/40">Write and organize documents</div>
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
      className="fixed z-[9999] w-48 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1"
    >
      <div className="app-text-overline px-3 py-1.5 text-gray-500">
        Create
      </div>
      <button
        onClick={() => { onCreateList(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
      >
        <ListIcon size={14} className="text-gray-400" />
        <div className="app-text-control-sm text-clickup-text">List</div>
      </button>
      <button
        onClick={() => { onCreateDoc(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
      >
        <FileText size={14} className="text-gray-400" />
        <div className="app-text-control-sm text-clickup-text">Doc</div>
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
      className="fixed z-[9999] w-44 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1"
    >
      {onMoveUp ? (
        <button
          onClick={() => { onMoveUp(); onClose(); }}
          disabled={!canMoveUp}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowUp size={14} className="text-gray-400" />
          <span className="app-text-control-sm text-clickup-text">Move Up</span>
        </button>
      ) : null}
      {onMoveDown ? (
        <button
          onClick={() => { onMoveDown(); onClose(); }}
          disabled={!canMoveDown}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowDown size={14} className="text-gray-400" />
          <span className="app-text-control-sm text-clickup-text">Move Down</span>
        </button>
      ) : null}
      <button
        onClick={() => { onRename(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
      >
        <Pencil size={14} className="text-gray-400" />
        <span className="app-text-control-sm text-clickup-text">Rename</span>
      </button>
      <button
        onClick={() => { onDelete(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
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
  onDelete,
}: {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
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
      className="fixed z-[9999] w-44 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1"
    >
      <button
        onClick={() => { onRename(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
      >
        <Pencil size={14} className="text-gray-400" />
        <span className="app-text-control-sm text-clickup-text">Rename</span>
      </button>
      <button
        onClick={() => { onDelete(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
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
  lists: PmsList[];
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
  spaceDocs,
  onRenameDoc,
  onDeleteDoc,
  activeNavItemId,
  canManageSpace,
  canManageCollections,
}: {
  spaceId: string;
  name: string;
  iconColor: string;
  rootLists: PmsList[];
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
  spaceDocs: PmsSpaceDoc[];
  onRenameDoc: (docId: string, newTitle: string) => void;
  onDeleteDoc: (docId: string) => void;
  activeNavItemId: string;
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

  type SidebarRootItem =
    | { kind: 'list'; id: string; name: string; issueCount: number }
    | { kind: 'doc'; id: string; title: string };

  const rootItems: SidebarRootItem[] = useMemo(() => {
    const listItems: SidebarRootItem[] = rootLists.map((list) => ({
      kind: 'list', id: list.id, name: list.name, issueCount: list.issue_count,
    }));
    const docItems: SidebarRootItem[] = spaceDocs.map((doc) => ({
      kind: 'doc', id: doc.id, title: doc.title,
    }));
    return [...listItems, ...docItems].sort((a, b) => {
      const nameA = a.kind === 'list' ? a.name : a.title;
      const nameB = b.kind === 'list' ? b.name : b.title;
      return nameA.localeCompare(nameB, 'ko');
    });
  }, [rootLists, spaceDocs]);

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

  return (
    <div className="space-y-0.5">
      <div className="group relative flex items-center gap-1">
        <div
          className={cn(
            'flex min-w-0 flex-1 items-center gap-1 rounded-md transition-colors',
            spaceActive ? 'bg-clickup-hover' : 'hover:bg-clickup-hover',
          )}
        >
          <button
            onClick={onToggle}
            className={cn(
              'ml-1 flex h-7 w-6 shrink-0 items-center justify-center rounded transition-colors',
              spaceActive ? 'text-clickup-text/50' : 'text-gray-600 dark:text-gray-300 hover:text-clickup-text dark:hover:text-white',
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
                className="app-text-control-sm flex-1 min-w-0 rounded border border-blue-500 bg-transparent px-1 py-0.5 text-clickup-text outline-none"
                autoFocus
              />
            </div>
          ) : (
            <button
              onClick={() => { if (!expanded) onToggle(); onNavigate(); }}
              className={cn(
                'flex min-w-0 flex-1 items-center gap-2 py-1.5 pl-0.5 pr-2 text-left',
                spaceActive ? 'text-clickup-text' : 'text-gray-600 dark:text-gray-300 group-hover:text-clickup-text dark:group-hover:text-white',
              )}
            >
              <div className={cn('h-5 w-5 shrink-0 rounded flex items-center justify-center', iconColor)}>
                <Layout size={12} className="text-white" />
              </div>
              <span className={cn('app-text-control-sm truncate', spaceActive && 'font-medium')}>{name}</span>
            </button>
          )}
        </div>

        {canManageSpace ? (
          <>
            <div className={cn('items-center gap-0.5 pr-1 shrink-0', addPopoverOpen || spaceMenuOpen ? 'flex' : 'hidden group-hover:flex')}>
              <button
                ref={spaceMenuBtnRef}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setSpaceMenuOpen((current) => !current);
                }}
                className="p-0.5 hover:bg-clickup-hover rounded text-gray-600 dark:text-gray-300 hover:text-clickup-text dark:hover:text-white transition-colors"
                title="More"
              >
                <MoreHorizontal size={14} />
              </button>
              <button
                ref={addBtnRef}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setAddPopoverOpen((current) => !current);
                }}
                className="p-0.5 hover:bg-clickup-hover rounded text-gray-600 dark:text-gray-300 hover:text-clickup-text dark:hover:text-white transition-colors"
                title="Add"
              >
                <Plus size={14} />
              </button>
            </div>

            <SpaceContextMenu
              open={spaceMenuOpen}
              anchorRef={spaceMenuBtnRef}
              onClose={() => setSpaceMenuOpen(false)}
              onRename={() => { setRenameValue(name); setRenaming(true); }}
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
            <div className="ml-4 pl-3 border-l border-clickup-border space-y-1">
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
                      {canManageSpace ? (
                        <>
                          <div className={cn('items-center gap-0.5 pr-1 shrink-0', hasAnyPopup ? 'flex' : 'hidden group-hover/folder:flex')}>
                            <button
                              ref={(el) => { if (el) folderMenuBtnRefs.current.set(folder.id, el); }}
                              onClick={(event) => {
                                event.stopPropagation();
                                setFolderMenuOpen((current) => (current === folder.id ? null : folder.id));
                              }}
                              className="p-0.5 hover:bg-clickup-hover rounded text-gray-600 dark:text-gray-300 hover:text-clickup-text dark:hover:text-white transition-colors"
                              title="Folder options"
                            >
                              <MoreHorizontal size={12} />
                            </button>
                            <button
                              ref={(el) => { if (el) folderAddBtnRefs.current.set(folder.id, el); }}
                              onClick={(event) => {
                                event.stopPropagation();
                                setFolderPopoverOpen((current) => (current === folder.id ? null : folder.id));
                              }}
                              className="p-0.5 hover:bg-clickup-hover rounded text-gray-600 dark:text-gray-300 hover:text-clickup-text dark:hover:text-white transition-colors"
                              title="Add to folder"
                            >
                              <Plus size={12} />
                            </button>
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
                              <Link
                                key={list.id}
                                to={`/tool/pms-list-${list.id}`}
                                className={cn(
                                  'sidebar-submenu-item',
                                  activeNavItemId === `pms-list-${list.id}` && 'sidebar-submenu-item-active',
                                )}
                              >
                                <ListIcon size={13} className="text-gray-500 shrink-0" />
                                <span className="sidebar-submenu-label">{list.name}</span>
                                <span className="sidebar-submenu-meta">
                                  ({list.issue_count})
                                </span>
                              </Link>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })}

              {rootItems.map((item) => {
                if (item.kind === 'list') {
                  return (
                    <Link
                      key={`list-${item.id}`}
                      to={`/tool/pms-list-${item.id}`}
                      className={cn(
                        'sidebar-submenu-item',
                        activeNavItemId === `pms-list-${item.id}` && 'sidebar-submenu-item-active',
                      )}
                    >
                      <ListIcon size={13} className="text-gray-500 shrink-0" />
                      <span className="sidebar-submenu-label">{item.name}</span>
                      <span className="sidebar-submenu-meta">
                        ({item.issueCount})
                      </span>
                    </Link>
                  );
                }
                const docNavId = `pms-space-${spaceId}-docs-${item.id}`;
                const isDocMenuOpen = docMenuOpen === item.id;
                const isDocRenaming = renamingDocId === item.id;
                return (
                  <div key={`doc-${item.id}`} className="group/doc flex items-center">
                    {isDocRenaming ? (
                      <div className="sidebar-submenu-item flex-1 min-w-0">
                        <FileText size={13} className="text-gray-500 shrink-0" />
                        <input
                          ref={docRenameInputRef}
                          value={docRenameValue}
                          onChange={(e) => setDocRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              const trimmed = docRenameValue.trim();
                              if (trimmed && trimmed !== item.title) onRenameDoc(item.id, trimmed);
                              setRenamingDocId(null);
                            } else if (e.key === 'Escape') {
                              setRenamingDocId(null);
                            }
                          }}
                          onBlur={() => {
                            const trimmed = docRenameValue.trim();
                            if (trimmed && trimmed !== item.title) onRenameDoc(item.id, trimmed);
                            setRenamingDocId(null);
                          }}
                          className="app-text-body-sm flex-1 min-w-0 rounded border border-blue-500 bg-transparent px-1 py-0.5 text-clickup-text outline-none"
                          autoFocus
                        />
                      </div>
                    ) : (
                      <Link
                        to={`/tool/${docNavId}`}
                        className={cn('sidebar-submenu-item flex-1 min-w-0', activeNavItemId === docNavId && 'sidebar-submenu-item-active')}
                      >
                        <FileText size={13} className="text-gray-500 shrink-0" />
                        <span className="sidebar-submenu-label">{item.title || 'Untitled'}</span>
                      </Link>
                    )}
                    {canManageCollections ? (
                      <>
                        <div className={cn('items-center gap-0.5 pr-1 shrink-0', isDocMenuOpen ? 'flex' : 'hidden group-hover/doc:flex')}>
                          <button
                            ref={(el) => { if (el) docMenuBtnRefs.current.set(item.id, el); }}
                            onClick={(e) => {
                              e.stopPropagation();
                              setDocMenuOpen((c) => (c === item.id ? null : item.id));
                            }}
                            className="p-0.5 hover:bg-clickup-hover rounded text-gray-600 dark:text-gray-300 hover:text-clickup-text dark:hover:text-white transition-colors"
                            title="Doc options"
                          >
                            <MoreHorizontal size={12} />
                          </button>
                        </div>
                        <FolderContextMenu
                          open={isDocMenuOpen}
                          anchorRef={{ current: docMenuBtnRefs.current.get(item.id) ?? null }}
                          onClose={() => setDocMenuOpen(null)}
                          onRename={() => { setDocRenameValue(item.title); setRenamingDocId(item.id); }}
                          onDelete={() => onDeleteDoc(item.id)}
                        />
                      </>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export const SubSidebar = ({ activeAppId, activeNavItemId }: { activeAppId: string, activeNavItemId: string }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();
  const isSpaceDocs = /^\/tool\/pms-space-[0-9a-f-]+-docs/.test(location.pathname);
  const isDocEditor = !isSpaceDocs && (
    location.pathname.match(/^\/tool\/[^/]+\/[^/]+$/)
    || location.pathname.match(/^\/docs\/[^/]+$/)
    || location.pathname.match(/^\/docs\/shared\/[^/]+$/)
  );
  const canReadTeams = hasAppAccess(user, 'pms');
  const canWriteTeams = hasAppAccess(user, 'pms');
  const canManageSpace = useCallback(
    (team: PmsSpace) => teamRoleAllows(team.current_user_role, 'admin'),
    [],
  );

  const [expandedCategories, setExpandedCategories] = useState<string[]>([]);
  const [pmsLists, setPmsLists] = useState<PmsList[]>([]);
  const [pmsFolders, setPmsFolders] = useState<PmsFolder[]>([]);
  const [pmsTeams, setPmsTeams] = useState<PmsSpace[]>([]);
  const [pmsLoading, setPmsLoading] = useState(false);
  const [pmsError, setPmsError] = useState<string | null>(null);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [createProjectTeamId, setCreateProjectTeamId] = useState<string | null>(null);
  const [createProjectFolderId, setCreateProjectFolderId] = useState<string | null>(null);
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [expandedSpaces, setExpandedSpaces] = useState<Set<string>>(new Set());
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

  const filteredItems = useMemo(
    () => {
      const items = NAV_ITEMS.filter((item) => item.appId === activeAppId);
      if (activeAppId !== 'settings') {
        return items;
      }

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
    [activeAppId, user?.system_roles],
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

    const listRequest = listPmsLists(token)
      .then((response) => {
        if (cancelled) return;
        setPmsLists(response.items);
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

  const openCreateProject = (teamId: string | null) => {
    setCreateProjectTeamId(teamId);
    setCreateProjectFolderId(null);
    setCreateProjectOpen(true);
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
      const doc = await createSpaceDoc(token, spaceId, { title });
      setSpaceDocsMap((prev) => {
        const next = new Map(prev);
        next.set(spaceId, [...(next.get(spaceId) ?? []), doc]);
        return next;
      });
      navigate(`/tool/pms-space-${spaceId}-docs-${doc.id}`);
    } catch { /* ignore */ }
  }, [navigate, prompt, token]);

  const [spaceDocsMap, setSpaceDocsMap] = useState<Map<string, PmsSpaceDoc[]>>(new Map());

  useEffect(() => {
    if (!token) return;
    for (const team of pmsTeams) {
      if (!teamRoleAllows(team.current_user_role, 'viewer')) {
        continue;
      }
      listSpaceDocs(token, team.id)
        .then((res) => setSpaceDocsMap((prev) => new Map(prev).set(team.id, res.items)))
        .catch(() => undefined);
    }
  }, [token, pmsTeams]);

  const handleRenameDoc = useCallback(async (docId: string, newTitle: string) => {
    if (!token) return;
    try {
      const updated = await updateSpaceDoc(token, docId, { title: newTitle });
      setSpaceDocsMap((prev) => {
        const next = new Map(prev);
        const docs = next.get(updated.team_id) ?? [];
        next.set(updated.team_id, docs.map((d) => (d.id === updated.id ? updated : d)));
        return next;
      });
    } catch { /* ignore */ }
  }, [token]);

  const handleDeleteDoc = useCallback(async (docId: string) => {
    if (!token) return;
    if (!await confirm({ title: 'Delete Collection', description: 'Move this document collection and all its pages to Trash?', confirmLabel: 'Move to Trash', variant: 'danger' })) return;
    const deletedTeamId = [...spaceDocsMap.entries()].find(([, docs]) => docs.some((doc) => doc.id === docId))?.[0] ?? null;
    try {
      await deleteSpaceDoc(token, docId);
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

  const handleRenameFolder = useCallback(async (folderId: string, currentName: string) => {
    if (!token) return;
    const newName = await prompt({ title: 'Rename Folder', defaultValue: currentName, placeholder: 'Folder name' });
    if (!newName || newName === currentName) return;
    try {
      const updated = await updateFolder(token, folderId, { name: newName });
      setPmsFolders((current) => current.map((f) => (f.id === updated.id ? updated : f)));
    } catch { /* ignore */ }
  }, [token]);

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
      if (token) listPmsLists(token).then((res) => setPmsLists(res.items)).catch(() => undefined);
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
      setPmsLists((current) => current.filter((l) => l.team_id !== spaceId));
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
        navigate('/pms');
      }
    } catch (error) {
      setPmsError(getErrorMessage(error, '스페이스를 휴지통으로 옮기지 못했습니다.'));
    }
  }, [activeNavItemId, navigate, pmsLists, token]);

  const groupedSpaces = useMemo(() => {
    const folderMap = new Map(pmsFolders.map((folder) => [folder.id, folder]));
    const spaces = new Map<string, { id: string; name: string; rootLists: PmsList[]; folders: Map<string, FolderWithLists> }>();

    for (const team of pmsTeams) {
      spaces.set(team.id, {
        id: team.id,
        name: team.name,
        rootLists: [],
        folders: new Map(),
      });
    }

    for (const list of pmsLists) {
      if (!list.team_id) {
        continue;
      }

      const current = spaces.get(list.team_id) ?? {
        id: list.team_id,
        name: list.team_name ?? 'Untitled Space',
        rootLists: [],
        folders: new Map<string, FolderWithLists>(),
      };
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

      spaces.set(current.id, current);
    }

    for (const folder of pmsFolders) {
      if (!folder.team_id) continue;
      const current = spaces.get(folder.team_id) ?? {
        id: folder.team_id,
        name: 'Untitled Space',
        rootLists: [],
        folders: new Map<string, FolderWithLists>(),
      };
      if (!current.folders.has(folder.id)) {
        current.folders.set(folder.id, { folder, lists: [] });
      }
      spaces.set(current.id, current);
    }

    return Array.from(spaces.values())
      .map((space) => ({
        id: space.id,
        name: space.name,
        rootLists: [...space.rootLists].sort((left, right) => left.name.localeCompare(right.name, 'ko')),
        folders: Array.from(space.folders.values())
          .map((entry) => ({
            folder: entry.folder,
            lists: [...entry.lists].sort((left, right) => left.name.localeCompare(right.name, 'ko')),
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
              <ChevronDown size={11} className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-clickup-text dark:group-hover/section:text-white" />
            ) : (
              <ChevronRight size={11} className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-clickup-text dark:group-hover/section:text-white" />
            )}
            <span>Spaces</span>
          </button>
          {canWriteTeams && (
            <button
              onClick={() => setCreateSpaceOpen(true)}
              className="p-1 hover:bg-clickup-hover rounded text-gray-600 dark:text-gray-300 hover:text-clickup-text dark:hover:text-white transition-colors"
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
                  {groupedSpaces.map((space, index) => (
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
                      onAddList={() => openCreateProject(space.id)}
                      onAddListToFolder={(folderId) => { setCreateProjectTeamId(space.id); setCreateProjectFolderId(folderId); setCreateProjectOpen(true); }}
                      onAddFolder={() => openCreateFolder(space.id)}
                      onOpenDocs={() => { void handleCreateDoc(space.id); }}
                      onMoveFolder={(folderId, direction) => { void handleMoveFolder(space.id, folderId, direction); }}
                      onRenameFolder={(folderId, currentName) => { void handleRenameFolder(folderId, currentName); }}
                      onDeleteFolder={(folderId) => { void handleDeleteFolder(folderId); }}
                      onRenameSpace={(newName) => { void handleRenameSpace(space.id, newName); }}
                      onDeleteSpace={() => { void handleDeleteSpace(space.id); }}
                      spaceDocs={spaceDocsMap.get(space.id) ?? []}
                      onRenameDoc={(pageId, newTitle) => { void handleRenameDoc(pageId, newTitle); }}
                      onDeleteDoc={(pageId) => { void handleDeleteDoc(pageId); }}
                      activeNavItemId={activeNavItemId}
                      canManageSpace={canManageSpace(space)}
                      canManageCollections={teamRoleAllows(space.current_user_role, 'admin')}
                    />
                  ))}

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

  return (
    <>
      {confirmDialog}
      {promptDialog}
      <div
        className="relative h-full bg-clickup-sidebar border-r border-clickup-border flex flex-col overflow-hidden shrink-0"
        style={{ width: `${sidebarWidth}px` }}
      >
        <div className="p-4 border-b border-clickup-border">
          <h2 className="app-text-overline text-gray-600 dark:text-gray-300">
            {activeAppId === 'settings' ? 'All settings' : APP_BAR_ITEMS.find((item) => item.id === activeAppId)?.title}
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto py-4 px-2 space-y-6 custom-scrollbar">
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
                    <ChevronDown size={11} className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-clickup-text dark:group-hover/section:text-white" />
                  ) : (
                    <ChevronRight size={11} className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-clickup-text dark:group-hover/section:text-white" />
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
                                  <item.icon size={16} className={cn('text-gray-500 dark:text-gray-400', isMyTasksActive && 'text-clickup-purple')} />
                                  <span className="sidebar-submenu-label">{item.title}</span>
                                </div>
                                <div className="ml-6 border-l border-clickup-border pl-2 space-y-1">
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
                            to={item.path ?? `/tool/${item.id}`}
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
              <div className="space-y-1 pt-2 border-t border-clickup-border mt-2">
                <span className="sidebar-section-label block px-3 py-1 text-gray-500">Favorites</span>
                {docsFavorites.length > 0 ? (
                  docsFavorites.map((fav) => (
                    <Link
                      key={fav.id}
                      to={`/docs/${fav.id}`}
                      className={cn('sidebar-submenu-item ml-1', location.pathname === `/docs/${fav.id}` && 'sidebar-submenu-item-active')}
                    >
                      <FileText size={14} className="text-yellow-500" />
                      <span className="sidebar-submenu-label truncate">{fav.title}</span>
                    </Link>
                  ))
                ) : (
                  <div className="px-3 py-2 text-center">
                    <span className="app-text-micro text-gray-600">Star a Doc to see it here</span>
                  </div>
                )}
              </div>

              <div className="space-y-1 pt-2 border-t border-clickup-border mt-2">
                <span className="sidebar-section-label block px-3 py-1 text-gray-500">Recent Pages</span>
                {docsRecentPages.length > 0 ? (
                  docsRecentPages.map((rp) => (
                    <Link
                      key={rp.page_id}
                      to={`/docs/${rp.doc_id}`}
                      className="sidebar-submenu-item ml-1"
                    >
                      <FileText size={14} className="text-gray-500" />
                      <span className="sidebar-submenu-label truncate">{rp.page_title}</span>
                    </Link>
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

        {activeAppId !== 'settings' && activeAppId !== 'docs' && (
          <div className="p-4 border-t border-clickup-border">
            <button
              onClick={() => openCreateProject(null)}
              className="app-text-control flex w-full items-center gap-2 rounded-md bg-clickup-purple px-3 py-2 text-clickup-bg transition-all hover:bg-opacity-90"
            >
              <Plus size={18} />
              <span>Quick Add</span>
            </button>
          </div>
        )}

        {/* Resize handle */}
        <div
          onMouseDown={(e) => { e.preventDefault(); setIsResizing(true); }}
          className={cn(
            'absolute right-0 top-0 h-full w-1 cursor-col-resize transition-colors hover:bg-clickup-purple/30',
            isResizing && 'bg-clickup-purple/50',
          )}
          title="Drag to resize"
        />
      </div>

      <CreateProjectModal
        isOpen={createProjectOpen}
        onClose={() => setCreateProjectOpen(false)}
        teamId={createProjectTeamId}
        folderId={createProjectFolderId}
        onCreated={(list) => {
          setPmsLists((current) => upsertList(current, list));
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

      {createFolderTeamId && (
        <CreateFolderModal
          isOpen={createFolderOpen}
          onClose={() => setCreateFolderOpen(false)}
          teamId={createFolderTeamId}
          onCreated={(folder) => {
            setPmsFolders((current) => [...current, folder]);
            if (token) {
              listPmsLists(token).then((res) => setPmsLists(res.items)).catch(() => undefined);
            }
          }}
        />
      )}
    </>
  );
};
