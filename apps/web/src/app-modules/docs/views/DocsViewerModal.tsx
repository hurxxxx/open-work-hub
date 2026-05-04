import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  X,
} from 'lucide-react';
import {
  BlockEditor,
  BlockViewer,
  Button,
  CollaborativeBlockEditor,
  Dialog,
  type BlockContent,
} from '@aidoo/ui';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import {
  getDocsItem,
  getDocsCollabSession,
  listDocPages,
  makeDocsPageRef,
  mediaResourceTypeForDocsPage,
  recordDocView,
  updateDocPage,
  type DocsHubItem,
  type DocsPageItem,
} from '../api/docs-api';
import { flattenVisibleTree } from '../api/docs-page-reorder';

export interface DocsViewerModalProps {
  open: boolean;
  itemId: string | null | undefined;
  workspaceSlug?: string | null;
  shareToken?: string | null;
  fallbackTitle?: string;
  allowEdit?: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DocsViewerModal({
  open,
  itemId,
  workspaceSlug,
  shareToken = null,
  fallbackTitle,
  allowEdit = true,
  onOpenChange,
}: DocsViewerModalProps) {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const { uploadFile, createLinkedUploadFile, resolveFileUrl } = useMediaUpload();
  const [doc, setDoc] = useState<DocsHubItem | null>(null);
  const [pages, setPages] = useState<DocsPageItem[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!open || !itemId || !token) {
      if (!open) {
        setDoc(null);
        setPages([]);
        setSelectedPageId(null);
        setExpandedNodes(new Set());
        setError(null);
        setLoading(false);
      }
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    void Promise.all([
      getDocsItem(token, itemId, shareToken, workspaceSlug),
      listDocPages(token, itemId, shareToken, workspaceSlug),
    ])
      .then(([nextDoc, pageList]) => {
        if (cancelled) return;
        const nextPages = pageList.items;
        const parentIds = new Set(
          nextPages
            .map((page) => page.parent_id)
            .filter((parentId): parentId is string => Boolean(parentId)),
        );
        setDoc(nextDoc);
        setPages(nextPages);
        setExpandedNodes(parentIds);
        setSelectedPageId((current) => (
          nextPages.some((page) => page.id === current)
            ? current
            : nextPages[0]?.id ?? null
        ));
      })
      .catch(() => {
        if (!cancelled) setError(t('apps:docs.viewer.loadFailed'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [itemId, open, shareToken, t, token, workspaceSlug]);

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

  const visibleTree = useMemo(
    () => flattenVisibleTree(pages, expandedNodes),
    [expandedNodes, pages],
  );
  const activePage = pages.find((page) => page.id === selectedPageId) ?? pages[0] ?? null;
  const title = doc?.title?.trim() || fallbackTitle || t('apps:docs.docs');
  const canEditActivePage = allowEdit && Boolean(doc?.can_edit && activePage?.can_edit);
  const activePageUploadFile = useMemo(
    () => createLinkedUploadFile?.(
      activePage?.source_page_id
        ? {
            resourceType: mediaResourceTypeForDocsPage(activePage.source_type),
            resourceId: activePage.source_page_id,
          }
        : null,
    ) ?? uploadFile,
    [activePage?.source_page_id, activePage?.source_type, createLinkedUploadFile, uploadFile],
  );

  useEffect(() => {
    if (!open || !token || !itemId || !activePage) return;
    void recordDocView(token, itemId, activePage.id, shareToken, workspaceSlug);
  }, [activePage, itemId, open, shareToken, token, workspaceSlug]);

  function toggleExpand(pageId: string) {
    setExpandedNodes((current) => {
      const next = new Set(current);
      if (next.has(pageId)) next.delete(pageId);
      else next.add(pageId);
      return next;
    });
  }

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

  const handleEditorChange = useCallback((blocks: Record<string, unknown>[]) => {
    if (!token || !activePage?.id || !canEditActivePage) return;
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }
    const pageId = activePage.id;
    saveTimerRef.current = setTimeout(async () => {
      try {
        const updated = await updateDocPage(
          token,
          pageId,
          { content_blocks: blocks },
          shareToken,
          workspaceSlug,
        );
        setPages((current) => current.map((page) => (page.id === updated.id ? updated : page)));
      } catch {
        // Keep local editor state; the next change will retry saving.
      }
    }, 800);
  }, [activePage?.id, canEditActivePage, shareToken, token, workspaceSlug]);

  async function handlePageTitleSave(pageId: string, nextTitle: string) {
    if (!token || !canEditActivePage) return;
    const trimmed = nextTitle.trim();
    if (!trimmed) return;
    const target = pages.find((page) => page.id === pageId);
    if (!target || target.title === trimmed) return;
    try {
      const updated = await updateDocPage(
        token,
        pageId,
        { title: trimmed },
        shareToken,
        workspaceSlug,
      );
      setPages((current) => current.map((page) => (page.id === updated.id ? updated : page)));
    } catch {
      // no-op
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      closeLabel={t('common:actions.close')}
      fullSize
      embedded
    >
      <div className="flex min-h-0 flex-1 flex-col bg-app-bg">
        <header className="flex min-h-12 items-center justify-between gap-3 border-b border-app-border bg-app-surface-sidebar px-4">
          <div className="min-w-0">
            <h2 className="app-text-title-sm truncate text-app-ink">{title}</h2>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onOpenChange(false)}
            aria-label={t('common:actions.close')}
          >
            <X size={16} />
          </Button>
        </header>

        {loading ? (
          <div className="flex min-h-0 flex-1 items-center justify-center text-app-ink/50">
            <Loader2 size={24} className="animate-spin" />
          </div>
        ) : error ? (
          <div className="flex min-h-0 flex-1 items-center justify-center px-5">
            <div className="flex max-w-md items-start gap-2 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/5 px-3 py-2 text-sm text-[var(--ui-color-danger)]">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          </div>
        ) : activePage ? (
          <div className="grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)] max-[760px]:grid-cols-1">
            <aside className="flex min-h-0 flex-col overflow-hidden border-r border-app-border bg-app-surface-sidebar px-3 py-4 max-[760px]:max-h-44 max-[760px]:border-b max-[760px]:border-r-0">
              <div className="mb-4 space-y-1 px-1">
                <h3 className="app-text-title-sm truncate text-app-ink">{title}</h3>
                <div className="flex items-center justify-between gap-2">
                  <span className="app-text-overline text-gray-500">{t('apps:docs.pages')}</span>
                  <span className="app-text-caption text-gray-500">
                    {t('apps:docs.pageCount', { count: pages.length })}
                  </span>
                </div>
              </div>
              <div className="ui-scrollbar min-h-0 flex-1 space-y-1 overflow-y-auto">
                {visibleTree.map((node) => {
                  const page = pagesById.get(node.id);
                  if (!page) return null;
                  const hasChildren = (childCounts.get(page.id) ?? 0) > 0;
                  const expanded = expandedNodes.has(page.id);
                  const selected = page.id === activePage.id;
                  return (
                    <button
                      key={page.id}
                      type="button"
                      onClick={() => setSelectedPageId(page.id)}
                      className={cn(
                        'app-text-body-sm group flex w-full items-center gap-1 rounded px-2 py-1.5 transition-colors',
                        selected
                          ? 'bg-app-accent/10 text-app-accent'
                          : 'text-gray-400 hover:bg-app-surface-hover hover:text-gray-200',
                      )}
                      style={{ paddingLeft: `${8 + node.depth * 16}px` }}
                    >
                      {hasChildren ? (
                        <span
                          className="flex-shrink-0"
                          onClick={(event) => {
                            event.stopPropagation();
                            toggleExpand(page.id);
                          }}
                        >
                          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        </span>
                      ) : (
                        <span className="w-3" />
                      )}
                      <FileText size={14} className="shrink-0" />
                      <span className="min-w-0 flex-1 truncate text-left">{page.title}</span>
                    </button>
                  );
                })}
              </div>
            </aside>

            <main className="docs-print-area custom-scrollbar min-h-0 overflow-y-auto bg-white dark:bg-[#1e1e24]">
              <div className="mx-auto w-full max-w-4xl px-12 py-12 max-[760px]:px-5 max-[760px]:py-6">
                <div className="space-y-6">
                  {canEditActivePage ? (
                    <input
                      key={activePage.id}
                      type="text"
                      defaultValue={activePage.title}
                      placeholder={t('apps:docs.untitled')}
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
                  <div className="prose dark:prose-invert max-w-none pt-4">
                    {canEditActivePage && activePage.realtime_collab && !shareToken && token ? (
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
                        messages={{
                          permissionRevoked: t('apps:docs.collab.permissionRevoked'),
                          relayUnavailable: t('apps:docs.collab.relayUnavailable'),
                          startFailed: t('apps:docs.collab.startFailed'),
                          preparing: t('apps:docs.collab.preparing'),
                        }}
                        placeholder={t('apps:docs.startWriting')}
                        uploadFile={activePageUploadFile}
                        resolveFileUrl={resolveFileUrl}
                        onChange={(content) => {
                          handleCollabChange(
                            activePage.id,
                            content as Record<string, unknown>[],
                          );
                        }}
                      />
                    ) : canEditActivePage ? (
                      <BlockEditor
                        key={activePage.id}
                        initialContent={(activePage.content_blocks ?? []) as BlockContent}
                        placeholder={t('apps:docs.startWriting')}
                        uploadFile={activePageUploadFile}
                        resolveFileUrl={resolveFileUrl}
                        onChange={handleEditorChange}
                      />
                    ) : (
                      <BlockViewer
                        key={activePage.id}
                        content={(activePage.content_blocks ?? []) as BlockContent}
                        resolveFileUrl={resolveFileUrl}
                      />
                    )}
                  </div>
                </div>
              </div>
            </main>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 text-center text-app-ink/50">
            <FileText size={34} />
            <p className="app-text-body">{t('apps:docs.noPages')}</p>
          </div>
        )}
      </div>
    </Dialog>
  );
}
