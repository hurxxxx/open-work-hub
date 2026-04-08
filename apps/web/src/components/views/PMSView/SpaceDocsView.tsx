import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  FileText,
  Plus,
  Trash2,
  ChevronRight,
  ChevronDown,
  Loader2,
} from 'lucide-react';
import { BlockEditor } from '@aidoo/ui';
import type { BlockContent } from '@aidoo/ui';
import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { useMediaUpload } from '@/src/domains/media/use-media-upload';
import {
  createSpaceDocPage,
  deleteSpaceDocPage,
  listSpaceDocPages,
  updateSpaceDocPage,
  type PmsSpaceDocPage,
} from '@/src/domains/pms/pms-api';

type TreeNode = PmsSpaceDocPage & { children: TreeNode[] };

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function buildTree(pages: PmsSpaceDocPage[]): TreeNode[] {
  const byId = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];

  for (const page of pages) {
    byId.set(page.id, { ...page, children: [] });
  }

  for (const page of byId.values()) {
    const parentNode = page.parent_id ? byId.get(page.parent_id) : undefined;
    if (parentNode) {
      parentNode.children.push(page);
    } else {
      roots.push(page);
    }
  }

  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((left, right) => left.sort_order - right.sort_order || left.title.localeCompare(right.title, 'ko'));
    for (const node of nodes) {
      sortNodes(node.children);
    }
  };

  sortNodes(roots);
  return roots;
}

