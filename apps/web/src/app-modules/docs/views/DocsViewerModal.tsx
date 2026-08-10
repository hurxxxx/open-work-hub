import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  Loader2,
  X,
} from 'lucide-react';
import {
  Button,
  Dialog,
  blockContentToMarkdown,
  markdownToBlockContent,
  useConfirm,
  type BlockContent,
} from '@ai-do/ui';
import {
  REALTIME_TOPIC_EVENT_TYPES,
  createDocsPagesRealtimeSubscriptionMessage,
} from '@ai-do/contracts/realtime';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import {
  useRealtime,
  useRealtimeEvent,
  useRealtimeSubscription,
  type RealtimeEvent,
} from '@/src/platform/realtime/realtime-provider';
import {
  getDocsItem,
  listDocPages,
  mediaResourceTypeForDocsPage,
  recordDocView,
  resolveDocsContentFormat,
  resolveDocsHubContentFormat,
  updateDocPage,
  type DocsContentFormat,
  type DocsHubContentFormat,
  type DocsPagesEventPayload,
  type DocsPageItem,
} from '../api/docs-api';
import { flattenVisibleTree } from '../api/docs-page-reorder';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import { DocsBlockContentSurface } from './DocsBlockContentSurface';
import { DocsBlockMarkdownActions } from './docs-content-renderers';
import { DocsHtmlPageContentSurface } from './docs-html-renderers';
import { downloadMarkdownFile } from './docs-markdown-file';
import {
  DOCS_VIEWER_INITIAL_STATE,
  buildDocsPagesById,
  countDocsPageChildren,
  docsViewerReducer,
  isDocsTextUploadTooLarge,
} from './docs-view-model';
import { useDocsPageContentSaveController } from './useDocsPageContentSaveController';

function DocsContentFormatBadge({
  format,
  label,
}: {
  format: DocsContentFormat | DocsHubContentFormat;
  label: string;
}) {
  const Icon = format === 'html' ? FileCode2 : FileText;
  return (
    <span className="app-text-micro inline-flex shrink-0 items-center gap-1 rounded border border-app-border bg-app-bg px-1.5 py-0.5 text-app-ink/55">
      <Icon size={11} />
      <span>{label}</span>
    </span>
  );
}

export interface DocsViewerModalProps {
  open: boolean;
  itemId: string | null | undefined;
  workspaceSlug?: string | null;
  shareToken?: string | null;
  fallbackTitle?: string;
  allowEdit?: boolean;
  onOpenChange: (open: boolean) => void;
}

export interface DocsEmbeddedViewerProps {
  itemId: string | null | undefined;
  workspaceSlug?: string | null;
  shareToken?: string | null;
  fallbackTitle?: string;
  allowEdit?: boolean;
  active?: boolean;
  className?: string;
  onClose?: () => void;
}

export function DocsViewerModal({
  open,
  onOpenChange,
  ...viewerProps
}: DocsViewerModalProps) {
  const { t } = useTranslation(['apps', 'common']);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={viewerProps.fallbackTitle ?? t('apps:docs.docs')}
      closeLabel={t('common:actions.close')}
      fullSize
      embedded
      layer="elevated"
    >
      <DocsEmbeddedViewer
        {...viewerProps}
        active={open}
        onClose={() => onOpenChange(false)}
      />
    </Dialog>
  );
}

export function DocsEmbeddedViewer(props: DocsEmbeddedViewerProps) {
  return useDocsEmbeddedViewerContent(props);
}

