import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  Files,
  FileText,
  Sparkles,
  Star,
  X,
  Plus,
  Filter,
  Search,
  MoreHorizontal,
  Settings,
  Trash2,
  Link as LinkIcon,
  Lock,
  Globe,
  ChevronDown,
  ChevronRight,
  Loader2,
  Pencil,
} from 'lucide-react';
import { BlockEditor, useConfirm, usePrompt } from '@aidoo/ui';
import { useMediaUpload } from '@/src/domains/media/use-media-upload';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { cn } from '@/src/lib/utils';
import {
  listSpaces,
  listDocsHub,
  toggleDocFavorite,
  toggleDocPrivate,
  recordDocView,
  createSpaceDoc,
  listSpaceDocPages,
  createSpaceDocPage,
  updateSpaceDocPage,
  deleteSpaceDocPage,
  deleteSpaceDoc,
  updateSpaceDoc,
  type DocsHubItem,
  type PmsSpace,
  type PmsSpaceDocPage,
} from '@/src/domains/pms/pms-api';

// Category mapping from toolId to API category param
const CATEGORY_MAP: Record<string, string> = {
  'docs-all': 'all',
  'docs-my': 'my',
  'docs-shared': 'shared',
  'docs-private': 'private',
  'docs-notes': 'all', // Phase 2: tag-based filter
  'docs-recent': 'recent',
  'docs-archived': 'archived',
};

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

type TreeNode = PmsSpaceDocPage & { children: TreeNode[] };

