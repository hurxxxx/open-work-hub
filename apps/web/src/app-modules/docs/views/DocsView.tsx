import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink,
  FileText,
  Filter,
  Globe,
  Link2,
  Loader2,
  Lock,
  MoreHorizontal,
  Pencil,
  Plus,
  Printer,
  Search,
  Share2,
  Sparkles,
  Star,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { BlockEditor, BlockViewer, CollaborativeBlockEditor, useConfirm, usePrompt } from '@aidoo/ui';
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasWorkspaceMembership } from '@/src/platform/auth/auth-api';
import { formatRelativeTime, normalizeTimeZone } from '@/src/platform/time/time-utils';
import { cn } from '@/src/lib/utils';
import {
  createDocPage,
  createNativeDoc,
  deleteDocPage,
  deleteDocsItem,
  deleteDocLinkShare,
  deleteDocUserShare,
  deleteDocContainer,
  duplicateDocsItem,
  getDocsCollabSession,
  getDocsItem,
  getDocSharing,
  listDocPages,
  listDocsHub,
  makeDocsPageRef,
  mediaResourceTypeForDocsPage,
  listShareableUsers,
  recordDocView,
  resolveSharedLink,
  toggleDocFavorite,
  updateDocContainer,
  updateDocPage,
  updateDocsItem,
  upsertDocLinkShare,
  upsertDocUserShare,
  type DocsHubItem,
  type DocsPageItem,
  type NativeDocSharingResponse,
  type ShareableUserItem,
} from '../api/docs-api';
import {
  applyReorder,
  collectDescendantIds,
  computeDropTarget,
  flattenVisibleTree,
  resolveDropZone,
  type DropZone,
} from '../api/docs-page-reorder';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import { listSpaces, type PmsSpace } from '@/src/app-modules/pms/public-api';

const CATEGORY_MAP: Record<string, string> = {
  'docs-all': 'all',
  'docs-my': 'mine',
  'docs-shared': 'shared',
  'docs-private': 'private',
  'docs-notes': 'meeting_notes',
  'docs-recent': 'recent',
  'docs-archived': 'archived',
};

const CATEGORY_LABELS: Record<string, string> = {
  'docs-all': 'All Docs',
  'docs-my': 'My Docs',
  'docs-shared': 'Shared with me',
  'docs-private': 'Private',
  'docs-notes': 'Meeting Notes',
  'docs-recent': 'Recent Pages',
  'docs-archived': 'Archived',
};

const VIEW_LABELS: Record<string, string> = {
  all: 'All Docs',
  mine: 'Created by me',
  shared: 'Shared with me',
  private: 'Private',
  meeting_notes: 'Meeting Notes',
  recent: 'Recent Pages',
  archived: 'Archived',
};

const TEMPLATES = [
  { title: 'Project Overview', desc: 'Summarize goals, scope, and milestones', icon: '📋' },
  { title: 'Meeting Notes', desc: 'Capture an agenda, notes, and action items', icon: '📝' },
  { title: 'Wiki', desc: 'Organize information in one place', icon: '📚' },
];

interface DocsPageTreeNodeProps {
  page: DocsPageItem;
  depth: number;
  hasChildren: boolean;
  isExpanded: boolean;
  isSelected: boolean;
  dropZone: DropZone | null;
  canDrag: boolean;
  onSelect: (pageId: string) => void;
  onToggleExpand: (pageId: string) => void;
  onDelete: (page: DocsPageItem) => void;
}

function DocsPageTreeNode({
  page,
  depth,
  hasChildren,
  isExpanded,
  isSelected,
  dropZone,
  canDrag,
  onSelect,
  onToggleExpand,
  onDelete,
}: DocsPageTreeNodeProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: page.id,
    disabled: !canDrag,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  return (
    <div className="relative" style={style}>
      {dropZone === 'before' ? (
        <div className="pointer-events-none absolute inset-x-1 top-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
      <button
        ref={setNodeRef}
        {...attributes}
        {...listeners}
        onClick={() => onSelect(page.id)}
        className={cn(
          'app-text-body-sm group flex w-full items-center gap-1 rounded px-2 py-1.5 transition-all',
          isSelected
            ? 'bg-app-accent/10 text-app-accent'
            : 'text-gray-400 hover:bg-app-surface-hover hover:text-gray-200',
          isDragging && 'opacity-30',
          dropZone === 'inside' && 'bg-app-accent/15 ring-1 ring-inset ring-app-accent/70',
        )}
        style={{ paddingLeft: `${8 + depth * 16}px`, touchAction: 'none' }}
      >
        {hasChildren ? (
          <span
            className="flex-shrink-0"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              onToggleExpand(page.id);
            }}
          >
            {isExpanded ? (
              <ChevronDown size={12} className="text-gray-500" />
            ) : (
              <ChevronRight size={12} className="text-gray-500" />
            )}
          </span>
        ) : (
          <span className="w-3" />
        )}
        <FileText size={14} className={isSelected ? 'text-app-accent' : 'text-gray-500'} />
        <span className="truncate flex-1 text-left">{page.title}</span>
        {page.can_edit ? (
          <span
            className="opacity-0 group-hover:opacity-100"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              onDelete(page);
            }}
          >
            <Trash2 size={12} className="text-gray-500 hover:text-red-400" />
          </span>
        ) : null}
      </button>
      {dropZone === 'after' ? (
        <div className="pointer-events-none absolute inset-x-1 bottom-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
    </div>
  );
}

interface LocationOption {
  value: string;
  icon: typeof Globe;
  title: string;
  desc: string;
  disabled?: boolean;
  disabledReason?: string;
}

interface LocationPickerProps {
  value: string;
  onChange: (value: string) => void;
  options: LocationOption[];
  busy?: boolean;
}

function LocationPicker({ value, onChange, options, busy }: LocationPickerProps) {
  return (
    <div className="space-y-1.5">
      {options.map((option) => {
        const Icon = option.icon;
        const isSelected = value === option.value;
        const isDisabled = busy || option.disabled;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => !isDisabled && onChange(option.value)}
            disabled={isDisabled}
            title={option.disabled ? option.disabledReason : undefined}
            className={cn(
              'flex w-full items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors',
              isSelected
                ? 'border-app-accent bg-app-accent/10 ring-1 ring-app-accent'
                : 'border-app-border bg-app-bg hover:border-app-accent/50 hover:bg-app-surface-hover',
              isDisabled && 'cursor-not-allowed opacity-50 hover:border-app-border hover:bg-app-bg',
            )}
          >
            <span
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                isSelected ? 'bg-app-accent text-app-accent-fg' : 'bg-app-surface-hover text-gray-500',
              )}
            >
              <Icon size={15} />
            </span>
            <span className="flex-1 min-w-0">
              <span className="app-text-control block truncate text-app-ink">{option.title}</span>
              <span className="app-text-micro block truncate text-gray-500">{option.desc}</span>
            </span>
            {isSelected ? (
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-app-accent">
                <span className="block h-1.5 w-1.5 rounded-full bg-app-accent-fg" />
              </span>
            ) : (
              <span className="block h-4 w-4 shrink-0 rounded-full border border-app-border" />
            )}
          </button>
        );
      })}
    </div>
  );
}

function timeAgo(dateStr: string, timeZone: string): string {
  return formatRelativeTime(dateStr, { locale: 'en', timeZone });
}