function useDocsEmbeddedViewerContent({
  active = true,
  itemId,
  workspaceSlug,
  shareToken = null,
  fallbackTitle,
  allowEdit = true,
  className,
  onClose,
}: DocsEmbeddedViewerProps) {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const { reconnectSeq } = useRealtime();
  const { uploadFile, createLinkedUploadFile, resolveFileUrl } =
    useMediaUpload();
  const { confirm, confirmDialog } = useConfirm();
  const [viewerState, dispatchViewer] = useReducer(
    docsViewerReducer,
    DOCS_VIEWER_INITIAL_STATE,
  );
  const {
    doc,
    pages,
    selectedPageId,
    expandedNodes,
    contentEditorVersions,
    htmlEditPageIds,
    loading,
    error,
  } = viewerState;
  const docPagesRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const docPagesPendingParentIdRef = useRef<string | null>(null);
  const {
    cancelQueuedSave,
    flushTextSave: flushPendingContentTextSave,
    queueBlockSave,
    queueTextSave,
  } = useDocsPageContentSaveController({
    token,
    shareToken,
    workspaceSlug,
    flushOnUnmount: true,
    savePage: updateDocPage,
    onSavedPage: (updated) => {
      dispatchViewer({ type: 'updatePage', page: updated });
    },
  });
  useEffect(() => {
    if (!active || !itemId || !token) {
      if (!active || !itemId) {
        if (!active) {
          void flushPendingContentTextSave();
        }
        dispatchViewer({ type: 'reset' });
        cancelQueuedSave();
      }
      return;
    }

    let cancelled = false;
    dispatchViewer({ type: 'loadStart' });

    void Promise.all([
      getDocsItem(token, itemId, shareToken, workspaceSlug),
      listDocPages(token, itemId, shareToken, workspaceSlug),
    ])
      .then(([nextDoc, pageList]) => {
        if (cancelled) return;
        const nextPages = pageList.items;
        cancelQueuedSave();
        dispatchViewer({ type: 'loadSuccess', doc: nextDoc, pages: nextPages });
      })
      .catch(() => {
        if (!cancelled) {
          dispatchViewer({
            type: 'loadError',
            message: t('apps:docs.viewer.loadFailed'),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    active,
    cancelQueuedSave,
    flushPendingContentTextSave,
    itemId,
    shareToken,
    t,
    token,
    workspaceSlug,
  ]);

  const refreshPages = useCallback(
    async (expandedParentId?: string | null) => {
      if (!active || !itemId || !token) return;
      try {
        const pageList = await listDocPages(
          token,
          itemId,
          shareToken,
          workspaceSlug,
        );
        const nextPages = pageList.items;
        dispatchViewer({
          type: 'refreshPages',
          pages: nextPages,
          expandedParentId,
        });
      } catch {
        // The stream is advisory; keep the existing page tree if a refresh fails.
      }
    },
    [active, itemId, shareToken, token, workspaceSlug],
  );

  const schedulePagesRefresh = useCallback(
    (expandedParentId?: string | null) => {
      if (!active || !itemId) {
        return;
      }
      if (expandedParentId) {
        docPagesPendingParentIdRef.current = expandedParentId;
      }
      if (docPagesRefreshTimerRef.current !== null) {
        return;
      }
      docPagesRefreshTimerRef.current = setTimeout(() => {
        const parentId = docPagesPendingParentIdRef.current;
        docPagesPendingParentIdRef.current = null;
        docPagesRefreshTimerRef.current = null;
        void refreshPages(parentId);
      }, 150);
    },
    [active, itemId, refreshPages],
  );

  useRealtimeSubscription(
    active && itemId && token
      ? createDocsPagesRealtimeSubscriptionMessage({
          key: itemId,
          workspaceSlug: workspaceSlug ?? null,
          shareToken: shareToken ?? null,
        })
      : null,
  );

  useRealtimeEvent(
    REALTIME_TOPIC_EVENT_TYPES.docsPagesChanged,
    useCallback(
      (event: RealtimeEvent) => {
        const payload = event.data as DocsPagesEventPayload | undefined;
        if (
          !active ||
          !itemId ||
          (payload?.doc_id && doc?.id && payload.doc_id !== doc.id)
        ) {
          return;
        }
        schedulePagesRefresh(payload?.parent_id ?? null);
      },
      [active, doc?.id, itemId, schedulePagesRefresh],
    ),
  );

  useEffect(() => {
    if (!active || !itemId || !token) {
      return;
    }
    schedulePagesRefresh(null);
  }, [active, itemId, reconnectSeq, schedulePagesRefresh, token]);

  useEffect(
    () => () => {
      if (docPagesRefreshTimerRef.current !== null) {
        clearTimeout(docPagesRefreshTimerRef.current);
        docPagesRefreshTimerRef.current = null;
      }
      docPagesPendingParentIdRef.current = null;
    },
    [active, itemId],
  );

  const pagesById = useMemo(() => buildDocsPagesById(pages), [pages]);

  const childCounts = useMemo(() => countDocsPageChildren(pages), [pages]);

  const visibleTree = useMemo(
    () => flattenVisibleTree(pages, expandedNodes),
    [expandedNodes, pages],
  );
  const activePage =
    pages.find((page) => page.id === selectedPageId) ?? pages[0] ?? null;
  const activeContentFormat = resolveDocsContentFormat(activePage);
  const title = doc?.title?.trim() || fallbackTitle || t('apps:docs.docs');
  const canEditActivePage =
    allowEdit && Boolean(doc?.can_edit && activePage?.can_edit);
  const activePageUploadFile = useMemo(
    () =>
      createLinkedUploadFile?.(
        activePage?.source_page_id
          ? {
              resourceType: mediaResourceTypeForDocsPage(),
              resourceId: activePage.source_page_id,
            }
          : null,
      ) ?? uploadFile,
    [activePage?.source_page_id, createLinkedUploadFile, uploadFile],
  );

  useEffect(() => {
    if (!active || !token || !itemId || !activePage) return;
    void recordDocView(token, itemId, activePage.id, shareToken, workspaceSlug);
  }, [active, activePage, itemId, shareToken, token, workspaceSlug]);

  function toggleExpand(pageId: string) {
    dispatchViewer({ type: 'toggleExpanded', pageId });
  }

  function setHtmlPageEditMode(pageId: string, editing: boolean) {
    dispatchViewer({ type: 'setHtmlEditMode', pageId, editing });
  }

  const updatePageContentBlocksLocally = useCallback(
    (pageId: string, blocks: Record<string, unknown>[]) => {
      dispatchViewer({ type: 'updatePageBlocks', pageId, blocks });
    },
    [],
  );

  const handleCollabChange = useCallback(
    (pageId: string, content: Record<string, unknown>[]) => {
      updatePageContentBlocksLocally(pageId, content);
    },
    [updatePageContentBlocksLocally],
  );

  const handleEditorChange = useCallback(
    (pageId: string, blocks: Record<string, unknown>[]) => {
      const target = pagesById.get(pageId);
      if (!token || !target?.can_edit || !allowEdit || !doc?.can_edit) return;
      updatePageContentBlocksLocally(pageId, blocks);
      queueBlockSave(pageId, blocks);
    },
    [
      allowEdit,
      doc?.can_edit,
      pagesById,
      queueBlockSave,
      token,
      updatePageContentBlocksLocally,
    ],
  );

  const updatePageContentTextLocally = useCallback(
    (pageId: string, contentText: string) => {
      dispatchViewer({ type: 'updatePageText', pageId, contentText });
    },
    [],
  );

  const bumpContentEditorVersion = useCallback((pageId: string) => {
    dispatchViewer({ type: 'bumpContentEditorVersion', pageId });
  }, []);

  const handleContentTextChange = useCallback(
    (contentText: string) => {
      if (!token || !activePage?.id || !canEditActivePage) return;
      updatePageContentTextLocally(activePage.id, contentText);
      queueTextSave(activePage.id, contentText);
    },
    [
      activePage?.id,
      canEditActivePage,
      queueTextSave,
      token,
      updatePageContentTextLocally,
    ],
  );

  const handleContentTextFileUpload = useCallback(
    async (page: DocsPageItem, file: File | null) => {
      if (!token || !canEditActivePage || !file) return;
      if (isDocsTextUploadTooLarge(file.size)) {
        window.alert(t('apps:docs.uploadTooLarge'));
        return;
      }
      const text = await file.text();
      cancelQueuedSave();
      updatePageContentTextLocally(page.id, text);
      bumpContentEditorVersion(page.id);
      try {
        const updated = await updateDocPage(
          token,
          page.id,
          { content_text: text },
          shareToken,
          workspaceSlug,
        );
        dispatchViewer({ type: 'updatePage', page: updated });
      } catch {
        // Keep local editor state; the next change will retry saving.
      }
    },
    [
      bumpContentEditorVersion,
      canEditActivePage,
      cancelQueuedSave,
      shareToken,
      t,
      token,
      updatePageContentTextLocally,
      workspaceSlug,
    ],
  );

  const handleBlockMarkdownExport = useCallback((page: DocsPageItem) => {
    const markdown = blockContentToMarkdown(
      (page.content_blocks ?? []) as BlockContent,
    ).trimEnd();
    downloadMarkdownFile(page.title, markdown ? `${markdown}\n` : '');
  }, []);

  const handleBlockMarkdownImportFile = useCallback(
    async (page: DocsPageItem, file: File | null) => {
      if (!token || !canEditActivePage || !file) return;
      if (isDocsTextUploadTooLarge(file.size)) {
        window.alert(t('apps:docs.uploadTooLarge'));
        return;
      }
      const ok = await confirm({
        title: t('apps:docs.blockMarkdown.importConfirmTitle'),
        description: t('apps:docs.blockMarkdown.importConfirmDescription'),
        confirmLabel: t('apps:docs.blockMarkdown.import'),
        cancelLabel: t('common:actions.cancel'),
      });
      if (!ok) return;
      try {
        const markdown = await file.text();
        const blocks = markdownToBlockContent(markdown) as unknown as Record<
          string,
          unknown
        >[];
        cancelQueuedSave();
        const updated = await updateDocPage(
          token,
          page.id,
          { content_blocks: blocks },
          shareToken,
          workspaceSlug,
        );
        dispatchViewer({ type: 'updatePage', page: updated });
        bumpContentEditorVersion(page.id);
      } catch {
        window.alert(t('apps:docs.blockMarkdown.importFailed'));
      }
    },
    [
      bumpContentEditorVersion,
      canEditActivePage,
      cancelQueuedSave,
      confirm,
      shareToken,
      t,
      token,
      workspaceSlug,
    ],
  );

  async function handleOpenHtmlPage(page: DocsPageItem) {
    if (!doc) return;
    if (shareToken) {
      await flushPendingContentTextSave();
      window.open(
        `/docs/shared/${shareToken}/html/${page.id}`,
        '_blank',
        'noopener,noreferrer',
      );
      return;
    }
    if (!workspaceSlug) return;
    await flushPendingContentTextSave();
    window.open(
      buildWorkspaceAppPath(
        workspaceSlug,
        'docs',
        `/${doc.id}/html/${page.id}`,
      ),
      '_blank',
      'noopener,noreferrer',
    );
  }

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
      dispatchViewer({ type: 'updatePage', page: updated });
    } catch {
      // no-op
    }
  }

  function handleClose() {
    void flushPendingContentTextSave();
    onClose?.();
  }

  return (
    <>
      {confirmDialog}
      <div className={cn('flex min-h-0 flex-1 flex-col bg-app-bg', className)}>
        <header className="flex min-h-12 items-center justify-between gap-3 border-b border-app-border bg-app-surface-sidebar px-4">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="app-text-title-sm truncate text-app-ink">{title}</h2>
            {doc ? (
              <DocsContentFormatBadge
                format={resolveDocsHubContentFormat(doc)}
                label={t(
                  `apps:docs.contentFormat.${resolveDocsHubContentFormat(doc)}`,
                )}
              />
            ) : null}
          </div>
          {onClose ? (
            <Button
              variant="ghost"
              size="icon"
              onClick={handleClose}
              aria-label={t('common:actions.close')}
            >
              <X size={16} />
            </Button>
          ) : null}
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
                <h3 className="app-text-title-sm truncate text-app-ink">
                  {title}
                </h3>
                <div className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="app-text-overline text-app-ink/55">
                      {t('apps:docs.pages')}
                    </span>
                    {doc ? (
                      <DocsContentFormatBadge
                        format={resolveDocsHubContentFormat(doc)}
                        label={t(
                          `apps:docs.contentFormat.${resolveDocsHubContentFormat(doc)}`,
                        )}
                      />
                    ) : null}
                  </span>
                  <span className="app-text-caption text-app-ink/55">
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
                  const PageIcon =
                    resolveDocsContentFormat(page) === 'html'
                      ? FileCode2
                      : FileText;
                  return (
                    <div
                      key={page.id}
                      className={cn(
                        'app-text-body-sm group flex w-full items-center gap-1 rounded px-2 py-1.5 transition-colors',
                        selected
                          ? 'bg-app-accent/10 text-app-accent'
                          : 'text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink',
                      )}
                      style={{ paddingLeft: `${8 + node.depth * 16}px` }}
                    >
                      {hasChildren ? (
                        <button
                          type="button"
                          className="flex-shrink-0"
                          aria-label={
                            expanded
                              ? t('common:actions.close')
                              : t('common:actions.open')
                          }
                          onClick={(event) => {
                            event.stopPropagation();
                            toggleExpand(page.id);
                          }}
                        >
                          {expanded ? (
                            <ChevronDown size={12} />
                          ) : (
                            <ChevronRight size={12} />
                          )}
                        </button>
                      ) : (
                        <span className="w-3" />
                      )}
                      <button
                        type="button"
                        onClick={() =>
                          dispatchViewer({
                            type: 'selectPage',
                            pageId: page.id,
                          })
                        }
                        className="flex min-w-0 flex-1 items-center gap-1 text-left"
                      >
                        <PageIcon size={14} className="shrink-0" />
                        <span className="min-w-0 flex-1 truncate text-left">
                          {page.title}
                        </span>
                      </button>
                    </div>
                  );
                })}
              </div>
            </aside>

            <main className="docs-print-area custom-scrollbar min-h-0 overflow-y-auto bg-white dark:bg-app-surface">
              <div
                data-testid="docs-viewer-content-canvas"
                className="w-full px-8 py-12 2xl:px-12 max-[760px]:px-5 max-[760px]:py-6"
              >
                <div className="space-y-6">
                  {canEditActivePage ? (
                    <input
                      key={activePage.id}
                      type="text"
                      aria-label={activePage.title || t('apps:docs.untitled')}
                      defaultValue={activePage.title}
                      placeholder={t('apps:docs.untitled')}
                      className="app-text-title-xl w-full bg-transparent text-app-ink placeholder:text-app-ink/45 focus:outline-none"
                      onBlur={(event) =>
                        void handlePageTitleSave(
                          activePage.id,
                          event.target.value,
                        )
                      }
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
                    <h1 className="app-text-title-xl text-app-ink">
                      {activePage.title}
                    </h1>
                  )}
                  <div className="prose dark:prose-invert max-w-none pt-4">
                    {activeContentFormat === 'html' ? (
                      <DocsHtmlPageContentSurface
                        canEdit={canEditActivePage}
                        content={activePage.content_text}
                        editing={htmlEditPageIds.has(activePage.id)}
                        labels={{
                          editSource: t('apps:docs.html.editSource'),
                          empty: t('apps:docs.html.empty'),
                          openRendered: t('apps:docs.html.openRendered'),
                          pastePlaceholder: t(
                            'apps:docs.html.pastePlaceholder',
                          ),
                          preview: t('apps:docs.html.preview'),
                          sourceLabel: t('apps:docs.html.sourceLabel'),
                          uploadLabel: t('apps:docs.html.uploadLabel'),
                          uploadPlaceholder: t(
                            'apps:docs.html.uploadPlaceholder',
                          ),
                        }}
                        onChange={handleContentTextChange}
                        onEdit={() => setHtmlPageEditMode(activePage.id, true)}
                        onOpen={() => void handleOpenHtmlPage(activePage)}
                        onPreview={() =>
                          setHtmlPageEditMode(activePage.id, false)
                        }
                        onUploadFile={(file) =>
                          void handleContentTextFileUpload(activePage, file)
                        }
                        title={activePage.title}
                      />
                    ) : (
                      <>
                        <DocsBlockMarkdownActions
                          canImport={canEditActivePage}
                          exportLabel={t('apps:docs.blockMarkdown.export')}
                          importLabel={t('apps:docs.blockMarkdown.import')}
                          onExport={() => handleBlockMarkdownExport(activePage)}
                          onImportFile={(file) =>
                            void handleBlockMarkdownImportFile(activePage, file)
                          }
                        />
                        <DocsBlockContentSurface
                          page={activePage}
                          canEdit={canEditActivePage}
                          token={token}
                          workspaceSlug={workspaceSlug}
                          shareToken={shareToken}
                          contentEditorVersion={
                            contentEditorVersions[activePage.id] ?? 0
                          }
                          uploadFile={activePageUploadFile}
                          resolveFileUrl={resolveFileUrl}
                          onStandaloneBlocksChange={handleEditorChange}
                          onCollaborativeBlocksChange={handleCollabChange}
                        />
                      </>
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
    </>
  );
}