function buildTree(pages: PmsSpaceDocPage[]): TreeNode[] {
  const byId = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];
  for (const page of pages) {
    byId.set(page.id, { ...page, children: [] });
  }
  for (const page of pages) {
    const node = byId.get(page.id)!;
    if (page.parent_id && byId.has(page.parent_id)) {
      byId.get(page.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots.sort((a, b) => a.sort_order - b.sort_order);
}

// Templates data (Phase 1: just titles, Phase 3: real templates)
const TEMPLATES = [
  { title: 'Project Overview', desc: 'Summarize goals, scope, and milestones', icon: '📋' },
  { title: 'Meeting Notes', desc: 'Capture an agenda, notes, and action items', icon: '📝' },
  { title: 'Wiki', desc: 'Organize information in one place', icon: '📚' },
];

export const DocsView = () => {
  const { toolId, docId } = useParams();
  const navigate = useNavigate();
  const { token } = useAuth();
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();

  // List view state
  const [docs, setDocs] = useState<DocsHubItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [sortBy, setSortBy] = useState('updated_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

  // Create doc modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [teams, setTeams] = useState<PmsSpace[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState('');
  const [newDocTitle, setNewDocTitle] = useState('');
  const [creating, setCreating] = useState(false);

  // Editor view state
  const [pages, setPages] = useState<PmsSpaceDocPage[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [pageContent, setPageContent] = useState<Record<string, unknown>[] | null>(null);
  const [editorLoading, setEditorLoading] = useState(true);
  const [selectedDoc, setSelectedDoc] = useState<DocsHubItem | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  const searchTimerRef = useRef<ReturnType<typeof setTimeout>>(null);

  const activeCategory = toolId
    ? (CATEGORY_MAP[toolId] || 'all')
    : 'all';

  const categoryLabels: Record<string, string> = {
    'docs-all': 'All Docs',
    'docs-my': 'My Docs',
    'docs-shared': 'Shared with me',
    'docs-private': 'Private',
    'docs-notes': 'Meeting Notes',
    'docs-recent': 'Recent Pages',
    'docs-archived': 'Archived',
  };
  const activeCategoryLabel = (toolId && categoryLabels[toolId]) || 'All Docs';

  // Fetch docs list
  const fetchDocs = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await listDocsHub(token, {
        category: activeCategory,
        q: searchQuery || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      setDocs(res.items);
      setTotal(res.total);
    } catch {
      setDocs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [token, activeCategory, searchQuery, sortBy, sortDir]);

  useEffect(() => {
    if (!docId) fetchDocs();
  }, [fetchDocs, docId]);

  // Debounced search
  const handleSearchChange = (val: string) => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => setSearchQuery(val), 300);
  };

  // Fetch teams for create modal
  const openCreateModal = async (templateTitle?: string) => {
    if (!token) return;
    try {
      const t = await listSpaces(token);
      const activeTeams = t.filter((item) => item.current_user_role);
      setTeams(activeTeams);
      if (activeTeams.length === 1) setSelectedTeamId(activeTeams[0].id);
      else setSelectedTeamId('');
    } catch {
      setTeams([]);
    }
    setNewDocTitle(templateTitle || '');
    setShowCreateModal(true);
  };

  const handleCreateDoc = async () => {
    if (!token || !selectedTeamId || !newDocTitle.trim()) return;
    setCreating(true);
    try {
      const doc = await createSpaceDoc(token, selectedTeamId, { title: newDocTitle.trim() });
      setShowCreateModal(false);
      setNewDocTitle('');
      // Pre-set selectedDoc so the editor useEffect can load pages immediately
      const teamName = teams.find(t => t.id === selectedTeamId)?.name ?? '';
      setSelectedDoc({
        id: doc.id,
        team_id: doc.team_id,
        space_name: teamName,
        title: doc.title,
        page_count: 0,
        created_by_id: doc.created_by_id,
        created_by_name: doc.created_by_name,
        is_favorite: false,
        is_private: false,
        last_viewed_at: null,
        created_at: doc.created_at,
        updated_at: doc.updated_at,
        trashed_at: null,
      });
      navigate(toolId ? `/tool/${toolId}/${doc.id}` : `/docs/${doc.id}`);
    } catch {
      // error
    } finally {
      setCreating(false);
    }
  };

  // Favorite toggle
  const handleToggleFavorite = async (e: React.MouseEvent, docItem: DocsHubItem) => {
    e.stopPropagation();
    if (!token) return;
    try {
      const res = await toggleDocFavorite(token, docItem.id);
      setDocs(prev =>
        prev.map(d => (d.id === docItem.id ? { ...d, is_favorite: res.is_favorite } : d)),
      );
    } catch { /* */ }
  };

  // Click doc row → navigate to editor
  const handleDocClick = (doc: DocsHubItem) => {
    navigate(toolId ? `/tool/${toolId}/${doc.id}` : `/docs/${doc.id}`);
  };

  const handleBack = () => {
    navigate(toolId ? `/tool/${toolId}` : '/docs');
  };

  // Column sort
  const handleSort = (col: string) => {
    if (sortBy === col) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(col);
      setSortDir('desc');
    }
  };

  // Context menu actions
  const handleRename = async (doc: DocsHubItem) => {
    setMenuOpenId(null);
    if (!token) return;
    const newTitle = await prompt({ title: 'Rename Document', defaultValue: doc.title });
    if (newTitle && newTitle.trim() && newTitle.trim() !== doc.title) {
      try {
        await updateSpaceDoc(token, doc.id, { title: newTitle.trim() });
        fetchDocs();
      } catch { /* */ }
    }
  };

  const handleDelete = async (doc: DocsHubItem) => {
    setMenuOpenId(null);
    if (!token) return;
    const ok = await confirm({ title: `Delete "${doc.title}"?`, description: 'This document will be moved to trash.' });
    if (ok) {
      try {
        await deleteSpaceDoc(token, doc.id);
        fetchDocs();
      } catch { /* */ }
    }
  };

  const handleTogglePrivate = async (doc: DocsHubItem) => {
    setMenuOpenId(null);
    if (!token) return;
    try {
      const res = await toggleDocPrivate(token, doc.id);
      setDocs(prev =>
        prev.map(d => (d.id === doc.id ? { ...d, is_private: res.is_private } : d)),
      );
    } catch { /* */ }
  };

  // ── Editor View ──────────────────────────────────────────────────

  // Load doc pages when docId changes
  useEffect(() => {
    if (!docId || !token) return;
    setEditorLoading(true);
    setSelectedPageId(null);
    setPageContent(null);

    // Find doc info: pre-set selectedDoc (from create), docs list, or hub fetch
    const docInfo = docs.find(d => d.id === docId) ?? (selectedDoc?.id === docId ? selectedDoc : null);
    if (docInfo) {
      setSelectedDoc(docInfo);
      recordDocView(token, docInfo.id).catch(() => {});
      loadPages(docInfo.team_id, docInfo.id);
    } else {
      // Direct URL load → fetch from hub
      listDocsHub(token, { category: 'all', page_size: 100 })
        .then(async (allRes) => {
          const found = allRes.items.find(d => d.id === docId);
          if (found) {
            setSelectedDoc(found);
            recordDocView(token, found.id).catch(() => {});
            loadPages(found.team_id, found.id);
          } else {
            // Also check archived
            const archRes = await listDocsHub(token, { category: 'archived', page_size: 100 });
            const archFound = archRes.items.find(d => d.id === docId);
            if (archFound) {
              setSelectedDoc(archFound);
              recordDocView(token, archFound.id).catch(() => {});
              loadPages(archFound.team_id, archFound.id);
            } else {
              setEditorLoading(false);
            }
          }
        })
        .catch(() => setEditorLoading(false));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, token]);

  const loadPages = async (teamId: string, spaceDocId: string) => {
    if (!token) return;
    try {
      const res = await listSpaceDocPages(token, teamId, spaceDocId);
      const pgs = res.items ?? [];
      setPages(pgs);
      if (pgs.length > 0) {
        setSelectedPageId(pgs[0].id);
        setPageContent(pgs[0].content_blocks ?? null);
      }
    } catch { /* */ }
    setEditorLoading(false);
  };

  // Load page content when selectedPageId changes
  useEffect(() => {
    const pg = pages.find(p => p.id === selectedPageId);
    if (pg) {
      setPageContent(pg.content_blocks ?? null);
    }
  }, [selectedPageId, pages]);

  // Save page content on editor change (debounced)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>(null);
  const handleEditorChange = (blocks: Record<string, unknown>[]) => {
    if (!token || !selectedPageId) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      try {
        await updateSpaceDocPage(token, selectedPageId, { content_blocks: blocks });
      } catch { /* */ }
    }, 1000);
  };

  // Add page
  const handleAddPage = async (parentId?: string | null) => {
    if (!token || !selectedDoc) return;
    const title = await prompt({ title: 'New Page', defaultValue: 'Untitled' });
    if (!title || !title.trim()) return;
    try {
      const pg = await createSpaceDocPage(token, selectedDoc.team_id, {
        title: title.trim(),
        space_doc_id: selectedDoc.id,
        parent_id: parentId ?? null,
      });
      setPages(prev => [...prev, pg]);
      setSelectedPageId(pg.id);
    } catch { /* */ }
  };

  // Delete page
  const handleDeletePage = async (pageId: string) => {
    if (!token) return;
    const pg = pages.find(p => p.id === pageId);
    const ok = await confirm({ title: `Delete "${pg?.title || 'this page'}"?`, description: 'This action cannot be undone.' });
    if (!ok) return;
    try {
      await deleteSpaceDocPage(token, pageId);
      setPages(prev => prev.filter(p => p.id !== pageId));
      if (selectedPageId === pageId) {
        const remaining = pages.filter(p => p.id !== pageId);
        setSelectedPageId(remaining.length > 0 ? remaining[0].id : null);
      }
    } catch { /* */ }
  };

  const toggleExpand = (nodeId: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  // Render page tree node
  const renderTreeNode = (node: TreeNode, depth = 0) => (
    <div key={node.id}>
      <button
        onClick={() => setSelectedPageId(node.id)}
        className={cn(
          'app-text-body-sm group flex w-full items-center gap-1 rounded px-2 py-1.5 transition-all',
          selectedPageId === node.id
            ? 'bg-clickup-purple/10 text-clickup-purple'
            : 'text-gray-400 hover:bg-clickup-hover hover:text-gray-200',
        )}
        style={{ paddingLeft: `${8 + depth * 16}px` }}
      >
        {node.children.length > 0 ? (
          <span
            onClick={e => { e.stopPropagation(); toggleExpand(node.id); }}
            className="flex-shrink-0"
          >
            {expandedNodes.has(node.id)
              ? <ChevronDown size={12} className="text-gray-500" />
              : <ChevronRight size={12} className="text-gray-500" />
            }
          </span>
        ) : (
          <span className="w-3" />
        )}
        <FileText size={14} className={selectedPageId === node.id ? 'text-clickup-purple' : 'text-gray-500'} />
        <span className="truncate flex-1 text-left">{node.title}</span>
        <span
          className="opacity-0 group-hover:opacity-100"
          onClick={e => { e.stopPropagation(); handleDeletePage(node.id); }}
        >
          <Trash2 size={12} className="text-gray-500 hover:text-red-400" />
        </span>
      </button>
      {expandedNodes.has(node.id) &&
        node.children
          .sort((a, b) => a.sort_order - b.sort_order)
          .map(child => renderTreeNode(child, depth + 1))
      }
    </div>
  );

  // Document Editor View
  const renderEditor = () => {
    if (editorLoading) {
      return (
        <div className="flex-1 flex items-center justify-center bg-clickup-bg">
          <Loader2 size={32} className="animate-spin text-clickup-purple" />
        </div>
      );
    }

    if (!selectedDoc) {
      return (
        <div className="flex-1 flex items-center justify-center text-gray-500 bg-clickup-bg">
          <div className="text-center">
            <FileText size={48} className="mx-auto mb-4 opacity-20" />
            <h2 className="app-text-title-md text-clickup-text">Document not found</h2>
            <button onClick={handleBack} className="app-text-control mt-4 text-clickup-purple hover:underline">
              Go back
            </button>
          </div>
        </div>
      );
    }

    const tree = buildTree(pages);
    const activePage = pages.find(p => p.id === selectedPageId);

    return (
      <div className="h-full flex flex-col bg-clickup-bg overflow-hidden">
        {/* Top Header */}
        <div className="h-12 border-b border-clickup-border flex items-center justify-between px-4 bg-clickup-sidebar">
          <div className="app-text-caption flex items-center gap-2">
            <span className="cursor-pointer text-gray-500 hover:text-gray-300" onClick={handleBack}>
              Docs
            </span>
            <span className="text-gray-600">/</span>
            <div className="flex items-center gap-2 px-2 py-1 hover:bg-clickup-hover rounded cursor-pointer">
              <FileText size={14} className="text-clickup-purple" />
              <span className="app-text-control text-clickup-text">{selectedDoc.title}</span>
              <Star
                size={12}
                className={cn(
                  'text-gray-600 cursor-pointer',
                  selectedDoc.is_favorite && 'text-yellow-500 fill-yellow-500',
                )}
                onClick={e => handleToggleFavorite(e, selectedDoc)}
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button className="app-text-control-sm flex items-center gap-1.5 rounded-md px-3 py-1.5 text-clickup-purple transition-colors hover:bg-clickup-purple/10">
              <Sparkles size={14} />
              <span>Ask AI</span>
            </button>
            <button onClick={handleBack} className="p-1.5 hover:bg-red-500/20 hover:text-red-500 rounded text-gray-500 transition-colors">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* Page Sidebar */}
          <div className="w-60 border-r border-clickup-border bg-clickup-sidebar flex flex-col overflow-hidden">
            <div className="p-4 space-y-4">
              <h2 className="app-text-title-sm px-2 text-clickup-text truncate">{selectedDoc.title}</h2>
              <div>
                <div className="flex items-center justify-between px-2 mb-2">
                  <span className="app-text-overline text-gray-500">Pages</span>
                </div>
                <div className="space-y-0.5 overflow-y-auto custom-scrollbar max-h-[calc(100vh-250px)]">
                  {tree.map(node => renderTreeNode(node))}
                  <button
                    onClick={() => handleAddPage(null)}
                    className="app-text-body-sm flex w-full items-center gap-2 rounded px-3 py-1.5 text-gray-500 transition-all hover:bg-clickup-hover hover:text-clickup-purple"
                  >
                    <Plus size={14} />
                    <span>Add page</span>
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-auto p-4 border-t border-clickup-border space-y-1">
              <button className="app-text-body-sm flex w-full items-center gap-2 rounded px-3 py-1.5 text-gray-500 hover:bg-clickup-hover">
                <Settings size={14} />
                <span>Doc Settings</span>
              </button>
              <button
                onClick={() => handleDelete(selectedDoc)}
                className="app-text-body-sm flex w-full items-center gap-2 rounded px-3 py-1.5 text-gray-500 hover:bg-clickup-hover hover:text-red-400"
              >
                <Trash2 size={14} />
                <span>Delete Doc</span>
              </button>
            </div>
          </div>

          {/* Editor Content */}
          <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-[#1e1e24] overflow-y-auto custom-scrollbar">
            <div className="max-w-4xl mx-auto py-12 px-12 w-full">
              <div className="space-y-6">
                {activePage ? (
                  <>
                    <div className="space-y-4">
                      <h1 className="app-text-title-xl text-clickup-text">{activePage.title}</h1>
                      <div className="app-text-caption flex items-center gap-3 text-gray-500">
                        <div className="flex items-center gap-1.5">
                          <div className="app-text-micro flex h-5 w-5 items-center justify-center rounded-full bg-clickup-purple font-bold text-clickup-bg">
                            {selectedDoc.created_by_name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                          </div>
                          <span className="app-text-control text-clickup-text">{selectedDoc.created_by_name}</span>
                        </div>
                        <span>·</span>
                        <span>Updated {timeAgo(selectedDoc.updated_at)}</span>
                      </div>
                    </div>
                    <div className="prose dark:prose-invert max-w-none pt-4">
                      <BlockEditor
                        key={selectedPageId}
                        initialContent={pageContent as never}
                        placeholder="Start writing..."
                        uploadFile={uploadFile}
                        resolveFileUrl={resolveFileUrl}
                        onChange={handleEditorChange}
                      />
                    </div>
                  </>
                ) : (
                  <div className="text-center py-20">
                    <FileText size={48} className="mx-auto mb-4 text-gray-600 opacity-20" />
                    <p className="app-text-body text-gray-500 mb-4">No pages yet</p>
                    <button
                      onClick={() => handleAddPage(null)}
                      className="app-text-control rounded-md bg-clickup-purple px-4 py-2 text-clickup-bg hover:opacity-90"
                    >
                      Add first page
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // ── Main Render ──────────────────────────────────────────────────

  return (
    <div className="h-full w-full flex flex-col min-w-0 bg-clickup-bg overflow-hidden relative">
      {confirmDialog}
      {promptDialog}

      {/* Create Doc Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50" onClick={() => setShowCreateModal(false)}>
          <div className="w-full max-w-md rounded-lg border border-clickup-border bg-clickup-sidebar p-6 space-y-4" onClick={e => e.stopPropagation()}>
            <h2 className="app-text-title-md text-clickup-text">New Document</h2>
            <div className="space-y-3">
              <div>
                <label className="app-text-caption text-gray-500 mb-1 block">Title</label>
                <input
                  type="text"
                  value={newDocTitle}
                  onChange={e => setNewDocTitle(e.target.value)}
                  placeholder="Document title..."
                  className="app-text-body w-full rounded-md border border-clickup-border bg-clickup-bg px-3 py-2 text-clickup-text focus:border-clickup-purple focus:outline-none"
                  autoFocus
                  onKeyDown={e => { if (e.key === 'Enter') handleCreateDoc(); }}
                />
              </div>
              {teams.length > 1 && (
                <div>
                  <label className="app-text-caption text-gray-500 mb-1 block">Space</label>
                  <select
                    value={selectedTeamId}
                    onChange={e => setSelectedTeamId(e.target.value)}
                    className="app-text-body w-full rounded-md border border-clickup-border bg-clickup-bg px-3 py-2 text-clickup-text focus:border-clickup-purple focus:outline-none"
                  >
                    <option value="">Select a space...</option>
                    {teams.map(t => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowCreateModal(false)}
                className="app-text-control rounded-md border border-clickup-border px-4 py-2 text-clickup-text hover:bg-clickup-hover"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateDoc}
                disabled={creating || !newDocTitle.trim() || !selectedTeamId}
                className="app-text-control rounded-md bg-clickup-purple px-4 py-2 text-clickup-bg hover:opacity-90 disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      <AnimatePresence mode="wait">
        {!docId ? (
          <motion.div
            key="list"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 flex flex-col overflow-hidden"
          >
            <div className="p-8 space-y-5 overflow-y-auto h-full custom-scrollbar">
              {/* Header */}
              <div className="flex items-center justify-between">
                <h1 className="app-text-title-lg text-clickup-text">{activeCategoryLabel}</h1>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => openCreateModal()}
                    className="app-text-control flex items-center gap-2 rounded-md bg-clickup-purple px-4 py-2 text-clickup-bg shadow-lg shadow-purple-500/20 transition-opacity hover:opacity-90"
                  >
                    <Plus size={16} />
                    <span>New Doc</span>
                  </button>
                </div>
              </div>

              {/* Templates */}
              <div className="flex gap-3">
                {TEMPLATES.map(t => (
                  <button
                    key={t.title}
                    onClick={() => openCreateModal(t.title)}
                    className="flex items-center gap-3 rounded-lg border border-clickup-border bg-clickup-sidebar px-4 py-3 text-left transition-colors hover:border-clickup-purple/30 hover:bg-clickup-hover flex-1"
                  >
                    <span className="text-2xl">{t.icon}</span>
                    <div>
                      <div className="app-text-control text-clickup-text">{t.title}</div>
                      <div className="app-text-micro text-gray-500">{t.desc}</div>
                    </div>
                  </button>
                ))}
              </div>

              {/* Filter Bar */}
              <div className="flex items-center gap-4 border-b border-clickup-border pb-2">
                <button className="app-text-control-sm flex items-center gap-1.5 rounded px-2 py-1 text-gray-500 hover:bg-clickup-hover hover:text-clickup-text">
                  <Filter size={14} />
                  <span>Filters</span>
                </button>
                <div className="app-text-caption ml-auto flex items-center gap-2 text-gray-500">
                  <span>Tags:</span>
                  <button className="px-2 py-0.5 bg-clickup-sidebar border border-clickup-border rounded hover:bg-clickup-hover">View all</button>
                </div>
                {searchOpen ? (
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={14} />
                    <input
                      type="text"
                      placeholder="Search docs..."
                      defaultValue={searchQuery}
                      onChange={e => handleSearchChange(e.target.value)}
                      className="app-text-body-sm w-64 rounded-md border border-clickup-border bg-clickup-sidebar py-1.5 pl-9 pr-4 text-clickup-text focus:border-clickup-purple focus:outline-none"
                      autoFocus
                      onBlur={e => { if (!e.target.value) setSearchOpen(false); }}
                    />
                  </div>
                ) : (
                  <button
                    onClick={() => setSearchOpen(true)}
                    className="p-1.5 rounded text-gray-500 hover:bg-clickup-hover hover:text-clickup-text"
                  >
                    <Search size={16} />
                  </button>
                )}
              </div>

              {/* Table */}
              {loading ? (
                <div className="flex items-center justify-center py-20">
                  <Loader2 size={32} className="animate-spin text-clickup-purple" />
                </div>
              ) : docs.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center py-20 text-center">
                  <div className="w-24 h-24 bg-clickup-sidebar rounded-full flex items-center justify-center mb-6">
                    <FileText size={48} className="text-gray-600 opacity-20" />
                  </div>
                  <h2 className="app-text-title-md mb-2 text-clickup-text">No Docs found</h2>
                  <p className="app-text-body mb-8 max-w-xs mx-auto text-gray-500">
                    Create anything from project plans to knowledge bases with Docs
                  </p>
                  <button
                    onClick={() => openCreateModal()}
                    className="app-text-control rounded-md bg-clickup-purple px-6 py-2 font-bold text-clickup-bg transition-opacity hover:opacity-90"
                  >
                    New Doc
                  </button>
                </div>
              ) : (
                <div className="border border-clickup-border rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-clickup-border bg-clickup-sidebar">
                        <th
                          className="app-text-overline text-left px-4 py-2.5 text-gray-500 cursor-pointer hover:text-clickup-text"
                          onClick={() => handleSort('title')}
                        >
                          <span className="flex items-center gap-1">
                            Name
                            {sortBy === 'title' && (sortDir === 'asc' ? ' ↑' : ' ↓')}
                          </span>
                        </th>
                        <th className="app-text-overline text-left px-4 py-2.5 text-gray-500 w-36">Location</th>
                        <th className="app-text-overline text-left px-4 py-2.5 text-gray-500 w-24">Tags</th>
                        <th
                          className="app-text-overline text-left px-4 py-2.5 text-gray-500 w-32 cursor-pointer hover:text-clickup-text"
                          onClick={() => handleSort('updated_at')}
                        >
                          <span className="flex items-center gap-1">
                            Date updated
                            {sortBy === 'updated_at' && (sortDir === 'asc' ? ' ↑' : ' ↓')}
                          </span>
                        </th>
                        <th
                          className="app-text-overline text-left px-4 py-2.5 text-gray-500 w-32 cursor-pointer hover:text-clickup-text"
                          onClick={() => handleSort('last_viewed_at')}
                        >
                          <span className="flex items-center gap-1">
                            Date viewed
                            {sortBy === 'last_viewed_at' && (sortDir === 'asc' ? ' ↑' : ' ↓')}
                          </span>
                        </th>
                        <th className="app-text-overline text-center px-4 py-2.5 text-gray-500 w-20">Sharing</th>
                        <th className="w-10" />
                      </tr>
                    </thead>
                    <tbody>
                      {docs.map(doc => (
                        <tr
                          key={doc.id}
                          onClick={() => handleDocClick(doc)}
                          className="border-b border-clickup-border last:border-b-0 hover:bg-clickup-hover cursor-pointer group transition-colors"
                        >
                          {/* Name */}
                          <td className="px-4 py-2.5">
                            <div className="flex items-center gap-2.5">
                              <Star
                                size={14}
                                className={cn(
                                  'flex-shrink-0 cursor-pointer transition-colors',
                                  doc.is_favorite
                                    ? 'text-yellow-500 fill-yellow-500'
                                    : 'text-transparent group-hover:text-gray-600 hover:!text-yellow-500',
                                )}
                                onClick={e => handleToggleFavorite(e, doc)}
                              />
                              <FileText size={16} className="flex-shrink-0 text-clickup-purple" />
                              <span className="app-text-body text-clickup-text truncate">{doc.title}</span>
                              {doc.page_count > 0 && (
                                <span className="app-text-micro flex items-center gap-0.5 rounded border border-clickup-border bg-clickup-sidebar px-1.5 py-0.5 text-gray-500 flex-shrink-0">
                                  <Files size={10} />
                                  {doc.page_count}
                                </span>
                              )}
                            </div>
                          </td>
                          {/* Location */}
                          <td className="px-4 py-2.5">
                            <span className="app-text-caption text-gray-500">{doc.space_name || '–'}</span>
                          </td>
                          {/* Tags */}
                          <td className="px-4 py-2.5">
                            <span className="app-text-caption text-gray-600">–</span>
                          </td>
                          {/* Date updated */}
                          <td className="px-4 py-2.5">
                            <span className="app-text-caption text-gray-500">{timeAgo(doc.updated_at)}</span>
                          </td>
                          {/* Date viewed */}
                          <td className="px-4 py-2.5">
                            <span className="app-text-caption text-gray-500">
                              {doc.last_viewed_at ? timeAgo(doc.last_viewed_at) : '–'}
                            </span>
                          </td>
                          {/* Sharing */}
                          <td className="px-4 py-2.5 text-center">
                            {doc.is_private ? (
                              <Lock size={14} className="inline text-gray-500" />
                            ) : (
                              <Globe size={14} className="inline text-green-500" />
                            )}
                          </td>
                          {/* More */}
                          <td className="px-2 py-2.5 relative">
                            <button
                              onClick={e => {
                                e.stopPropagation();
                                setMenuOpenId(menuOpenId === doc.id ? null : doc.id);
                              }}
                              className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-clickup-hover text-gray-500"
                            >
                              <MoreHorizontal size={16} />
                            </button>
                            {menuOpenId === doc.id && (
                              <div className="absolute right-0 top-full z-50 w-44 rounded-md border border-clickup-border bg-clickup-sidebar shadow-lg py-1">
                                <button
                                  onClick={e => { e.stopPropagation(); handleRename(doc); }}
                                  className="app-text-body-sm flex w-full items-center gap-2 px-3 py-1.5 text-clickup-text hover:bg-clickup-hover"
                                >
                                  <Pencil size={14} /> Rename
                                </button>
                                <button
                                  onClick={e => { e.stopPropagation(); handleToggleFavorite(e, doc); setMenuOpenId(null); }}
                                  className="app-text-body-sm flex w-full items-center gap-2 px-3 py-1.5 text-clickup-text hover:bg-clickup-hover"
                                >
                                  <Star size={14} /> {doc.is_favorite ? 'Unfavorite' : 'Favorite'}
                                </button>
                                <button
                                  onClick={e => { e.stopPropagation(); handleTogglePrivate(doc); }}
                                  className="app-text-body-sm flex w-full items-center gap-2 px-3 py-1.5 text-clickup-text hover:bg-clickup-hover"
                                >
                                  {doc.is_private ? <Globe size={14} /> : <Lock size={14} />}
                                  {doc.is_private ? 'Make Public' : 'Make Private'}
                                </button>
                                <div className="border-t border-clickup-border my-1" />
                                <button
                                  onClick={e => { e.stopPropagation(); handleDelete(doc); }}
                                  className="app-text-body-sm flex w-full items-center gap-2 px-3 py-1.5 text-red-400 hover:bg-clickup-hover"
                                >
                                  <Trash2 size={14} /> Delete
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="editor"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 z-10 flex flex-col bg-clickup-bg overflow-hidden"
          >
            {renderEditor()}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