function sharingLabel(item: DocsHubItem): string {
  if (item.source_type !== 'native_doc') {
    return item.source_app.toUpperCase();
  }
  if (item.sharing_summary?.visibility === 'private') {
    return 'Private';
  }
  const parts = [];
  if ((item.sharing_summary?.user_share_count ?? 0) > 0) {
    parts.push(`${item.sharing_summary?.user_share_count} users`);
  }
  if (item.sharing_summary?.link_active) {
    parts.push(`Link (${item.sharing_summary.link_access_level})`);
  }
  return parts.join(' · ') || 'Shared';
}

export const DocsView = () => {
  const { toolId, docId, shareToken, workspaceSlug } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const auth = useAuth();
  const { token } = auth;
  const timeZone = normalizeTimeZone(auth.user?.time_zone);
  const { uploadFile, createLinkedUploadFile, resolveFileUrl } = useMediaUpload();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();

  const [docs, setDocs] = useState<DocsHubItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [editorLoading, setEditorLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [sortBy, setSortBy] = useState('updated_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [docMenuOpen, setDocMenuOpen] = useState(false);
  const docMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!docMenuOpen) return;
    function onClick(e: MouseEvent) {
      if (docMenuRef.current && !docMenuRef.current.contains(e.target as Node)) {
        setDocMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [docMenuOpen]);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newDocTitle, setNewDocTitle] = useState('');
  const [newDocLocation, setNewDocLocation] = useState<string>('workspace');
  const [availableSpaces, setAvailableSpaces] = useState<PmsSpace[]>([]);
  const [creating, setCreating] = useState(false);

  const [selectedDoc, setSelectedDoc] = useState<DocsHubItem | null>(null);
  const [pages, setPages] = useState<DocsPageItem[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [resolvedSharedDocId, setResolvedSharedDocId] = useState<string | null>(null);

  const [showShareModal, setShowShareModal] = useState(false);
  const [sharingState, setSharingState] = useState<NativeDocSharingResponse | null>(null);
  const [shareableUsers, setShareableUsers] = useState<ShareableUserItem[]>([]);
  const [shareAccessLevel, setShareAccessLevel] = useState<'read' | 'edit'>('read');
  const [shareLoading, setShareLoading] = useState(false);
  const [inviteQuery, setInviteQuery] = useState('');
  const [inviteFocused, setInviteFocused] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [shareLinkCopied, setShareLinkCopied] = useState(false);

  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const activeCategory = toolId
    ? (CATEGORY_MAP[toolId] ?? 'all')
    : (searchParams.get('view') ?? 'all');
  const activeCategoryLabel = (toolId && CATEGORY_LABELS[toolId]) || VIEW_LABELS[activeCategory] || 'All Docs';
  const activeSourceApp = searchParams.get('source_app') ?? undefined;
  const activeSourceKind = searchParams.get('source_kind') ?? undefined;
  const activeFilterQuery = searchParams.toString();
  const activeItemId = docId ?? resolvedSharedDocId;
  const visibleTree = useMemo(() => flattenVisibleTree(pages, expandedNodes), [pages, expandedNodes]);
  const pagesById = useMemo(() => {
    const map = new Map<string, DocsPageItem>();
    for (const page of pages) map.set(page.id, page);
    return map;
  }, [pages]);
  const childCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const page of pages) {
      if (page.parent_id) counts.set(page.parent_id, (counts.get(page.parent_id) ?? 0) + 1);
    }
    return counts;
  }, [pages]);
  const activePage = pages.find((page) => page.id === selectedPageId) ?? pages[0] ?? null;
  const activeDocId = selectedDoc?.id ?? null;
  const activePageId = activePage?.id ?? null;
  const activePageUploadFile = useMemo(
    () => createLinkedUploadFile?.(
      activePage?.source_page_id
        ? {
            resourceType: mediaResourceTypeForDocsPage(activePage.source_type),
            resourceId: activePage.source_page_id,
          }
        : null
    ) ?? uploadFile,
    [activePage?.source_page_id, activePage?.source_type, createLinkedUploadFile, uploadFile],
  );
  const isListView = !activeItemId && !shareToken;
  const hasDocsWorkspace = hasWorkspaceMembership(auth.user, workspaceSlug);
  const currentWorkspace = useMemo(
    () => auth.user?.workspaces.find((workspace) => workspace.slug === workspaceSlug)
      ?? auth.user?.workspaces[0]
      ?? null,
    [auth.user, workspaceSlug],
  );
  const docsRoot = workspaceSlug
    ? buildWorkspaceAppPath(workspaceSlug, 'docs')
    : resolveDefaultWorkspaceAppPath(auth.user, 'docs');
  const docPathFor = useCallback(
    (itemId: string) => (
      workspaceSlug
        ? buildWorkspaceAppPath(workspaceSlug, 'docs', `/${itemId}`)
        : resolveDefaultWorkspaceAppPath(auth.user, 'docs', `/${itemId}`)
    ),
    [auth.user, workspaceSlug],
  );

  const fetchDocs = useCallback(async () => {
    if (!token) return;
    setLoadingList(true);
    try {
      const response = await listDocsHub(token, {
        view: activeCategory,
        q: searchQuery || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
        source_app: activeSourceApp,
        source_kind: activeSourceKind,
      }, workspaceSlug);
      setDocs(response.items);
      setTotal(response.total);
    } catch {
      setDocs([]);
      setTotal(0);
    } finally {
      setLoadingList(false);
    }
  }, [
    activeCategory,
    activeSourceApp,
    activeSourceKind,
    searchQuery,
    sortBy,
    sortDir,
    token,
    workspaceSlug,
  ]);

  const loadDoc = useCallback(async (itemId: string, currentShareToken?: string | null) => {
    if (!token) return;
    setEditorLoading(true);
    try {
      const [item, pageResponse] = await Promise.all([
        getDocsItem(token, itemId, currentShareToken, workspaceSlug),
        listDocPages(token, itemId, currentShareToken, workspaceSlug),
      ]);
      setSelectedDoc(item);
      setPages(pageResponse.items);
      const preferredPage = pageResponse.items[0]?.id ?? null;
      setSelectedPageId((current) => (
        current && pageResponse.items.some((page) => page.id === current)
          ? current
          : preferredPage
      ));
      setExpandedNodes(new Set(pageResponse.items.filter((page) => page.parent_id === null).map((page) => page.id)));
    } catch {
      setSelectedDoc(null);
      setPages([]);
      setSelectedPageId(null);
    } finally {
      setEditorLoading(false);
    }
  }, [token, workspaceSlug]);

  useEffect(() => {
    if (!token) return;
    if (isListView) {
      void fetchDocs();
    }
  }, [fetchDocs, isListView, token]);

  useEffect(() => {
    if (!token) return;
    if (!shareToken) {
      setResolvedSharedDocId(null);
      return;
    }
    setEditorLoading(true);
    void resolveSharedLink(token, shareToken)
      .then(async (response) => {
        setResolvedSharedDocId(response.item.id);
        await loadDoc(response.item.id, shareToken);
      })
      .catch(() => {
        setResolvedSharedDocId(null);
        setSelectedDoc(null);
        setPages([]);
        setSelectedPageId(null);
        setEditorLoading(false);
      });
  }, [loadDoc, shareToken, token]);

  useEffect(() => {
    if (!token || !docId || shareToken) return;
    void loadDoc(docId, null);
  }, [docId, loadDoc, shareToken, token]);

  useEffect(() => {
    if (!token || !activeDocId || !activePageId) return;
    void recordDocView(token, activeDocId, activePageId, shareToken, workspaceSlug);
  }, [activeDocId, activePageId, shareToken, token, workspaceSlug]);

  const handleSearchChange = (value: string) => {
    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }
    searchTimerRef.current = setTimeout(() => setSearchQuery(value), 250);
  };

  const openDoc = (itemId: string) => {
    const basePath = toolId ? `/tool/${toolId}/${itemId}` : docPathFor(itemId);
    navigate(activeFilterQuery ? `${basePath}?${activeFilterQuery}` : basePath);
  };

  const handleBack = () => {
    if (shareToken && !hasDocsWorkspace) {
      navigate('/');
      return;
    }
    const basePath = toolId ? `/tool/${toolId}` : docsRoot;
    navigate(activeFilterQuery ? `${basePath}?${activeFilterQuery}` : basePath);
  };

  const openCreateModal = useCallback((templateTitle?: string) => {
    setNewDocTitle(templateTitle ?? '');
    setNewDocLocation('workspace');
    setShowCreateModal(true);
    if (token) {
      void listSpaces(token)
        .then((spaces) => setAvailableSpaces(Array.isArray(spaces) ? spaces : []))
        .catch(() => setAvailableSpaces([]));
    }
  }, [token]);

  // Allow other parts of the shell (e.g. SubSidebar header "+" button) to
  // open the New Doc modal without owning a reference to this component.
  useEffect(() => {
    const handler = () => openCreateModal();
    window.addEventListener('docs:create', handler);
    return () => window.removeEventListener('docs:create', handler);
  }, [openCreateModal]);

  useEffect(() => {
    if (searchParams.get('create') !== '1' || shareToken) {
      return;
    }
    openCreateModal();
    const next = new URLSearchParams(searchParams);
    next.delete('create');
    setSearchParams(next, { replace: true });
  }, [openCreateModal, searchParams, setSearchParams, shareToken]);

  const locationOptions = useMemo<LocationOption[]>(() => [
    {
      value: 'workspace',
      icon: Globe,
      title: currentWorkspace ? `Workspace · ${currentWorkspace.name}` : 'Workspace',
      desc: '워크스페이스 전체 멤버가 볼 수 있어요',
    },
    ...availableSpaces.map((space) => ({
      value: `space:${space.id}`,
      icon: Users,
      title: space.name,
      desc: '팀스페이스 멤버만 볼 수 있어요',
    })),
    {
      value: 'private',
      icon: Lock,
      title: 'Private',
      desc: '나만 볼 수 있어요',
    },
  ], [availableSpaces, currentWorkspace]);

  const resolveContainerFromLocationValue = useCallback((locationValue: string) => {
    if (locationValue === 'private') return null;
    if (locationValue === 'workspace') {
      return currentWorkspace
        ? { app: 'docs', type: 'workspace_sidebar', id: currentWorkspace.id }
        : null;
    }
    if (locationValue.startsWith('space:')) {
      const spaceId = locationValue.slice('space:'.length);
      return { app: 'pms', type: 'space', id: spaceId };
    }
    return null;
  }, [currentWorkspace]);

  const resolveLocationValueFromContainer = useCallback((container: { app: string; type: string; id: string } | null) => {
    if (container === null) return 'private';
    if (container.app === 'docs' && container.type === 'workspace_sidebar') return 'workspace';
    if (container.app === 'pms' && container.type === 'space') return `space:${container.id}`;
    return 'private';
  }, []);

  const handleCreateDoc = async () => {
    if (!token || !newDocTitle.trim()) return;
    setCreating(true);
    try {
      const item = await createNativeDoc(token, {
        title: newDocTitle.trim(),
        primary_container: resolveContainerFromLocationValue(newDocLocation),
      }, workspaceSlug);
      setShowCreateModal(false);
      setNewDocTitle('');
      openDoc(item.id);
    } finally {
      setCreating(false);
    }
  };

  const handleToggleFavorite = async (event: React.MouseEvent, item: DocsHubItem) => {
    event.stopPropagation();
    if (!token) return;
    try {
      const response = await toggleDocFavorite(token, item.id);
      setDocs((current) => current.map((doc) => (
        doc.id === item.id ? { ...doc, is_favorite: response.is_favorite } : doc
      )));
      if (selectedDoc?.id === item.id) {
        setSelectedDoc({ ...item, is_favorite: response.is_favorite });
      }
    } catch {
      // no-op
    }
  };

  const handleRenameDoc = async (item: DocsHubItem) => {
    setMenuOpenId(null);
    if (!token || !item.can_manage) return;
    const nextTitle = await prompt({ title: 'Rename Document', defaultValue: item.title });
    if (!nextTitle || nextTitle.trim() === item.title) return;
    try {
      const updated = await updateDocsItem(token, item.id, { title: nextTitle.trim() }, shareToken, workspaceSlug);
      setDocs((current) => current.map((doc) => (doc.id === updated.id ? updated : doc)));
      if (selectedDoc?.id === updated.id) {
        setSelectedDoc(updated);
      }
    } catch {
      // no-op
    }
  };

  const handleDeleteDoc = async (item: DocsHubItem) => {
    setMenuOpenId(null);
    if (!token || !item.can_manage) return;
    const ok = await confirm({
      title: `Delete "${item.title}"?`,
      description: item.source_type === 'native_doc'
        ? 'This document will be moved to trash.'
        : 'This removes the source document from its origin.',
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await deleteDocsItem(token, item.id, shareToken);
      if (selectedDoc?.id === item.id) {
        handleBack();
      } else {
        void fetchDocs();
      }
    } catch {
      // no-op
    }
  };

  const handleDuplicateDoc = async (item: DocsHubItem) => {
    setMenuOpenId(null);
    setDocMenuOpen(false);
    if (!token) return;
    try {
      const duplicate = await duplicateDocsItem(token, item.id, shareToken);
      void fetchDocs();
      navigate(toolId ? `/tool/${toolId}/${duplicate.id}` : docPathFor(duplicate.id));
    } catch {
      // no-op
    }
  };

  const docUrlFor = (item: DocsHubItem): string => {
    const path = toolId ? `/tool/${toolId}/${item.id}` : docPathFor(item.id);
    return `${window.location.origin}${path}`;
  };

  const [copiedDocId, setCopiedDocId] = useState<string | null>(null);

  const handleCopyLink = async (item: DocsHubItem) => {
    setDocMenuOpen(false);
    try {
      await navigator.clipboard.writeText(docUrlFor(item));
      setCopiedDocId(item.id);
      window.setTimeout(() => setCopiedDocId((current) => (current === item.id ? null : current)), 1500);
    } catch {
      // no-op
    }
  };

  const handleOpenInNewTab = (item: DocsHubItem) => {
    setDocMenuOpen(false);
    window.open(docUrlFor(item), '_blank', 'noopener,noreferrer');
  };

  const handlePrintDoc = () => {
    setDocMenuOpen(false);
    window.print();
  };

  const handleAddPage = async (parentId?: string | null) => {
    if (!token || !selectedDoc || !selectedDoc.can_edit) return;
    const title = await prompt({ title: 'New Page', defaultValue: 'Untitled' });
    if (!title || !title.trim()) return;
    try {
      const page = await createDocPage(token, selectedDoc.id, {
        title: title.trim(),
        parent_id: parentId ?? null,
      }, shareToken);
      setPages((current) => [...current, page]);
      setSelectedPageId(page.id);
      if (parentId) {
        setExpandedNodes((current) => new Set(current).add(parentId));
      }
    } catch {
      // no-op
    }
  };

  const handleDeletePage = async (page: DocsPageItem) => {
    if (!token || !page.can_edit) return;
    const ok = await confirm({
      title: `Delete "${page.title}"?`,
      description: 'This page and its child pages will be removed from the document tree.',
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await deleteDocPage(token, page.id, shareToken);
      const removedIds = new Set<string>([page.id]);
      let changed = true;
      while (changed) {
        changed = false;
        for (const candidate of pages) {
          if (candidate.parent_id && removedIds.has(candidate.parent_id) && !removedIds.has(candidate.id)) {
            removedIds.add(candidate.id);
            changed = true;
          }
        }
      }
      const nextPages = pages.filter((item) => !removedIds.has(item.id));
      setPages(nextPages);
      if (selectedPageId && removedIds.has(selectedPageId)) {
        setSelectedPageId(nextPages[0]?.id ?? null);
      }
    } catch {
      // no-op
    }
  };

  const handleEditorChange = (blocks: Record<string, unknown>[]) => {
    if (!token || !activePage?.can_edit) return;
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = setTimeout(async () => {
      try {
        const updated = await updateDocPage(token, activePage.id, { content_blocks: blocks }, shareToken);
        setPages((current) => current.map((page) => (page.id === updated.id ? updated : page)));
      } catch {
        // no-op
      }
    }, 800);
  };

  const handlePageTitleSave = async (pageId: string, nextTitle: string) => {
    if (!token) return;
    const trimmed = nextTitle.trim();
    if (!trimmed) return;
    const target = pages.find((page) => page.id === pageId);
    if (!target || target.title === trimmed) return;
    try {
      const updated = await updateDocPage(token, pageId, { title: trimmed }, shareToken);
      setPages((current) => current.map((page) => (page.id === updated.id ? updated : page)));
    } catch {
      // no-op
    }
  };

  const handleCollabChange = useCallback((pageId: string, content: Record<string, unknown>[]) => {
    setPages((current) => current.map((page) => (
      page.id === pageId
        ? {
            ...page,
            content_blocks: content,
          }
        : page
    )));
  }, []);

  const toggleExpand = (nodeId: string) => {
    setExpandedNodes((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  const refreshSharing = useCallback(async (itemId: string) => {
    if (!token) return;
    const [sharing, users] = await Promise.all([
      getDocSharing(token, itemId),
      listShareableUsers(token),
    ]);
    setSharingState(sharing);
    setShareableUsers(users);
  }, [token]);

  const openShareModal = async () => {
    if (!selectedDoc?.can_share || !token) return;
    setShareLoading(true);
    setShowShareModal(true);
    void listSpaces(token)
      .then((spaces) => setAvailableSpaces(Array.isArray(spaces) ? spaces : []))
      .catch(() => setAvailableSpaces([]));
    try {
      await refreshSharing(selectedDoc.id);
    } finally {
      setShareLoading(false);
    }
  };

  const [changingLocation, setChangingLocation] = useState(false);

  const handleChangeLocation = async (nextLocation: string) => {
    if (!token || !selectedDoc || !selectedDoc.can_manage) return;
    const current = resolveLocationValueFromContainer(selectedDoc.primary_container);
    if (current === nextLocation) return;
    setChangingLocation(true);
    try {
      const nextContainer = resolveContainerFromLocationValue(nextLocation);
      const updated = nextContainer === null
        ? await deleteDocContainer(token, selectedDoc.id, workspaceSlug)
        : await updateDocContainer(token, selectedDoc.id, nextContainer, workspaceSlug);
      setSelectedDoc(updated);
      setDocs((current) => current.map((doc) => (doc.id === updated.id ? updated : doc)));
    } finally {
      setChangingLocation(false);
    }
  };


  const handleRemoveUserShare = async (userId: string) => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await deleteDocUserShare(token, selectedDoc.id, userId);
      setSharingState(updated);
    } finally {
      setShareLoading(false);
    }
  };

  const handleEnableLinkShare = async (accessLevel: 'read' | 'edit', regenerateToken = false) => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await upsertDocLinkShare(token, selectedDoc.id, {
        access_level: accessLevel,
        active: true,
        regenerate_token: regenerateToken,
      });
      setSharingState(updated);
    } finally {
      setShareLoading(false);
    }
  };

  const handleDisableLinkShare = async () => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await deleteDocLinkShare(token, selectedDoc.id);
      setSharingState(updated);
    } finally {
      setShareLoading(false);
    }
  };

  const copyShareLink = async () => {
    const tokenValue = sharingState?.link_share?.token;
    if (!tokenValue) return;
    const url = `${window.location.origin}/docs/shared/${tokenValue}`;
    try {
      await navigator.clipboard.writeText(url);
      setShareLinkCopied(true);
      window.setTimeout(() => setShareLinkCopied(false), 1500);
    } catch {
      // no-op
    }
  };

  const copyDirectLink = async () => {
    if (!selectedDoc) return;
    try {
      await navigator.clipboard.writeText(docUrlFor(selectedDoc));
      setLinkCopied(true);
      window.setTimeout(() => setLinkCopied(false), 1500);
    } catch {
      // no-op
    }
  };

  const invitedUserIds = useMemo(
    () => new Set(sharingState?.users.map((user) => user.user_id) ?? []),
    [sharingState?.users],
  );

  const inviteSuggestions = useMemo(() => {
    const query = inviteQuery.trim().toLowerCase();
    if (!query) return [];
    return shareableUsers
      .filter((user) => !invitedUserIds.has(user.id))
      .filter((user) => user.full_name.toLowerCase().includes(query) || user.email.toLowerCase().includes(query))
      .slice(0, 6);
  }, [inviteQuery, invitedUserIds, shareableUsers]);

  const handleInviteUser = async (userId: string) => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await upsertDocUserShare(token, selectedDoc.id, userId, shareAccessLevel);
      setSharingState(updated);
      setInviteQuery('');
    } finally {
      setShareLoading(false);
    }
  };

  const handleChangeUserAccess = async (userId: string, level: 'read' | 'edit') => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await upsertDocUserShare(token, selectedDoc.id, userId, level);
      setSharingState(updated);
    } finally {
      setShareLoading(false);
    }
  };

  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [dropIndicator, setDropIndicator] = useState<{ overId: string; zone: DropZone } | null>(null);
  const dragDescendantsRef = useRef<Set<string> | null>(null);
  const dragPointerYRef = useRef<number>(0);

  const dndSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragPointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    dragPointerYRef.current = event.clientY;
  }, []);

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const activeId = String(event.active.id);
    dragDescendantsRef.current = collectDescendantIds(pages, activeId);
    setActiveDragId(activeId);
    setDropIndicator(null);
  }, [pages]);

  const handleDragOver = useCallback((event: DragOverEvent) => {
    const { active, over } = event;
    if (!over || !active) {
      setDropIndicator(null);
      return;
    }
    const overId = String(over.id);
    if (overId === String(active.id)) {
      setDropIndicator(null);
      return;
    }
    const descendants = dragDescendantsRef.current;
    if (descendants && descendants.has(overId)) {
      setDropIndicator(null);
      return;
    }
    const rect = over.rect;
    if (!rect) return;
    const pointerY = dragPointerYRef.current;
    const pointerWithinRow = pointerY >= rect.top && pointerY <= rect.top + rect.height;
    let zone: DropZone;
    if (pointerWithinRow) {
      zone = resolveDropZone(pointerY, { top: rect.top, height: rect.height });
    } else {
      // Keyboard / out-of-row fallback: compare over vs active position.
      const activeRect = active.rect?.current?.translated ?? active.rect?.current?.initial ?? null;
      if (activeRect && rect.top < activeRect.top) {
        zone = 'before';
      } else {
        zone = 'after';
      }
    }
    setDropIndicator((current) => (
      current && current.overId === overId && current.zone === zone
        ? current
        : { overId, zone }
    ));
  }, []);

  const resetDragState = useCallback(() => {
    setActiveDragId(null);
    setDropIndicator(null);
    dragDescendantsRef.current = null;
  }, []);

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const indicator = dropIndicator;
    const activeId = String(event.active.id);
    resetDragState();
    if (!token || !indicator) return;
    const target = computeDropTarget(pages, indicator.overId, indicator.zone);
    if (!target) return;
    const result = applyReorder(pages, activeId, target);
    if (!result) return;
    const snapshot = pages;
    setPages(result.nextPages);
    if (target.parentId && !expandedNodes.has(target.parentId)) {
      setExpandedNodes((current) => {
        const next = new Set(current);
        next.add(target.parentId as string);
        return next;
      });
    }
    try {
      const updated = await Promise.all(
        result.patches.map((patch) => updateDocPage(
          token,
          patch.id,
          { parent_id: patch.parent_id, sort_order: patch.sort_order },
          shareToken,
        )),
      );
      setPages((current) => {
        const byId = new Map(updated.map((page) => [page.id, page]));
        return current.map((page) => byId.get(page.id) ?? page);
      });
    } catch {
      setPages(snapshot);
    }
  }, [dropIndicator, expandedNodes, pages, resetDragState, shareToken, token]);

  const renderEditor = () => {
    if (editorLoading) {
      return (
        <div className="flex-1 flex items-center justify-center bg-app-bg">
          <Loader2 size={28} className="animate-spin text-app-accent" />
        </div>
      );
    }

    if (!selectedDoc) {
      return (
        <div className="flex-1 flex items-center justify-center bg-app-bg text-gray-500">
          <div className="text-center">
            <FileText size={48} className="mx-auto mb-4 opacity-20" />
            <h2 className="app-text-title-md text-app-ink">Document not found</h2>
            <button onClick={handleBack} className="app-text-control mt-4 text-app-accent hover:underline">
              Go back
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="h-full flex flex-col bg-app-bg overflow-hidden">
        <div className="h-12 border-b border-app-border flex items-center justify-between px-4 bg-app-surface-sidebar">
          <div className="app-text-caption flex items-center gap-2 min-w-0">
            <span className="cursor-pointer text-gray-500 hover:text-gray-300" onClick={handleBack}>
              Docs
            </span>
            <span className="text-gray-600">/</span>
            <span className="truncate text-app-ink">{selectedDoc.title}</span>
            <Star
              size={12}
              className={cn(
                'text-gray-600 cursor-pointer',
                selectedDoc.is_favorite && 'text-yellow-500 fill-yellow-500',
              )}
              onClick={(event) => void handleToggleFavorite(event, selectedDoc)}
            />
          </div>

          <div className="flex items-center gap-2">
            {selectedDoc.can_share ? (
              <button
                onClick={() => void openShareModal()}
                className="app-text-control-sm flex items-center gap-1.5 rounded-md px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover"
              >
                <Share2 size={14} />
                <span>Share</span>
              </button>
            ) : null}
            <button className="app-text-control-sm flex items-center gap-1.5 rounded-md px-3 py-1.5 text-app-accent transition-colors hover:bg-app-accent/10">
              <Sparkles size={14} />
              <span>Ask AI</span>
            </button>
            <div ref={docMenuRef} className="relative">
              <button
                onClick={() => setDocMenuOpen((o) => !o)}
                className="rounded p-1.5 text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                title="More actions"
              >
                <MoreHorizontal size={18} />
              </button>
              {docMenuOpen ? (
                <div className="absolute right-0 top-full mt-1 z-30 w-52 rounded-lg border border-app-border bg-app-surface-sidebar py-1 shadow-xl">
                  <button
                    onClick={() => void handleCopyLink(selectedDoc)}
                    className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                  >
                    <Link2 size={14} />
                    <span>{copiedDocId === selectedDoc.id ? 'Copied!' : 'Copy link'}</span>
                  </button>
                  <button
                    onClick={() => handleOpenInNewTab(selectedDoc)}
                    className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                  >
                    <ExternalLink size={14} />
                    <span>Open in new tab</span>
                  </button>
                  <button
                    onClick={() => void handleDuplicateDoc(selectedDoc)}
                    className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                  >
                    <Copy size={14} />
                    <span>Duplicate</span>
                  </button>
                  <button
                    onClick={handlePrintDoc}
                    className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                  >
                    <Printer size={14} />
                    <span>Print</span>
                  </button>
                  {selectedDoc.can_manage ? (
                    <>
                      <div className="my-1 h-px bg-app-border" />
                      <button
                        onClick={() => {
                          setDocMenuOpen(false);
                          void handleRenameDoc(selectedDoc);
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <Pencil size={14} />
                        <span>Rename</span>
                      </button>
                      <button
                        onClick={() => {
                          setDocMenuOpen(false);
                          void handleDeleteDoc(selectedDoc);
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-red-400 hover:bg-app-surface-hover"
                      >
                        <Trash2 size={14} />
                        <span>Delete</span>
                      </button>
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>
            <button onClick={handleBack} className="p-1.5 hover:bg-red-500/20 hover:text-red-500 rounded text-gray-500 transition-colors">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="flex-1 flex overflow-hidden">
          <div className="w-64 border-r border-app-border bg-app-surface-sidebar flex flex-col overflow-hidden">
            <div className="p-4 space-y-4">
              <div className="space-y-1">
                <h2 className="app-text-title-sm text-app-ink truncate">{selectedDoc.title}</h2>
                <p className="app-text-caption text-gray-500 truncate">{selectedDoc.location_label}</p>
              </div>

              <div>
                <div className="flex items-center justify-between px-2 mb-2">
                  <span className="app-text-overline text-gray-500">Pages</span>
                </div>
                <DndContext
                  sensors={dndSensors}
                  collisionDetection={closestCenter}
                  onDragStart={handleDragStart}
                  onDragOver={handleDragOver}
                  onDragEnd={handleDragEnd}
                  onDragCancel={resetDragState}
                >
                  <SortableContext
                    items={visibleTree.map((node) => node.id)}
                    strategy={verticalListSortingStrategy}
                  >
                    <div
                      className="space-y-0.5 overflow-y-auto custom-scrollbar max-h-[calc(100vh-250px)]"
                      onPointerMove={handleDragPointerMove}
                    >
                      {visibleTree.map((node) => {
                        const page = pagesById.get(node.id);
                        if (!page) return null;
                        const zone = dropIndicator && dropIndicator.overId === node.id
                          ? dropIndicator.zone
                          : null;
                        return (
                          <DocsPageTreeNode
                            key={node.id}
                            page={page}
                            depth={node.depth}
                            hasChildren={(childCounts.get(node.id) ?? 0) > 0}
                            isExpanded={expandedNodes.has(node.id)}
                            isSelected={selectedPageId === node.id}
                            dropZone={zone}
                            canDrag={Boolean(selectedDoc.can_edit && page.can_edit)}
                            onSelect={setSelectedPageId}
                            onToggleExpand={toggleExpand}
                            onDelete={handleDeletePage}
                          />
                        );
                      })}
                      {selectedDoc.can_edit ? (
                        <button
                          onClick={() => void handleAddPage(null)}
                          className="app-text-body-sm flex w-full items-center gap-2 rounded px-3 py-1.5 text-gray-500 transition-all hover:bg-app-surface-hover hover:text-app-accent"
                        >
                          <Plus size={14} />
                          <span>Add page</span>
                        </button>
                      ) : null}
                    </div>
                  </SortableContext>
                  <DragOverlay dropAnimation={null}>
                    {activeDragId ? (
                      <div className="app-text-body-sm flex items-center gap-1 rounded bg-app-surface-sidebar px-2 py-1.5 text-app-ink shadow-lg ring-1 ring-app-accent/40">
                        <FileText size={14} className="text-app-accent" />
                        <span className="truncate">{pagesById.get(activeDragId)?.title ?? ''}</span>
                      </div>
                    ) : null}
                  </DragOverlay>
                </DndContext>
              </div>
            </div>

            <div className="mt-auto p-4 border-t border-app-border">
              <div className="app-text-body-sm flex items-center gap-2 rounded px-3 py-1.5 text-gray-500">
                {selectedDoc.source_type === 'native_doc' ? <Lock size={14} /> : <Globe size={14} />}
                <span>{sharingLabel(selectedDoc)}</span>
              </div>
            </div>
          </div>

          <div className="docs-print-area flex-1 flex flex-col min-w-0 bg-white dark:bg-[#1e1e24] overflow-y-auto custom-scrollbar">
            <div className="max-w-4xl mx-auto py-12 px-12 w-full">
              {activePage ? (
                <div className="space-y-6">
                  <div className="space-y-4">
                    {selectedDoc.can_edit && activePage.can_edit ? (
                      <input
                        key={activePage.id}
                        type="text"
                        defaultValue={activePage.title}
                        placeholder="Untitled"
                        className="app-text-title-xl w-full bg-transparent text-app-ink placeholder:text-gray-500 focus:outline-none"
                        onBlur={(event) => void handlePageTitleSave(activePage.id, event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault();
                            event.currentTarget.blur();
                          }
                          if (event.key === 'Escape') {
                            event.currentTarget.value = activePage.title;
                            event.currentTarget.blur();
                          }
                        }}
                      />
                    ) : (
                      <h1 className="app-text-title-xl text-app-ink">{activePage.title}</h1>
                    )}
                    <div className="app-text-caption flex items-center gap-3 text-gray-500">
                      <div className="flex items-center gap-1.5">
                        <div className="app-text-micro flex h-5 w-5 items-center justify-center rounded-full bg-app-accent font-bold text-app-bg">
                          {selectedDoc.created_by_name.split(' ').map((name) => name[0]).join('').slice(0, 2)}
                        </div>
                        <span className="app-text-control text-app-ink">{selectedDoc.created_by_name}</span>
                      </div>
                      <span>·</span>
                      <span>{selectedDoc.location_label}</span>
                      <span>·</span>
                      <span>Updated {timeAgo(activePage.updated_at, timeZone)}</span>
                    </div>
                  </div>
                  <div className="prose dark:prose-invert max-w-none pt-4">
                    {selectedDoc.can_edit && activePage.can_edit && activePage.realtime_collab && !shareToken && token ? (
                      <CollaborativeBlockEditor
                        sessionKey={`${workspaceSlug ?? 'current'}:${activePage.id}`}
                        authToken={token}
                        loadSession={async () => {
                          const session = await getDocsCollabSession(
                            token,
                            makeDocsPageRef(activePage.source_type, activePage.source_page_id),
                            workspaceSlug,
                          );
                          return {
                            roomKey: session.room_key,
                            wsPath: session.ws_path,
                            user: {
                              id: session.user.id,
                              fullName: session.user.full_name,
                            },
                            realtimeStatus: session.realtime_status,
                            readOnlyReason: session.read_only_reason,
                            snapshotContent: (session.snapshot_content_blocks ?? []) as never,
                            yjsState: session.yjs_state,
                          };
                        }}
                        placeholder="Start writing..."
                        uploadFile={activePageUploadFile}
                        resolveFileUrl={resolveFileUrl}
                        onChange={(content) => {
                          handleCollabChange(
                            activePage.id,
                            content as Record<string, unknown>[],
                          );
                        }}
                      />
                    ) : selectedDoc.can_edit && activePage.can_edit ? (
                      <BlockEditor
                        key={activePage.id}
                        initialContent={activePage.content_blocks as never}
                        placeholder="Start writing..."
                        uploadFile={activePageUploadFile}
                        resolveFileUrl={resolveFileUrl}
                        onChange={handleEditorChange}
                      />
                    ) : (
                      <BlockViewer
                        key={activePage.id}
                        content={(activePage.content_blocks as never) ?? []}
                        resolveFileUrl={resolveFileUrl}
                      />
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center py-20">
                  <FileText size={48} className="mx-auto mb-4 text-gray-600 opacity-20" />
                  <p className="app-text-body text-gray-500 mb-4">No pages yet</p>
                  {selectedDoc.can_edit ? (
                    <button
                      onClick={() => void handleAddPage(null)}
                      className="app-text-control rounded-md bg-app-accent px-4 py-2 text-app-bg hover:opacity-90"
                    >
                      Add first page
                    </button>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="h-full w-full flex flex-col min-w-0 bg-app-bg overflow-hidden relative">
      {confirmDialog}
      {promptDialog}

      {showCreateModal ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50" onClick={() => setShowCreateModal(false)}>
          <div className="w-full max-w-md rounded-lg border border-app-border bg-app-surface-sidebar p-6 space-y-4" onClick={(event) => event.stopPropagation()}>
            <h2 className="app-text-title-md text-app-ink">New Document</h2>
            <div>
              <label className="app-text-caption text-gray-500 mb-1 block">Title</label>
              <input
                type="text"
                value={newDocTitle}
                onChange={(event) => setNewDocTitle(event.target.value)}
                placeholder="Document title..."
                className="app-text-body w-full rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                autoFocus
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    void handleCreateDoc();
                  }
                }}
              />
            </div>
            <div>
              <label className="app-text-caption text-gray-500 mb-1.5 block">Location</label>
              <LocationPicker
                value={newDocLocation}
                onChange={setNewDocLocation}
                options={locationOptions}
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowCreateModal(false)}
                className="app-text-control rounded-md border border-app-border px-4 py-2 text-app-ink hover:bg-app-surface-hover"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleCreateDoc()}
                disabled={creating || !newDocTitle.trim()}
                className="app-text-control rounded-md bg-app-accent px-4 py-2 text-app-bg hover:opacity-90 disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {showShareModal && selectedDoc ? (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/50" onClick={() => setShowShareModal(false)}>
          <div className="w-full max-w-2xl rounded-lg border border-app-border bg-app-surface-sidebar p-6 space-y-5" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="app-text-title-md text-app-ink">Share Document</h2>
                <p className="app-text-caption text-gray-500">{selectedDoc.title}</p>
              </div>
              <button onClick={() => setShowShareModal(false)} className="rounded p-1.5 text-gray-500 hover:bg-app-surface-hover">
                <X size={18} />
              </button>
            </div>

            {shareLoading ? (
              <div className="py-10 flex items-center justify-center">
                <Loader2 size={24} className="animate-spin text-app-accent" />
              </div>
            ) : (
              <>
                {/* 1. Invite by name/email (top, most common action) */}
                <div className="space-y-3">
                  <div className="relative flex items-center gap-2">
                    <div className="relative flex-1">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={14} />
                      <input
                        type="text"
                        value={inviteQuery}
                        onChange={(event) => setInviteQuery(event.target.value)}
                        onFocus={() => setInviteFocused(true)}
                        onBlur={() => window.setTimeout(() => setInviteFocused(false), 150)}
                        placeholder="Invite by name or email..."
                        className="app-text-body w-full rounded-md border border-app-border bg-app-bg py-2 pl-9 pr-3 text-app-ink focus:border-app-accent focus:outline-none"
                      />
                      {inviteFocused && inviteSuggestions.length > 0 ? (
                        <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-60 overflow-y-auto rounded-md border border-app-border bg-app-surface-sidebar shadow-lg">
                          {inviteSuggestions.map((user) => (
                            <button
                              key={user.id}
                              type="button"
                              onMouseDown={(event) => {
                                event.preventDefault();
                                void handleInviteUser(user.id);
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-app-surface-hover"
                            >
                              <div className="app-text-micro flex h-7 w-7 items-center justify-center rounded-full bg-app-accent/20 font-bold text-app-accent">
                                {user.full_name.split(' ').map((name) => name[0]).join('').slice(0, 2)}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="app-text-control text-app-ink truncate">{user.full_name}</div>
                                <div className="app-text-micro text-gray-500 truncate">{user.email}</div>
                              </div>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <select
                      value={shareAccessLevel}
                      onChange={(event) => setShareAccessLevel(event.target.value as 'read' | 'edit')}
                      className="app-text-body rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                    >
                      <option value="read">Can read</option>
                      <option value="edit">Can edit</option>
                    </select>
                  </div>

                  {sharingState?.users.length ? (
                    <div className="space-y-1.5">
                      <div className="app-text-overline text-gray-500">People with access</div>
                      {sharingState.users.map((user) => (
                        <div key={user.user_id} className="flex items-center justify-between rounded-md border border-app-border bg-app-bg px-3 py-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <div className="app-text-micro flex h-7 w-7 items-center justify-center rounded-full bg-app-accent/20 font-bold text-app-accent shrink-0">
                              {user.full_name.split(' ').map((name) => name[0]).join('').slice(0, 2)}
                            </div>
                            <div className="min-w-0">
                              <div className="app-text-control text-app-ink truncate">{user.full_name}</div>
                              <div className="app-text-micro text-gray-500 truncate">{user.email}</div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <select
                              value={user.access_level}
                              onChange={(event) => void handleChangeUserAccess(user.user_id, event.target.value as 'read' | 'edit')}
                              className="app-text-caption rounded border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink focus:border-app-accent focus:outline-none"
                            >
                              <option value="read">Can read</option>
                              <option value="edit">Can edit</option>
                            </select>
                            <button
                              onClick={() => void handleRemoveUserShare(user.user_id)}
                              className="app-text-caption rounded border border-app-border px-2 py-1 text-app-ink hover:bg-app-surface-hover"
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>

                {/* 2. Who can access — container visibility */}
                <div className="rounded-lg border border-app-border bg-app-bg p-4 space-y-3">
                  <div>
                    <div className="app-text-control text-app-ink">Who can access</div>
                    <div className="app-text-caption text-gray-500">
                      이 문서를 기본으로 볼 수 있는 범위예요.
                    </div>
                  </div>
                  <LocationPicker
                    value={resolveLocationValueFromContainer(selectedDoc.primary_container)}
                    onChange={(value) => void handleChangeLocation(value)}
                    options={locationOptions}
                    busy={changingLocation || !selectedDoc.can_manage}
                  />
                  {!selectedDoc.can_manage ? (
                    <div className="app-text-micro text-gray-500">
                      공개 범위는 문서 소유자나 관리자만 변경할 수 있어요.
                    </div>
                  ) : null}
                </div>

                {/* 3. Copy link — always visible direct doc URL */}
                <div className="flex items-center gap-2 rounded-lg border border-app-border bg-app-bg px-3 py-2">
                  <Link2 size={16} className="text-gray-500 shrink-0" />
                  <input
                    type="text"
                    readOnly
                    value={docUrlFor(selectedDoc)}
                    className="app-text-body-sm flex-1 min-w-0 bg-transparent text-app-ink focus:outline-none"
                  />
                  <button
                    onClick={() => void copyDirectLink()}
                    className="app-text-control-sm flex items-center gap-1 rounded-md border border-app-border px-2.5 py-1 text-app-ink hover:bg-app-surface-hover"
                  >
                    <Copy size={12} />
                    <span>{linkCopied ? 'Copied!' : 'Copy link'}</span>
                  </button>
                </div>

                {/* 4. Internal share link — token-based toggle */}
                <div className="rounded-lg border border-app-border bg-app-bg p-4 space-y-3">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="app-text-control text-app-ink">Internal share link</div>
                      <div className="app-text-caption text-gray-500">
                        로그인한 모든 내부 사용자가 이 링크로 문서에 접근할 수 있어요.
                      </div>
                    </div>
                    {sharingState?.link_share?.active ? (
                      <button
                        onClick={() => void handleDisableLinkShare()}
                        className="app-text-control rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
                      >
                        Disable
                      </button>
                    ) : (
                      <div className="flex items-center gap-2">
                        <select
                          value={sharingState?.link_share?.access_level ?? 'read'}
                          onChange={(event) => void handleEnableLinkShare(event.target.value as 'read' | 'edit')}
                          className="app-text-body rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                        >
                          <option value="read">Can read</option>
                          <option value="edit">Can edit</option>
                        </select>
                        <button
                          onClick={() => void handleEnableLinkShare(sharingState?.link_share?.access_level ?? 'read')}
                          className="app-text-control rounded-md bg-app-accent px-3 py-2 text-app-bg hover:opacity-90"
                        >
                          Enable link
                        </button>
                      </div>
                    )}
                  </div>

                  {sharingState?.link_share?.active ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={`${window.location.origin}${sharingState.link_share.share_path}`}
                        className="app-text-body flex-1 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                      />
                      <button
                        onClick={() => void copyShareLink()}
                        className="app-text-control flex items-center gap-1 rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
                      >
                        <Copy size={14} />
                        <span>{shareLinkCopied ? 'Copied!' : 'Copy'}</span>
                      </button>
                      <button
                        onClick={() => void handleEnableLinkShare(sharingState.link_share?.access_level ?? 'read', true)}
                        className="app-text-control rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
                      >
                        Regenerate
                      </button>
                    </div>
                  ) : null}
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}

      {isListView ? (
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <div className="p-8 space-y-5 overflow-y-auto h-full custom-scrollbar">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="app-text-title-lg text-app-ink">{activeCategoryLabel}</h1>
                <p className="app-text-caption text-gray-500">{total} documents</p>
              </div>
              <button
                onClick={() => openCreateModal()}
                className="app-text-control flex items-center gap-2 rounded-md bg-app-accent px-4 py-2 text-app-accent-fg shadow-sm transition-opacity hover:opacity-90"
              >
                <Plus size={16} />
                <span>New Doc</span>
              </button>
            </div>

            <div className="flex gap-3">
              {TEMPLATES.map((template) => (
                <button
                  key={template.title}
                  onClick={() => openCreateModal(template.title)}
                  className="flex items-center gap-3 rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-3 text-left transition-colors hover:border-app-accent/30 hover:bg-app-surface-hover flex-1"
                >
                  <span className="text-2xl">{template.icon}</span>
                  <div>
                    <div className="app-text-control text-app-ink">{template.title}</div>
                    <div className="app-text-micro text-gray-500">{template.desc}</div>
                  </div>
                </button>
              ))}
            </div>

            <div className="flex items-center gap-4 border-b border-app-border pb-2">
              <button className="app-text-control-sm flex items-center gap-1.5 rounded px-2 py-1 text-gray-500 hover:bg-app-surface-hover hover:text-app-ink">
                <Filter size={14} />
                <span>Filters</span>
              </button>
              <div className="app-text-caption ml-auto flex items-center gap-2 text-gray-500">
                {searchOpen ? (
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={14} />
                    <input
                      type="text"
                      defaultValue={searchQuery}
                      placeholder="Search docs..."
                      onChange={(event) => handleSearchChange(event.target.value)}
                      className="app-text-body-sm w-64 rounded-md border border-app-border bg-app-surface-sidebar py-1.5 pl-9 pr-4 text-app-ink focus:border-app-accent focus:outline-none"
                      autoFocus
                      onBlur={(event) => {
                        if (!event.target.value) {
                          setSearchOpen(false);
                        }
                      }}
                    />
                  </div>
                ) : (
                  <button
                    onClick={() => setSearchOpen(true)}
                    className="p-1.5 rounded text-gray-500 hover:bg-app-surface-hover hover:text-app-ink"
                  >
                    <Search size={16} />
                  </button>
                )}
              </div>
            </div>

            {loadingList ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 size={32} className="animate-spin text-app-accent" />
              </div>
            ) : docs.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center py-20 text-center">
                <div className="w-24 h-24 bg-app-surface-sidebar rounded-full flex items-center justify-center mb-6">
                  <FileText size={48} className="text-gray-600 opacity-20" />
                </div>
                <h2 className="app-text-title-md mb-2 text-app-ink">No Docs found</h2>
                <p className="app-text-body mb-8 max-w-xs mx-auto text-gray-500">
                  Create personal docs here, and browse PMS documents with their original permissions.
                </p>
                <button
                  onClick={() => openCreateModal()}
                  className="app-text-control rounded-md bg-app-accent px-6 py-2 font-bold text-app-bg transition-opacity hover:opacity-90"
                >
                  New Doc
                </button>
              </div>
            ) : (
              <div className="border border-app-border rounded-lg overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-app-border bg-app-surface-sidebar">
                      <th
                        className="app-text-overline text-left px-4 py-2.5 text-gray-500 cursor-pointer hover:text-app-ink"
                        onClick={() => {
                          if (sortBy === 'title') setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'));
                          else {
                            setSortBy('title');
                            setSortDir('asc');
                          }
                        }}
                      >
                        Name
                      </th>
                      <th className="app-text-overline text-left px-4 py-2.5 text-gray-500">Location</th>
                      <th className="app-text-overline text-left px-4 py-2.5 text-gray-500">Sharing</th>
                      <th
                        className="app-text-overline text-left px-4 py-2.5 text-gray-500 cursor-pointer hover:text-app-ink"
                        onClick={() => {
                          if (sortBy === 'updated_at') setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'));
                          else {
                            setSortBy('updated_at');
                            setSortDir('desc');
                          }
                        }}
                      >
                        Updated
                      </th>
                      <th className="w-12" />
                    </tr>
                  </thead>
                  <tbody>
                    {docs.map((item) => (
                      <tr
                        key={item.id}
                        onClick={() => openDoc(item.id)}
                        className="cursor-pointer border-b border-app-border last:border-b-0 hover:bg-app-surface-sidebar/60"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <FileText size={16} className="text-app-accent shrink-0" />
                            <div className="min-w-0">
                              <div className="app-text-control text-app-ink truncate">{item.title}</div>
                              <div className="app-text-caption text-gray-500">
                                {item.page_count} page{item.page_count === 1 ? '' : 's'}
                              </div>
                            </div>
                            <Star
                              size={14}
                              className={cn(
                                'shrink-0 text-gray-600',
                                item.is_favorite && 'text-yellow-500 fill-yellow-500',
                              )}
                              onClick={(event) => void handleToggleFavorite(event, item)}
                            />
                          </div>
                        </td>
                        <td className="px-4 py-3 app-text-body-sm text-gray-400">{item.location_label}</td>
                        <td className="px-4 py-3 app-text-body-sm text-gray-400">
                          <div className="flex items-center gap-2">
                            {item.source_type === 'native_doc' && item.is_private ? <Lock size={14} /> : <Globe size={14} />}
                            <span>{sharingLabel(item)}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 app-text-body-sm text-gray-400">{timeAgo(item.updated_at, timeZone)}</td>
                        <td className="px-4 py-3 relative">
                          <button
                            onClick={(event) => {
                              event.stopPropagation();
                              setMenuOpenId((current) => (current === item.id ? null : item.id));
                            }}
                            className="rounded p-1.5 text-gray-500 hover:bg-app-surface-hover"
                          >
                            <MoreHorizontal size={16} />
                          </button>
                          {menuOpenId === item.id ? (
                            <div className="absolute right-4 top-11 z-20 w-48 rounded-lg border border-app-border bg-app-surface-sidebar py-1 shadow-xl">
                              <button
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleRenameDoc(item);
                                }}
                                disabled={!item.can_manage}
                                className="flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover disabled:opacity-40"
                              >
                                <Pencil size={14} />
                                <span className="app-text-control-sm">Rename</span>
                              </button>
                              <button
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleDeleteDoc(item);
                                }}
                                disabled={!item.can_manage}
                                className="flex w-full items-center gap-2 px-3 py-2 text-left text-red-400 hover:bg-app-surface-hover disabled:opacity-40"
                              >
                                <Trash2 size={14} />
                                <span className="app-text-control-sm">Delete</span>
                              </button>
                            </div>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : (
        renderEditor()
      )}
    </div>
  );
};
