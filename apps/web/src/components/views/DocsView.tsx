import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
  X,
} from 'lucide-react';
import { BlockEditor, BlockViewer, useConfirm, usePrompt } from '@aidoo/ui';

import { useMediaUpload } from '@/src/domains/media/use-media-upload';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { hasWorkspaceMembership } from '@/src/domains/auth/auth-api';
import { cn } from '@/src/lib/utils';
import {
  createDocPage,
  createNativeDoc,
  deleteDocPage,
  deleteDocsItem,
  deleteDocLinkShare,
  deleteDocUserShare,
  duplicateDocsItem,
  getDocsItem,
  getDocSharing,
  listDocPages,
  listDocsHub,
  listShareableUsers,
  recordDocView,
  resolveSharedLink,
  toggleDocFavorite,
  updateDocPage,
  updateDocsItem,
  upsertDocLinkShare,
  upsertDocUserShare,
  type DocsHubItem,
  type DocsPageItem,
  type NativeDocSharingResponse,
  type ShareableUserItem,
} from '@/src/domains/docs/docs-api';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/domains/workspaces/workspace-utils';

const CATEGORY_MAP: Record<string, string> = {
  'docs-all': 'all',
  'docs-my': 'my',
  'docs-shared': 'shared',
  'docs-private': 'private',
  'docs-notes': 'all',
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

const TEMPLATES = [
  { title: 'Project Overview', desc: 'Summarize goals, scope, and milestones', icon: '📋' },
  { title: 'Meeting Notes', desc: 'Capture an agenda, notes, and action items', icon: '📝' },
  { title: 'Wiki', desc: 'Organize information in one place', icon: '📚' },
];

type TreeNode = DocsPageItem & { children: TreeNode[] };

function buildTree(pages: DocsPageItem[]): TreeNode[] {
  const roots: TreeNode[] = [];
  const byId = new Map<string, TreeNode>();
  for (const page of pages) {
    byId.set(page.id, { ...page, children: [] });
  }
  for (const page of pages) {
    const node = byId.get(page.id);
    if (!node) continue;
    if (page.parent_id && byId.has(page.parent_id)) {
      byId.get(page.parent_id)?.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots.sort((left, right) => left.sort_order - right.sort_order || left.title.localeCompare(right.title, 'ko'));
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
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
  const auth = useAuth();
  const { token } = auth;
  const { uploadFile, resolveFileUrl } = useMediaUpload();
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
  const [creating, setCreating] = useState(false);

  const [selectedDoc, setSelectedDoc] = useState<DocsHubItem | null>(null);
  const [pages, setPages] = useState<DocsPageItem[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [resolvedSharedDocId, setResolvedSharedDocId] = useState<string | null>(null);

  const [showShareModal, setShowShareModal] = useState(false);
  const [sharingState, setSharingState] = useState<NativeDocSharingResponse | null>(null);
  const [shareableUsers, setShareableUsers] = useState<ShareableUserItem[]>([]);
  const [shareUserId, setShareUserId] = useState('');
  const [shareAccessLevel, setShareAccessLevel] = useState<'read' | 'edit'>('read');
  const [shareLoading, setShareLoading] = useState(false);

  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const activeCategory = toolId ? (CATEGORY_MAP[toolId] ?? 'all') : 'all';
  const activeCategoryLabel = (toolId && CATEGORY_LABELS[toolId]) || 'All Docs';
  const activeItemId = docId ?? resolvedSharedDocId;
  const tree = useMemo(() => buildTree(pages), [pages]);
  const activePage = pages.find((page) => page.id === selectedPageId) ?? pages[0] ?? null;
  const isListView = !activeItemId && !shareToken;
  const hasDocsWorkspace = hasWorkspaceMembership(auth.user, workspaceSlug);
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
        category: activeCategory,
        q: searchQuery || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      setDocs(response.items);
      setTotal(response.total);
    } catch {
      setDocs([]);
      setTotal(0);
    } finally {
      setLoadingList(false);
    }
  }, [activeCategory, searchQuery, sortBy, sortDir, token]);

  const loadDoc = useCallback(async (itemId: string, currentShareToken?: string | null) => {
    if (!token) return;
    setEditorLoading(true);
    try {
      const [item, pageResponse] = await Promise.all([
        getDocsItem(token, itemId, currentShareToken),
        listDocPages(token, itemId, currentShareToken),
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
  }, [token]);

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
    if (!token || !selectedDoc || !activePage) return;
    void recordDocView(token, selectedDoc.id, activePage.id, shareToken);
  }, [activePage, selectedDoc, shareToken, token]);

  const handleSearchChange = (value: string) => {
    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }
    searchTimerRef.current = setTimeout(() => setSearchQuery(value), 250);
  };

  const openDoc = (itemId: string) => {
    navigate(toolId ? `/tool/${toolId}/${itemId}` : docPathFor(itemId));
  };

  const handleBack = () => {
    if (shareToken && !hasDocsWorkspace) {
      navigate('/');
      return;
    }
    navigate(toolId ? `/tool/${toolId}` : docsRoot);
  };

  const openCreateModal = useCallback((templateTitle?: string) => {
    setNewDocTitle(templateTitle ?? '');
    setShowCreateModal(true);
  }, []);

  // Allow other parts of the shell (e.g. SubSidebar header "+" button) to
  // open the New Doc modal without owning a reference to this component.
  useEffect(() => {
    const handler = () => openCreateModal();
    window.addEventListener('docs:create', handler);
    return () => window.removeEventListener('docs:create', handler);
  }, [openCreateModal]);

  const handleCreateDoc = async () => {
    if (!token || !newDocTitle.trim()) return;
    setCreating(true);
    try {
      const item = await createNativeDoc(token, { title: newDocTitle.trim() });
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
      const updated = await updateDocsItem(token, item.id, { title: nextTitle.trim() }, shareToken);
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
    try {
      await refreshSharing(selectedDoc.id);
    } finally {
      setShareLoading(false);
    }
  };

  const handleAddUserShare = async () => {
    if (!token || !selectedDoc || !shareUserId) return;
    setShareLoading(true);
    try {
      const updated = await upsertDocUserShare(token, selectedDoc.id, shareUserId, shareAccessLevel);
      setSharingState(updated);
      setShareUserId('');
    } finally {
      setShareLoading(false);
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
    await navigator.clipboard.writeText(url);
  };

  const renderTreeNode = (node: TreeNode, depth = 0) => {
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children.length > 0;
    return (
      <div key={node.id}>
        <button
          onClick={() => setSelectedPageId(node.id)}
          className={cn(
            'app-text-body-sm group flex w-full items-center gap-1 rounded px-2 py-1.5 transition-all',
            selectedPageId === node.id
              ? 'bg-app-accent/10 text-app-accent'
              : 'text-gray-400 hover:bg-app-surface-hover hover:text-gray-200',
          )}
          style={{ paddingLeft: `${8 + depth * 16}px` }}
        >
          {hasChildren ? (
            <span
              className="flex-shrink-0"
              onClick={(event) => {
                event.stopPropagation();
                toggleExpand(node.id);
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
          <FileText size={14} className={selectedPageId === node.id ? 'text-app-accent' : 'text-gray-500'} />
          <span className="truncate flex-1 text-left">{node.title}</span>
          {node.can_edit ? (
            <span
              className="opacity-0 group-hover:opacity-100"
              onClick={(event) => {
                event.stopPropagation();
                void handleDeletePage(node);
              }}
            >
              <Trash2 size={12} className="text-gray-500 hover:text-red-400" />
            </span>
          ) : null}
        </button>
        {isExpanded ? node.children.sort((left, right) => left.sort_order - right.sort_order).map((child) => renderTreeNode(child, depth + 1)) : null}
      </div>
    );
  };

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
                <div className="space-y-0.5 overflow-y-auto custom-scrollbar max-h-[calc(100vh-250px)]">
                  {tree.map((node) => renderTreeNode(node))}
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
                      <span>Updated {timeAgo(activePage.updated_at)}</span>
                    </div>
                  </div>
                  <div className="prose dark:prose-invert max-w-none pt-4">
                    {selectedDoc.can_edit && activePage.can_edit ? (
                      <BlockEditor
                        key={activePage.id}
                        initialContent={activePage.content_blocks as never}
                        placeholder="Start writing..."
                        uploadFile={uploadFile}
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
                <div className="rounded-lg border border-app-border bg-app-bg p-4 space-y-3">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="app-text-control text-app-ink">Internal link</div>
                      <div className="app-text-caption text-gray-500">
                        Logged-in internal users can access this document through the generated link.
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
                        className="app-text-control rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
                      >
                        <Copy size={14} />
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

                <div className="rounded-lg border border-app-border bg-app-bg p-4 space-y-4">
                  <div>
                    <div className="app-text-control text-app-ink">Invite internal users</div>
                    <div className="app-text-caption text-gray-500">
                      Grant read or edit access to specific internal users.
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <select
                      value={shareUserId}
                      onChange={(event) => setShareUserId(event.target.value)}
                      className="app-text-body flex-1 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                    >
                      <option value="">Select user...</option>
                      {shareableUsers.map((user) => (
                        <option key={user.id} value={user.id}>
                          {user.full_name} ({user.email})
                        </option>
                      ))}
                    </select>
                    <select
                      value={shareAccessLevel}
                      onChange={(event) => setShareAccessLevel(event.target.value as 'read' | 'edit')}
                      className="app-text-body rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                    >
                      <option value="read">Can read</option>
                      <option value="edit">Can edit</option>
                    </select>
                    <button
                      onClick={() => void handleAddUserShare()}
                      disabled={!shareUserId}
                      className="app-text-control rounded-md bg-app-accent px-3 py-2 text-app-bg hover:opacity-90 disabled:opacity-50"
                    >
                      Add
                    </button>
                  </div>

                  <div className="space-y-2">
                    {sharingState?.users.length ? sharingState.users.map((user) => (
                      <div key={user.user_id} className="flex items-center justify-between rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
                        <div>
                          <div className="app-text-control text-app-ink">{user.full_name}</div>
                          <div className="app-text-caption text-gray-500">{user.email}</div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="app-text-caption text-gray-500">{user.access_level === 'edit' ? 'Can edit' : 'Can read'}</span>
                          <button
                            onClick={() => void handleRemoveUserShare(user.user_id)}
                            className="app-text-control rounded-md border border-app-border px-3 py-1.5 text-app-ink hover:bg-app-surface-hover"
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    )) : (
                      <div className="app-text-caption text-gray-500">No individual users have access.</div>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}

      {isListView ? (
        <div className="flex-1 flex flex-col overflow-hidden">
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
                        <td className="px-4 py-3 app-text-body-sm text-gray-400">{timeAgo(item.updated_at)}</td>
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
