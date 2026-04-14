import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  MoreHorizontal,
  Plus,
  Trash2,
} from 'lucide-react';
import { BlockViewer, CollaborativeBlockEditor } from '@aidoo/ui';
import type { BlockContent } from '@aidoo/ui';

import { useConfirm, usePrompt } from '@aidoo/ui';

import { cn } from '@/src/lib/utils';
import { teamRoleAllows } from '@/src/domains/auth/auth-api';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';
import { useMediaUpload } from '@/src/domains/media/use-media-upload';
import {
  getDocsCollabSession,
  makeDocsPageRef,
  saveDocsCollabSnapshot,
} from '@/src/domains/docs/docs-api';
import {
  createSpaceDoc,
  createSpaceDocPage,
  deleteSpaceDoc,
  deleteSpaceDocPage,
  getSpaceDocPage,
  listSpaceDocPages,
  listSpaceDocs,
  listSpaces,
  updateSpaceDoc,
  updateSpaceDocPage,
  type PmsSpaceDoc,
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
  canEdit,
  depth = 0,
}: {
  node: TreeNode;
  selectedPageId: string | null;
  onSelect: (pageId: string) => void;
  onCreateChild: (parentId: string) => void;
  onDelete: (pageId: string) => void;
  canEdit: boolean;
  depth?: number;
}) => {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = node.children.length > 0;

  return (
    <div className="space-y-0.5">
      <div
        className={cn(
          'app-text-body group flex items-center gap-1 rounded-md px-2 py-1.5 transition-colors',
          selectedPageId === node.id ? 'bg-app-surface-hover text-app-ink' : 'text-gray-400 hover:bg-app-surface-hover hover:text-gray-300',
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
          <FileText size={14} className={selectedPageId === node.id ? 'text-app-accent' : 'text-gray-500'} />
          <span className="truncate">{node.title}</span>
        </button>
        {canEdit ? (
          <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            <button onClick={() => onCreateChild(node.id)} className="text-gray-500 hover:text-app-ink">
              <Plus size={12} />
            </button>
            <button onClick={() => onDelete(node.id)} className="text-gray-500 hover:text-red-400">
              <Trash2 size={12} />
            </button>
          </div>
        ) : null}
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
              canEdit={canEdit}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const SpaceDocsView = ({ spaceId, spaceName, docId: spaceDocId }: { spaceId: string; spaceName?: string | null; docId?: string | null }) => {
  const navigate = useNavigate();
  const { docId: pageId, workspaceSlug } = useParams();
  const { token } = useAuth();
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();
  const [collections, setCollections] = useState<PmsSpaceDoc[]>([]);
  const [pages, setPages] = useState<PmsSpaceDocPage[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(true);
  const [loadingPages, setLoadingPages] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [spaceRole, setSpaceRole] = useState<string | null>(null);
  const [spaceRoleResolved, setSpaceRoleResolved] = useState(false);
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  const basePath = `/tool/pms-space-${spaceId}-docs`;
  const collectionPath = useCallback((docId: string) => `${basePath}-${docId}`, [basePath]);
  const pagePath = useCallback((docId: string, currentPageId: string) => `${collectionPath(docId)}/${currentPageId}`, [collectionPath]);

  const selectedCollection = collections.find((doc) => doc.id === spaceDocId) ?? null;
  const selectedPage = pages.find((page) => page.id === pageId) ?? null;
  const pageTree = useMemo(() => buildTree(pages), [pages]);
  const canAccessSpaceDocs = teamRoleAllows(spaceRole, 'viewer');
  const canEditPages = teamRoleAllows(spaceRole, 'member');
  const canManageCollections = teamRoleAllows(spaceRole, 'admin');

  useEffect(() => {
    if (!token) {
      setSpaceRole(null);
      setSpaceRoleResolved(true);
      return;
    }

    let cancelled = false;
    setSpaceRoleResolved(false);
    void listSpaces(token)
      .then((items) => {
        if (cancelled) return;
        const currentTeam = items.find((item) => item.id === spaceId);
        setSpaceRole(currentTeam?.current_user_role ?? null);
      })
      .catch(() => {
        if (!cancelled) {
          setSpaceRole(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSpaceRoleResolved(true);
        }
      });

    return () => { cancelled = true; };
  }, [spaceId, token]);

  const loadCollections = useCallback(async () => {
    if (!token) return;
    setLoadingCollections(true);
    try {
      const response = await listSpaceDocs(token, spaceId);
      setCollections(response.items);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '문서 컬렉션을 불러오지 못했습니다.'));
    } finally {
      setLoadingCollections(false);
    }
  }, [spaceId, token]);


  useEffect(() => {
    if (!spaceRoleResolved) {
      return;
    }
    if (!canAccessSpaceDocs) {
      setCollections([]);
      setPages([]);
      setLoadingCollections(false);
      setLoadingPages(false);
      return;
    }
    void loadCollections();
  }, [canAccessSpaceDocs, loadCollections, spaceRoleResolved]);

  const pageIdRef = useRef(pageId);
  pageIdRef.current = pageId;

  useEffect(() => {
    if (!canAccessSpaceDocs || !selectedCollection) {
      setPages([]);
      setLoadingPages(false);
      return;
    }
    let cancelled = false;
    const docId = selectedCollection.id;
    setLoadingPages(true);
    void listSpaceDocPages(token!, spaceId, docId)
      .then((response) => {
        if (cancelled) return;
        setPages(response.items);
        if (!pageIdRef.current && response.items[0]) {
          navigateRef.current(pagePath(docId, response.items[0].id), { replace: true });
        }
      })
      .catch((caughtError) => {
        if (!cancelled) setError(getErrorMessage(caughtError, '문서 페이지를 불러오지 못했습니다.'));
      })
      .finally(() => {
        if (!cancelled) setLoadingPages(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canAccessSpaceDocs, pagePath, selectedCollection, spaceId, token]);

  useEffect(() => {
    if (!spaceDocId || !pageId || loadingCollections) return;
    if (selectedCollection) return;
    navigate(basePath, { replace: true });
  }, [basePath, loadingCollections, navigate, pageId, selectedCollection, spaceDocId]);

  useEffect(() => {
    if (!token || spaceDocId || !pageId) return;
    let cancelled = false;

    void getSpaceDocPage(token, pageId)
      .then((page) => {
        if (cancelled) return;
        if (page.team_id !== spaceId || !page.space_doc_id) {
          navigate(basePath, { replace: true });
          return;
        }
        navigate(pagePath(page.space_doc_id, page.id), { replace: true });
      })
      .catch(() => {
        if (!cancelled) navigate(basePath, { replace: true });
      });

    return () => { cancelled = true; };
  }, [basePath, navigate, pageId, pagePath, spaceDocId, spaceId, token]);

  useEffect(() => {
    if (!selectedCollection || loadingPages || !pageId) return;
    if (!pages.some((page) => page.id === pageId)) {
      if (pages[0]) navigate(pagePath(selectedCollection.id, pages[0].id), { replace: true });
    }
  }, [loadingPages, navigate, pageId, pagePath, pages, selectedCollection]);

  useEffect(() => {
    setTitleDraft(selectedPage?.title ?? '');
  }, [selectedPage]);

  const patchPage = useCallback(async (targetPageId: string, payload: Record<string, unknown>, fallbackMessage: string) => {
    if (!token || !canEditPages) return null;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateSpaceDocPage(token, targetPageId, payload);
      setPages((current) => current.map((page) => (page.id === updated.id ? updated : page)));
      return updated;
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, fallbackMessage));
      return null;
    } finally {
      setSaving(false);
    }
  }, [canEditPages, token]);

  const handleCreateCollection = useCallback(async () => {
    if (!token || !canManageCollections) return;
    const title = await prompt({ title: 'New Document', placeholder: 'Document name', defaultValue: '' });
    if (!title) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createSpaceDoc(token, spaceId, { title });
      setCollections((current) => [created, ...current]);
      navigate(collectionPath(created.id));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '문서 컬렉션을 만들지 못했습니다.'));
    } finally {
      setSaving(false);
    }
  }, [canManageCollections, collectionPath, navigate, prompt, spaceId, token]);

  const handleRenameCollection = useCallback(async (doc: PmsSpaceDoc) => {
    if (!token || !canManageCollections) return;
    const nextTitle = await prompt({ title: 'Rename Collection', defaultValue: doc.title, placeholder: 'Collection name' });
    if (!nextTitle || nextTitle === doc.title) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateSpaceDoc(token, doc.id, { title: nextTitle });
      setCollections((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '문서 컬렉션 이름을 저장하지 못했습니다.'));
    } finally {
      setSaving(false);
    }
  }, [canManageCollections, token]);

  const handleDeleteCollection = useCallback(async (doc: PmsSpaceDoc) => {
    if (!token || !canManageCollections) return;
    if (!await confirm({ title: 'Delete Collection', description: 'Move this document collection and all its pages to Trash?', confirmLabel: 'Move to Trash', variant: 'danger' })) return;
    setSaving(true);
    setError(null);
    try {
      await deleteSpaceDoc(token, doc.id);
      setCollections((current) => current.filter((item) => item.id !== doc.id));
      if (spaceDocId === doc.id) {
        setPages([]);
        navigate(basePath, { replace: true });
      }
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '문서 컬렉션을 휴지통으로 옮기지 못했습니다.'));
    } finally {
      setSaving(false);
    }
  }, [basePath, canManageCollections, navigate, spaceDocId, token]);

  const handleCreatePage = useCallback(async (parentId: string | null = null) => {
    if (!token || !selectedCollection || !canEditPages) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createSpaceDocPage(token, spaceId, {
        title: parentId ? 'Untitled Subpage' : 'Untitled Page',
        parent_id: parentId,
        space_doc_id: selectedCollection.id,
      });
      setPages((current) => [...current, created]);
      navigate(pagePath(selectedCollection.id, created.id));
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '페이지를 생성하지 못했습니다.'));
    } finally {
      setSaving(false);
    }
  }, [canEditPages, navigate, pagePath, selectedCollection, spaceId, token]);

  const handleDeletePage = useCallback(async (targetPageId: string) => {
    if (!token || !selectedCollection || !canEditPages) return;
    if (!await confirm({ title: 'Delete Page', description: 'Move this page and its subpages to Trash?', confirmLabel: 'Move to Trash', variant: 'danger' })) return;
    setSaving(true);
    setError(null);
    try {
      await deleteSpaceDocPage(token, targetPageId);
      const response = await listSpaceDocPages(token, spaceId, selectedCollection.id);
      setPages(response.items);
      if (selectedPage?.id === targetPageId) {
        if (response.items[0]) navigate(pagePath(selectedCollection.id, response.items[0].id), { replace: true });
        else navigate(collectionPath(selectedCollection.id), { replace: true });
      }
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, '페이지를 휴지통으로 옮기지 못했습니다.'));
    } finally {
      setSaving(false);
    }
  }, [canEditPages, collectionPath, navigate, pagePath, selectedCollection, selectedPage, spaceId, token]);

  const handleTitleSave = useCallback(async () => {
    if (!canEditPages || !selectedPage || titleDraft.trim() === selectedPage.title) return;
    await patchPage(selectedPage.id, { title: titleDraft.trim() || 'Untitled Page' }, '페이지 제목을 저장하지 못했습니다.');
  }, [canEditPages, patchPage, selectedPage, titleDraft]);

  if (!spaceRoleResolved) {
    return (
      <div className="flex h-full items-center justify-center bg-app-bg">
        <Loader2 size={20} className="animate-spin text-gray-500" />
      </div>
    );
  }

  if (!canAccessSpaceDocs) {
    return <AccessDeniedView description="현재 계정에는 이 스페이스 문서에 접근할 권한이 없습니다." />;
  }

  if (!spaceDocId) {
    return (
      <div className="h-full flex flex-col bg-app-bg">
        {confirmDialog}
        {promptDialog}
        <header className="border-b border-app-border px-8 py-6">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="app-text-overline text-gray-500">Space Docs</div>
              <div className="app-text-title-lg text-app-ink">{spaceName ?? 'Space'}</div>
              <div className="app-text-body text-gray-500">문서 컬렉션 단위로 페이지를 정리하고 관리합니다.</div>
            </div>
            {canManageCollections ? (
              <button
                onClick={() => { void handleCreateCollection(); }}
                className="app-text-control flex items-center gap-2 rounded-md bg-app-accent px-4 py-2 text-app-bg"
              >
                <Plus size={16} />
                <span>New Collection</span>
              </button>
            ) : null}
          </div>
        </header>

        {error ? (
          <div className="app-text-body border-b border-red-500/20 bg-red-500/10 px-8 py-3 text-red-300">{error}</div>
        ) : null}

        <main className="custom-scrollbar flex-1 overflow-y-auto px-8 py-8">
          {loadingCollections ? (
            <div className="flex h-64 items-center justify-center">
              <Loader2 size={20} className="animate-spin text-gray-500" />
            </div>
          ) : collections.length > 0 ? (
            <div className="mx-auto max-w-4xl space-y-3">
              {collections.map((doc) => (
                <div key={doc.id} className="group flex items-center gap-3 rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-3">
                  <button
                    onClick={() => navigate(collectionPath(doc.id))}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                  >
                    <div className="flex h-10 w-10 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent">
                      <FileText size={18} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="app-text-title-md truncate text-app-ink">{doc.title}</div>
                      <div className="app-text-caption text-gray-500">
                        Updated {new Date(doc.updated_at).toLocaleString()}
                      </div>
                    </div>
                  </button>
                  {canManageCollections ? (
                    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        onClick={() => { void handleRenameCollection(doc); }}
                        className="rounded p-1.5 text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
                        title="Rename collection"
                      >
                        <MoreHorizontal size={14} />
                      </button>
                      <button
                        onClick={() => { void handleDeleteCollection(doc); }}
                        className="rounded p-1.5 text-gray-500 transition-colors hover:bg-red-500/10 hover:text-red-400"
                        title="Move to Trash"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <div className="mx-auto flex max-w-xl flex-col items-center justify-center rounded-xl border border-dashed border-app-border bg-app-surface-sidebar px-8 py-12 text-center">
              <FileText size={24} className="mb-4 text-gray-400" />
              <div className="app-text-title-md text-app-ink">No document collections yet</div>
              <div className="app-text-body mt-2 text-gray-500">첫 번째 컬렉션을 만들고 그 안에서 페이지를 관리하세요.</div>
              {canManageCollections ? (
                <button
                  onClick={() => { void handleCreateCollection(); }}
                  className="app-text-control mt-6 inline-flex items-center gap-2 rounded-md bg-app-accent px-4 py-2 text-app-bg"
                >
                  <Plus size={16} />
                  <span>Create Collection</span>
                </button>
              ) : null}
            </div>
          )}
        </main>
      </div>
    );
  }

  return (
    <div className="h-full flex bg-app-bg">
      {confirmDialog}
      {promptDialog}
      <div className="flex w-72 flex-col border-r border-app-border bg-app-surface-sidebar">
        <div className="flex items-center justify-between border-b border-app-border px-4 py-4">
          <div className="min-w-0">
            <button
              onClick={() => navigate(basePath)}
              className="app-text-overline text-gray-500 transition-colors hover:text-app-ink"
            >
              Space Docs
            </button>
            <div className="app-text-title-md truncate text-app-ink">
              {selectedCollection?.title ?? 'Collection'}
            </div>
          </div>
          {canEditPages ? (
            <button
              onClick={() => { void handleCreatePage(null); }}
              className="rounded p-1 text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
              title="Add page"
            >
              <Plus size={14} />
            </button>
          ) : null}
        </div>

        <div className="custom-scrollbar flex-1 overflow-y-auto px-2 py-3 space-y-1">
          {loadingPages ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={16} className="animate-spin text-gray-500" />
            </div>
          ) : pageTree.length > 0 ? (
            pageTree.map((node) => (
              <PageTreeItem
                key={node.id}
                node={node}
                selectedPageId={selectedPage?.id ?? null}
                onSelect={(nextPageId) => {
                  if (selectedCollection) navigate(pagePath(selectedCollection.id, nextPageId));
                }}
                onCreateChild={(parentId) => { void handleCreatePage(parentId); }}
                onDelete={(targetPageId) => { void handleDeletePage(targetPageId); }}
                canEdit={canEditPages}
              />
            ))
          ) : canEditPages ? (
            <button
              onClick={() => { void handleCreatePage(null); }}
              className="app-text-body w-full rounded-md border border-dashed border-app-border px-3 py-4 text-gray-500 transition-colors hover:border-app-accent hover:text-app-ink"
            >
              Create the first page
            </button>
          ) : (
            <div className="app-text-body rounded-md border border-dashed border-app-border px-3 py-4 text-gray-500">
              No pages in this collection
            </div>
          )}
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {error ? (
          <div className="app-text-body border-b border-red-500/20 bg-red-500/10 px-6 py-3 text-red-300">{error}</div>
        ) : null}

        {selectedPage ? (
          <>
            <div className="app-text-caption flex h-12 items-center justify-between border-b border-app-border px-6 text-gray-500">
              <div className="flex items-center gap-2">
                <FileText size={12} />
                <span>{selectedCollection?.title ?? 'Collection'}</span>
              </div>
              <div className="flex items-center gap-3">
                {saving ? <Loader2 size={12} className="animate-spin" /> : null}
                <span>{selectedPage.created_by_name}</span>
              </div>
            </div>

            <div className="custom-scrollbar flex-1 overflow-y-auto">
              <motion.div
                key={selectedPage.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="mx-auto max-w-4xl space-y-6 px-12 py-12"
              >
                <div className="space-y-3">
                  <input
                    value={titleDraft}
                    onChange={(event) => setTitleDraft(event.target.value)}
                    onBlur={() => { void handleTitleSave(); }}
                    onKeyDown={(event) => {
                      if (canEditPages && event.key === 'Enter') {
                        event.preventDefault();
                        void handleTitleSave();
                      }
                    }}
                    className={cn(
                      'app-text-title-xl w-full bg-transparent text-app-ink outline-none placeholder:text-app-ink/20',
                      !canEditPages && 'cursor-default',
                    )}
                    placeholder="Untitled Page"
                    readOnly={!canEditPages}
                  />
                  <div className="app-text-caption text-gray-500">
                    Last updated {new Date(selectedPage.updated_at).toLocaleString()}
                  </div>
                </div>

                <div className="prose max-w-none dark:prose-invert">
                  {canEditPages && selectedPage.realtime_collab && token ? (
                    <CollaborativeBlockEditor
                      sessionKey={`${workspaceSlug ?? 'current'}:${selectedPage.id}`}
                      authToken={token}
                      loadSession={async () => {
                        const session = await getDocsCollabSession(
                          token,
                          makeDocsPageRef('pms_space_doc_page', selectedPage.id),
                          workspaceSlug,
                        );
                        return {
                          roomKey: session.room_key,
                          wsPath: session.ws_path,
                          user: {
                            id: session.user.id,
                            fullName: session.user.full_name,
                          },
                          snapshotContent: (session.snapshot_content_blocks ?? []) as BlockContent,
                          yjsState: session.yjs_state,
                        };
                      }}
                      saveSnapshot={async ({ content, yjsState }) => {
                        const response = await saveDocsCollabSnapshot(
                          token,
                          makeDocsPageRef('pms_space_doc_page', selectedPage.id),
                          {
                            content_blocks: content,
                            yjs_state: yjsState,
                          },
                          workspaceSlug,
                        );
                        return { updatedAt: response.updated_at };
                      }}
                      placeholder="Start writing..."
                      uploadFile={uploadFile}
                      resolveFileUrl={resolveFileUrl}
                      onPersisted={({ content, updatedAt }) => {
                        setPages((current) => current.map((page) => (
                          page.id === selectedPage.id
                            ? {
                                ...page,
                                content_blocks: content as BlockContent,
                                updated_at: updatedAt ?? page.updated_at,
                              }
                            : page
                        )));
                      }}
                    />
                  ) : selectedPage ? (
                    <BlockViewer
                      key={selectedPage.id}
                      content={(selectedPage.content_blocks as BlockContent | null) ?? []}
                    />
                  ) : null}
                </div>
              </motion.div>
            </div>
          </>
        ) : (
          <div className="app-text-body flex flex-1 items-center justify-center text-gray-500">
            {loadingPages ? <Loader2 size={18} className="animate-spin" /> : 'Select a page'}
          </div>
        )}
      </div>
    </div>
  );
};