const PageTreeItem = ({
  node,
  selectedPageId,
  onSelect,
  onCreateChild,
  onDelete,
  depth = 0,
}: {
  node: TreeNode;
  selectedPageId: string | null;
  onSelect: (pageId: string) => void;
  onCreateChild: (parentId: string) => void;
  onDelete: (pageId: string) => void;
  depth?: number;
}) => {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = node.children.length > 0;

  return (
    <div className="space-y-0.5">
      <div
        className={cn(
          'app-text-body group flex items-center gap-1 rounded-md px-2 py-1.5 transition-colors',
          selectedPageId === node.id ? 'bg-clickup-hover text-clickup-text' : 'text-gray-400 hover:bg-clickup-hover hover:text-gray-300',
        )}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
      >
        <button
          onClick={() => hasChildren && setExpanded((current) => !current)}
          className="flex h-4 w-4 items-center justify-center text-gray-500"
        >
          {hasChildren ? (expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />) : null}
        </button>
        <button onClick={() => onSelect(node.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          <FileText size={14} className={selectedPageId === node.id ? 'text-clickup-purple' : 'text-gray-500'} />
          <span className="truncate">{node.title}</span>
        </button>
        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button onClick={() => onCreateChild(node.id)} className="text-gray-500 hover:text-clickup-text">
            <Plus size={12} />
          </button>
          <button onClick={() => onDelete(node.id)} className="text-gray-500 hover:text-red-400">
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {expanded && hasChildren && (
        <div className="space-y-0.5">
          {node.children.map((child) => (
            <PageTreeItem
              key={child.id}
              node={child}
              selectedPageId={selectedPageId}
              onSelect={onSelect}
              onCreateChild={onCreateChild}
              onDelete={onDelete}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const SpaceDocsView = ({ spaceId, spaceName }: { spaceId: string; spaceName?: string | null }) => {
  const navigate = useNavigate();
  const { docId } = useParams();
  const { token } = useAuth();
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const [pages, setPages] = useState<PmsSpaceDocPage[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pageTree = useMemo(() => buildTree(pages), [pages]);
  const selectedPage = pages.find((page) => page.id === docId) ?? null;

  const loadPages = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const response = await listSpaceDocPages(token, spaceId);
      setPages(response.items);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '문서 페이지를 불러오지 못했습니다.'));
    } finally {
      setLoading(false);
    }
  }, [spaceId, token]);

  useEffect(() => {
    void loadPages();
  }, [loadPages]);

  useEffect(() => {
    if (loading) return;
    if (!pages.length) return;
    if (!docId || !pages.some((page) => page.id === docId)) {
      navigate(`/tool/pms-space-${spaceId}-docs/${pages[0].id}`, { replace: true });
    }
  }, [docId, loading, navigate, pages, spaceId]);

  useEffect(() => {
    setTitleDraft(selectedPage?.title ?? '');
  }, [selectedPage]);

  useEffect(() => () => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
  }, []);

  const patchPage = useCallback(async (pageId: string, payload: Record<string, unknown>, fallbackMessage: string) => {
    if (!token) return null;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateSpaceDocPage(token, pageId, payload);
      setPages((current) => current.map((page) => (page.id === updated.id ? updated : page)));
      return updated;
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, fallbackMessage));
      return null;
    } finally {
      setSaving(false);
    }
  }, [token]);

  const handleCreatePage = useCallback(async (parentId: string | null = null) => {
    if (!token) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createSpaceDocPage(token, spaceId, {
        title: parentId ? 'Untitled Subpage' : 'Untitled Page',
        parent_id: parentId,
      });
      setPages((current) => [...current, created]);
      navigate(`/tool/pms-space-${spaceId}-docs/${created.id}`);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '페이지를 생성하지 못했습니다.'));
    } finally {
      setSaving(false);
    }
  }, [navigate, spaceId, token]);

  const handleDeletePage = useCallback(async (pageId: string) => {
    if (!token) return;
    setSaving(true);
    setError(null);
    try {
      await deleteSpaceDocPage(token, pageId);
      const remaining = pages.filter((page) => page.id !== pageId);
      setPages(remaining);
      if (docId === pageId) {
        if (remaining[0]) navigate(`/tool/pms-space-${spaceId}-docs/${remaining[0].id}`, { replace: true });
        else navigate(`/tool/pms-space-${spaceId}-docs`, { replace: true });
      }
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '페이지를 삭제하지 못했습니다.'));
    } finally {
      setSaving(false);
    }
  }, [docId, navigate, pages, spaceId, token]);

  const handleTitleSave = useCallback(async () => {
    if (!selectedPage || titleDraft.trim() === selectedPage.title) return;
    await patchPage(selectedPage.id, { title: titleDraft.trim() || 'Untitled Page' }, '페이지 제목을 저장하지 못했습니다.');
  }, [patchPage, selectedPage, titleDraft]);

  const handleContentChange = useCallback((content: BlockContent) => {
    if (!selectedPage) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      void patchPage(selectedPage.id, { content_blocks: content }, '페이지 내용을 저장하지 못했습니다.');
    }, 500);
  }, [patchPage, selectedPage]);

  return (
    <div className="h-full flex bg-clickup-bg">
      <div className="w-72 border-r border-clickup-border bg-clickup-sidebar flex flex-col">
        <div className="px-4 py-4 border-b border-clickup-border flex items-center justify-between">
          <div>
            <div className="app-text-overline text-gray-500">Space Docs</div>
            <div className="app-text-title-md text-clickup-text">{spaceName ?? 'Docs'}</div>
          </div>
          <button
            onClick={() => { void handleCreatePage(null); }}
            className="p-1 rounded hover:bg-clickup-hover text-gray-500 hover:text-clickup-text"
            title="Add page"
          >
            <Plus size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-3 custom-scrollbar space-y-1">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={16} className="animate-spin text-gray-500" />
            </div>
          ) : pageTree.length > 0 ? (
            pageTree.map((node) => (
              <PageTreeItem
                key={node.id}
                node={node}
                selectedPageId={selectedPage?.id ?? null}
                onSelect={(pageId) => navigate(`/tool/pms-space-${spaceId}-docs/${pageId}`)}
                onCreateChild={(parentId) => { void handleCreatePage(parentId); }}
                onDelete={(pageId) => { void handleDeletePage(pageId); }}
              />
            ))
          ) : (
            <button
              onClick={() => { void handleCreatePage(null); }}
              className="app-text-body w-full rounded-md border border-dashed border-clickup-border px-3 py-4 text-gray-500 transition-colors hover:border-clickup-purple hover:text-clickup-text"
            >
              Create the first page
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 min-w-0 flex flex-col">
        {error ? (
          <div className="app-text-body border-b border-red-500/20 bg-red-500/10 px-6 py-3 text-red-300">{error}</div>
        ) : null}

        {selectedPage ? (
          <>
            <div className="app-text-caption flex h-12 items-center justify-between border-b border-clickup-border px-6 text-gray-500">
              <div className="flex items-center gap-2">
                <FileText size={12} />
                <span>{spaceName ?? 'Space'} Docs</span>
              </div>
              <div className="flex items-center gap-3">
                {saving ? <Loader2 size={12} className="animate-spin" /> : null}
                <span>{selectedPage.created_by_name}</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar">
              <motion.div
                key={selectedPage.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="max-w-4xl mx-auto px-12 py-12 space-y-6"
              >
                <div className="space-y-3">
                  <input
                    value={titleDraft}
                    onChange={(event) => setTitleDraft(event.target.value)}
                    onBlur={() => { void handleTitleSave(); }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void handleTitleSave();
                      }
                    }}
                    className="app-text-title-xl w-full bg-transparent text-clickup-text outline-none placeholder:text-clickup-text/20"
                    placeholder="Untitled Page"
                  />
                  <div className="app-text-caption text-gray-500">
                    Last updated {new Date(selectedPage.updated_at).toLocaleString()}
                  </div>
                </div>

                <div className="prose max-w-none dark:prose-invert">
                  <BlockEditor
                    key={selectedPage.id}
                    initialContent={selectedPage.content_blocks ?? undefined}
                    placeholder="Start writing..."
                    uploadFile={uploadFile}
                    resolveFileUrl={resolveFileUrl}
                    onChange={handleContentChange}
                  />
                </div>
              </motion.div>
            </div>
          </>
        ) : (
          <div className="app-text-body flex-1 flex items-center justify-center text-gray-500">
            {loading ? <Loader2 size={18} className="animate-spin" /> : 'Select a page'}
          </div>
        )}
      </div>
    </div>
  );
};
