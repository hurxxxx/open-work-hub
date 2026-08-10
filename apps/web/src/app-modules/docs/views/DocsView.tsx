import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Copy,
  ExternalLink,
  FileCode2,
  FileText,
  Filter,
  Globe,
  Link2,
  Loader2,
  Lock,
  Maximize2,
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
import {
  DropdownMenu,
  blockContentToMarkdown,
  markdownToBlockContent,
  type BlockContent,
  useConfirm,
  usePrompt,
} from '@open-alm/ui';
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
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import {
  REALTIME_TOPIC_EVENT_TYPES,
  createDocsPagesRealtimeSubscriptionMessage,
} from '@open-alm/contracts/realtime';

import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasWorkspaceMembership } from '@/src/platform/auth/auth-api';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import { cn } from '@/src/lib/utils';
import {
  useRealtime,
  useRealtimeEvent,
  useRealtimeSubscription,
  type RealtimeEvent,
} from '@/src/platform/realtime/realtime-provider';
import {
  createDocPage,
  createNativeDoc,
  attachDocPmsTask,
  deleteDocPage,
  deleteDocsItem,
  deleteDocLinkShare,
  deleteDocUserShare,
  deleteDocTarget,
  detachDocPmsTask,
  duplicateDocsItem,
  getDocsItem,
  getDocSharing,
  listDocPages,
  listDocPmsTasks,
  mediaResourceTypeForDocsPage,
  listShareableUsers,
  recordDocView,
  resolveDocsContentFormat,
  resolveDocsHubContentFormat,
  resolveSharedLink,
  toggleDocFavorite,
  updateDocTarget,
  updateDocPage,
  updateDocsItem,
  upsertDocLinkShare,
  upsertDocUserShare,
  type DocsHubItem,
  type DocsPagesEventPayload,
  type DocsPageItem,
  type NativeDocSharingResponse,
  type RelatedPmsTaskItem,
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
  appendDocPageQuery,
  consumeDocsCreateSearchParam,
  getDocPageIdFromSearchParams,
  getDocsFilterQueryString,
  getExpandedDocPageNodeIds,
  removeLegacyDocsSearchParams,
  resetDocsFilterSearchParams,
  DOCS_SPACE_QUERY_PARAM,
  withDocPageSearchParam,
  withDocsSpaceFilterSearchParam,
} from '../api/docs-url-state';
import { DocsBlockContentSurface } from './DocsBlockContentSurface';
import { DocsBlockMarkdownActions } from './docs-content-renderers';
import { DocsFullscreenReadModal } from './DocsFullscreenReadModal';
import { DocsHtmlPageContentSurface } from './docs-html-renderers';
import { downloadMarkdownFile } from './docs-markdown-file';
import {
  CATEGORY_LABEL_KEYS,
  CATEGORY_MAP,
  DOC_CONTENT_FORMAT_OPTIONS,
  DocsContentFormatBadge,
  DocsPageTreeNode,
  LocationPicker,
  VIEW_LABEL_KEYS,
  applyUpdatedDocsPage,
  buildDocsPagesById,
  bumpDocsContentEditorVersion,
  countDocsPageChildren,
  docsAuthorInitials,
  isDocsTextUploadTooLarge,
  isDocsViewCategory,
  removeDocsPageSubtree,
  resolveDefaultDocsCreateLocation,
  resolveDocsCreateLocationValue,
  resolveDocsCreatePrimaryTarget,
  resolveDocsPageAuthorName,
  resolveDocsPageSelection,
  resolveDocsRefreshSelection,
  sharingLabel,
  summarizeDocsPageCollection,
  timeAgo,
  updateDocsPageContentBlocks,
  updateDocsPageContentText,
  type DocsViewCategory,
  type LocationOption,
} from './DocsViewParts';
import { useDocsPageContentSaveController } from './useDocsPageContentSaveController';
import { useDocsHubController } from './useDocsHubController';
import { useDocsViewState } from './useDocsViewState';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import {
  listSpaces,
  TaskPickerModal,
  type PmsTask,
} from '@/src/app-modules/pms/public-api';

type DocsVisibleTreeNode = ReturnType<typeof flattenVisibleTree>[number];
type NativeDocShareUser = NativeDocSharingResponse['users'][number];

const useCloseOnOutsidePointer = (
  ref: React.RefObject<HTMLElement | null>,
  enabled: boolean,
  onClose: () => void,
) => {
  useEffect(() => {
    if (!enabled) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [enabled, onClose, ref]);
};

function handleBlockMarkdownExport(page: DocsPageItem) {
  const markdown = blockContentToMarkdown(
    (page.content_blocks ?? []) as BlockContent,
  ).trimEnd();
  downloadMarkdownFile(page.title, markdown ? `${markdown}\n` : '');
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const renderDocsEditor = (props: any) => {
  const {
    activeContentFormat,
    activeDragId,
    activePage,
    activePageAuthorInitials,
    activePageAuthorName,
    activePageUploadFile,
    childCounts,
    contentEditorVersions,
    copiedDocId,
    dndSensors,
    docMenuOpen,
    docMenuRef,
    dropIndicator,
    editorLoading,
    expandedNodes,
    handleAddPage,
    handleBack,
    handleBlockMarkdownExport,
    handleBlockMarkdownImportFile,
    handleCollabChange,
    handleContentTextChange,
    handleContentTextFileUpload,
    handleCopyLink,
    handleDeleteDoc,
    handleDeletePage,
    handleDetachPmsTask,
    handleDragEnd,
    handleDragOver,
    handleDragPointerMove,
    handleDragStart,
    handleDuplicateDoc,
    handleEditorChange,
    handleOpenHtmlPage,
    handleOpenInNewTab,
    handlePageTitleSave,
    handlePrintDoc,
    handleRenameDoc,
    handleToggleFavorite,
    htmlEditPageIds,
    locale,
    openShareModal,
    pages,
    pagesById,
    relatedPmsTaskBusyId,
    relatedPmsTaskError,
    relatedPmsTasks,
    resetDragState,
    resolveFileUrl,
    selectDocPage,
    selectedDoc,
    selectedPageId,
    setDocMenuOpen,
    setHtmlPageEditMode,
    setReadModeOpen,
    setTaskPickerOpen,
    shareToken,
    t,
    timeZone,
    toggleExpand,
    token,
    visibleTree,
    workspaceSlug,
  } = props;
  if (editorLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-app-bg">
        <Loader2 size={28} className="animate-spin text-app-accent" />
      </div>
    );
  }

  if (!selectedDoc) {
    return (
      <div className="flex-1 flex items-center justify-center bg-app-bg text-app-ink/55">
        <div className="text-center">
          <FileText size={48} className="mx-auto mb-4 opacity-20" />
          <h2 className="app-text-title-md text-app-ink">
            {t('apps:docs.documentNotFound')}
          </h2>
          <button
            type="button"
            onClick={handleBack}
            className="app-text-control mt-4 text-app-accent hover:underline"
          >
            {t('apps:docs.goBack')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-app-bg overflow-hidden">
      <div className="h-12 border-b border-app-border flex items-center justify-between px-4 bg-app-surface-sidebar">
        <div className="app-text-caption flex items-center gap-2 min-w-0">
          <button
            type="button"
            className="text-app-ink/55 hover:text-app-ink"
            onClick={handleBack}
          >
            {t('apps:docs.docs')}
          </button>
          <span className="text-app-ink/70">/</span>
          <span className="truncate text-app-ink">{selectedDoc.title}</span>
          <DocsContentFormatBadge
            format={resolveDocsHubContentFormat(selectedDoc)}
            label={t(
              `apps:docs.contentFormat.${resolveDocsHubContentFormat(selectedDoc)}`,
            )}
            compact
          />
          <Star
            size={12}
            className={cn(
              'text-app-ink/70 cursor-pointer',
              selectedDoc.is_favorite && 'text-yellow-500 fill-yellow-500',
            )}
            onClick={(event) => void handleToggleFavorite(event, selectedDoc)}
          />
        </div>

        <div className="flex items-center gap-2">
          {selectedDoc.can_share ? (
            <button
              type="button"
              onClick={() => void openShareModal()}
              className="app-text-control-sm flex items-center gap-1.5 rounded-md px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover"
            >
              <Share2 size={14} />
              <span>{t('common:actions.share')}</span>
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setReadModeOpen(true)}
            disabled={!activePage}
            className="app-text-control-sm flex items-center gap-1.5 rounded-md px-3 py-1.5 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Maximize2 size={14} />
            <span>{t('apps:docs.readMode.open')}</span>
          </button>
          <button
            type="button"
            className="app-text-control-sm flex items-center gap-1.5 rounded-md px-3 py-1.5 text-app-accent transition-colors hover:bg-app-accent/10"
          >
            <Sparkles size={14} />
            <span>{t('apps:docs.askAi')}</span>
          </button>
          <div ref={docMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setDocMenuOpen((o: boolean) => !o)}
              className="rounded p-1.5 text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
              title={t('apps:docs.moreActions')}
            >
              <MoreHorizontal size={18} />
            </button>
            {docMenuOpen ? (
              <div className="absolute right-0 top-full mt-1 z-30 w-52 rounded-lg border border-app-border bg-app-surface-sidebar py-1 shadow-xl">
                <button
                  type="button"
                  onClick={() => void handleCopyLink(selectedDoc)}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                >
                  <Link2 size={14} />
                  <span>
                    {copiedDocId === selectedDoc.id
                      ? t('apps:docs.copied')
                      : t('apps:docs.copyLink')}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => handleOpenInNewTab(selectedDoc)}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                >
                  <ExternalLink size={14} />
                  <span>{t('apps:docs.openInNewTab')}</span>
                </button>
                <button
                  type="button"
                  onClick={() => void handleDuplicateDoc(selectedDoc)}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                >
                  <Copy size={14} />
                  <span>{t('apps:docs.duplicate')}</span>
                </button>
                <button
                  type="button"
                  onClick={handlePrintDoc}
                  className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                >
                  <Printer size={14} />
                  <span>{t('apps:docs.print')}</span>
                </button>
                {selectedDoc.can_manage ? (
                  <>
                    <div className="my-1 h-px bg-app-border" />
                    <button
                      type="button"
                      onClick={() => {
                        setDocMenuOpen(false);
                        void handleRenameDoc(selectedDoc);
                      }}
                      className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                    >
                      <Pencil size={14} />
                      <span>{t('common:actions.rename')}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setDocMenuOpen(false);
                        void handleDeleteDoc(selectedDoc);
                      }}
                      className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-danger-text hover:bg-app-surface-hover"
                    >
                      <Trash2 size={14} />
                      <span>{t('common:actions.delete')}</span>
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
          <button
            type="button"
            onClick={handleBack}
            className="p-1.5 rounded text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-danger"
          >
            <X size={20} />
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="w-64 border-r border-app-border bg-app-surface-sidebar flex flex-col overflow-hidden">
          <div className="p-4 space-y-4">
            <div className="space-y-1">
              <h2 className="app-text-title-sm text-app-ink truncate">
                {selectedDoc.title}
              </h2>
              <div className="flex flex-wrap items-center gap-2">
                <DocsContentFormatBadge
                  format={resolveDocsHubContentFormat(selectedDoc)}
                  label={t(
                    `apps:docs.contentFormat.${resolveDocsHubContentFormat(selectedDoc)}`,
                  )}
                  compact
                />
                <p className="app-text-caption min-w-0 truncate text-app-ink/55">
                  {selectedDoc.location_label}
                </p>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between px-2 mb-2">
                <span className="app-text-overline text-app-ink/55">
                  {t('apps:docs.pages')}
                </span>
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
                  items={visibleTree.map(
                    (node: DocsVisibleTreeNode) => node.id,
                  )}
                  strategy={verticalListSortingStrategy}
                >
                  <div
                    className="space-y-0.5 overflow-y-auto custom-scrollbar max-h-[calc(100vh-250px)]"
                    onPointerMove={handleDragPointerMove}
                  >
                    {visibleTree.map((node: DocsVisibleTreeNode) => {
                      const page = pagesById.get(node.id);
                      if (!page) return null;
                      const zone =
                        dropIndicator && dropIndicator.overId === node.id
                          ? dropIndicator.zone
                          : null;
                      return (
                        <DocsPageTreeNode
                          key={node.id}
                          page={page}
                          contentFormat={resolveDocsContentFormat(page)}
                          depth={node.depth}
                          hasChildren={(childCounts.get(node.id) ?? 0) > 0}
                          isExpanded={expandedNodes.has(node.id)}
                          isSelected={selectedPageId === node.id}
                          dropZone={zone}
                          canDrag={Boolean(
                            selectedDoc.can_edit && page.can_edit,
                          )}
                          canDelete={Boolean(
                            page.can_edit &&
                              (resolveDocsContentFormat(page) !== 'html' ||
                                pages.length > 1),
                          )}
                          onSelect={selectDocPage}
                          onToggleExpand={toggleExpand}
                          onDelete={handleDeletePage}
                        />
                      );
                    })}
                    {selectedDoc.can_edit ? (
                      <button
                        type="button"
                        onClick={() => void handleAddPage(null)}
                        className="app-text-body-sm flex w-full items-center gap-2 rounded px-3 py-1.5 text-app-ink/55 transition-all hover:bg-app-surface-hover hover:text-app-accent"
                      >
                        <Plus size={14} />
                        <span>{t('apps:docs.addPage')}</span>
                      </button>
                    ) : null}
                  </div>
                </SortableContext>
                <DragOverlay dropAnimation={null}>
                  {activeDragId ? (
                    <div className="app-text-body-sm flex items-center gap-1 rounded bg-app-surface-sidebar px-2 py-1.5 text-app-ink shadow-lg ring-1 ring-app-accent/40">
                      <FileText size={14} className="text-app-accent" />
                      <span className="truncate">
                        {pagesById.get(activeDragId)?.title ?? ''}
                      </span>
                    </div>
                  ) : null}
                </DragOverlay>
              </DndContext>
            </div>
          </div>

          <div className="border-t border-app-border px-4 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="app-text-overline text-app-ink/55">
                {t('docs.relatedPms.title')}
              </span>
              {selectedDoc.can_edit && workspaceSlug ? (
                <button
                  type="button"
                  onClick={() => setTaskPickerOpen(true)}
                  className="rounded p-1 text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-accent"
                  title={t('docs.relatedPms.add')}
                  aria-label={t('docs.relatedPms.add')}
                >
                  <Plus size={14} />
                </button>
              ) : null}
            </div>
            {relatedPmsTaskError ? (
              <div className="app-text-micro mb-2 rounded border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-2 py-1 text-[var(--ui-color-danger)]">
                {relatedPmsTaskError}
              </div>
            ) : null}
            {relatedPmsTasks.length === 0 ? (
              <div className="app-text-caption px-2 py-1 text-app-ink/55">
                {t('docs.relatedPms.empty')}
              </div>
            ) : (
              <div className="space-y-1">
                {relatedPmsTasks.map((task: RelatedPmsTaskItem) => (
                  <div
                    key={task.id}
                    className="group flex items-center gap-2 rounded px-2 py-1.5 text-left transition-colors hover:bg-app-surface-hover"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="app-text-body-sm truncate text-app-ink">
                        {task.task_title}
                      </div>
                      <div className="app-text-caption truncate text-app-ink/55">
                        {task.task_reference} · {task.task_status_label}
                      </div>
                    </div>
                    {selectedDoc.can_edit ? (
                      <button
                        type="button"
                        onClick={() => void handleDetachPmsTask(task.task_id)}
                        disabled={relatedPmsTaskBusyId === task.task_id}
                        className="rounded p-1 text-app-ink/55 opacity-0 transition-all hover:bg-app-surface-hover hover:text-app-danger-text disabled:opacity-40 group-hover:opacity-100"
                        title={t('docs.relatedPms.remove')}
                        aria-label={t('docs.relatedPms.remove')}
                      >
                        {relatedPmsTaskBusyId === task.task_id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <X size={12} />
                        )}
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-auto p-4 border-t border-app-border">
            <div className="app-text-body-sm flex items-center gap-2 rounded px-3 py-1.5 text-app-ink/55">
              {selectedDoc.source_type === 'native_doc' ? (
                <Lock size={14} />
              ) : (
                <Globe size={14} />
              )}
              <span>{sharingLabel(selectedDoc, t)}</span>
            </div>
          </div>
        </div>

        <div className="docs-print-area flex-1 flex flex-col min-w-0 bg-white dark:bg-app-surface overflow-y-auto custom-scrollbar">
          <div
            data-testid="docs-content-canvas"
            className="w-full px-8 py-12 2xl:px-12 max-[760px]:px-5 max-[760px]:py-6"
          >
            {activePage ? (
              <div className="space-y-6">
                <div className="space-y-4">
                  {selectedDoc.can_edit && activePage.can_edit ? (
                    <input
                      key={activePage.id}
                      type="text"
                      aria-label={t('planner.title')}
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
                  <div className="app-text-caption flex items-center gap-3 text-app-ink/55">
                    <div className="flex items-center gap-1.5">
                      <div className="app-text-micro flex size-5 items-center justify-center rounded-full bg-app-accent font-bold text-app-accent-fg">
                        {activePageAuthorInitials}
                      </div>
                      <span className="app-text-control text-app-ink">
                        {activePageAuthorName}
                      </span>
                    </div>
                    <span>·</span>
                    <span>{selectedDoc.location_label}</span>
                    <span>·</span>
                    <DocsContentFormatBadge
                      format={activeContentFormat}
                      label={t(
                        `apps:docs.contentFormat.${activeContentFormat}`,
                      )}
                      compact
                    />
                    <span>·</span>
                    <span>
                      {t('apps:docs.updated', {
                        date: timeAgo(activePage.updated_at, timeZone, locale),
                      })}
                    </span>
                  </div>
                </div>
                <div className="prose dark:prose-invert max-w-none pt-4">
                  {activeContentFormat === 'html' ? (
                    <DocsHtmlPageContentSurface
                      canEdit={selectedDoc.can_edit && activePage.can_edit}
                      content={activePage.content_text}
                      editing={htmlEditPageIds.has(activePage.id)}
                      labels={{
                        editSource: t('apps:docs.html.editSource'),
                        empty: t('apps:docs.html.empty'),
                        openRendered: t('apps:docs.html.openRendered'),
                        pastePlaceholder: t('apps:docs.html.pastePlaceholder'),
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
                        canImport={selectedDoc.can_edit && activePage.can_edit}
                        exportLabel={t('apps:docs.blockMarkdown.export')}
                        importLabel={t('apps:docs.blockMarkdown.import')}
                        onExport={() => handleBlockMarkdownExport(activePage)}
                        onImportFile={(file) =>
                          void handleBlockMarkdownImportFile(activePage, file)
                        }
                      />
                      <DocsBlockContentSurface
                        page={activePage}
                        canEdit={selectedDoc.can_edit && activePage.can_edit}
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
            ) : (
              <div className="text-center py-20">
                <FileText
                  size={48}
                  className="mx-auto mb-4 text-app-ink/70 opacity-20"
                />
                <p className="app-text-body text-app-ink/55 mb-4">
                  {t('apps:docs.noPages')}
                </p>
                {selectedDoc.can_edit ? (
                  <button
                    type="button"
                    onClick={() => void handleAddPage(null)}
                    className="app-text-control rounded-md bg-app-accent px-4 py-2 text-app-accent-fg hover:opacity-90"
                  >
                    {t('apps:docs.addFirstPage')}
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

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const renderDocsShell = (props: any) => {
  const {
    activeCategoryLabel,
    activeSpaceFilterId,
    availableSpaces,
    changingLocation,
    confirmDialog,
    copyDirectLink,
    copyShareLink,
    creating,
    creatingPage,
    docNavigationPathFor,
    docUrlFor,
    docs,
    editorView,
    handleAttachPmsTask,
    handleChangeLocation,
    handleChangeUserAccess,
    handleCreateDoc,
    handleCreatePage,
    handleDeleteDoc,
    handleDisableLinkShare,
    handleEnableLinkShare,
    handleInviteUser,
    handleRemoveUserShare,
    handleRenameDoc,
    handleSearchChange,
    handleToggleFavorite,
    hasActiveRefinement,
    inviteFocused,
    inviteQuery,
    inviteSuggestions,
    isListView,
    linkCopied,
    loadingList,
    locale,
    locationOptions,
    menuOpenId,
    newDocContentFormat,
    newDocLocation,
    newDocTitle,
    newPageContentFormat,
    newPageTitle,
    openCreateModal,
    openDoc,
    pages,
    promptDialog,
    readModeOpen,
    relatedPmsTasks,
    resetDocsFilters,
    resolveFileUrl,
    resolveLocationValueFromTarget,
    searchOpen,
    searchQuery,
    selectDocPage,
    selectedDoc,
    selectedPageId,
    setInviteFocused,
    setInviteQuery,
    setMenuOpenId,
    setNewDocContentFormat,
    setNewDocLocation,
    setNewDocTitle,
    setNewPageContentFormat,
    setNewPageTitle,
    setReadModeOpen,
    setSearchOpen,
    setShareAccessLevel,
    setShowCreateModal,
    setShowCreatePageModal,
    setShowShareModal,
    setSortBy,
    setSortDir,
    setTaskPickerOpen,
    shareAccessLevel,
    shareLinkCopied,
    shareLoading,
    sharingState,
    showCreateModal,
    showCreatePageModal,
    showShareModal,
    sortBy,
    sortDir,
    t,
    taskPickerOpen,
    timeZone,
    total,
    updateDocsSpaceFilterParam,
    workspaceSlug,
  } = props;
  return (
    <div className="h-full w-full flex flex-col min-w-0 bg-app-bg overflow-hidden relative">
      {confirmDialog}
      {promptDialog}
      {readModeOpen && selectedDoc ? (
        <DocsFullscreenReadModal
          doc={selectedDoc}
          pages={pages}
          selectedPageId={selectedPageId}
          onSelectPage={selectDocPage}
          onClose={() => setReadModeOpen(false)}
          resolveFileUrl={resolveFileUrl}
        />
      ) : null}

      {selectedDoc && workspaceSlug ? (
        <TaskPickerModal
          isOpen={taskPickerOpen}
          onClose={() => setTaskPickerOpen(false)}
          onPick={handleAttachPmsTask}
          excludeTaskIds={relatedPmsTasks.map(
            (task: RelatedPmsTaskItem) => task.task_id,
          )}
          workspaceSlug={workspaceSlug}
        />
      ) : null}

      {showCreateModal ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center">
          <button
            type="button"
            aria-label={t('common:actions.cancel')}
            className="absolute inset-0 bg-black/50"
            onClick={() => setShowCreateModal(false)}
          />
          <div className="relative w-full max-w-2xl rounded-lg border border-app-border bg-app-surface-sidebar p-6 space-y-4">
            <h2 className="app-text-title-md text-app-ink">
              {t('docs.newDoc')}
            </h2>
            <div>
              <label className="app-text-caption text-app-ink/55 mb-1 block">
                {t('planner.title')}
              </label>
              <input
                type="text"
                aria-label={t('planner.title')}
                value={newDocTitle}
                onChange={(event) => setNewDocTitle(event.target.value)}
                placeholder={t('docs.documentTitlePlaceholder')}
                className="app-text-body w-full rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    void handleCreateDoc();
                  }
                }}
              />
            </div>
            <div>
              <label className="app-text-caption text-app-ink/55 mb-1.5 block">
                {t('docs.contentFormat.label')}
              </label>
              <div
                className="grid gap-2 sm:grid-cols-2"
                role="radiogroup"
                aria-label={t('docs.contentFormat.label')}
              >
                {DOC_CONTENT_FORMAT_OPTIONS.map((format) => {
                  const Icon = format === 'html' ? FileCode2 : FileText;
                  const isSelected = newDocContentFormat === format;
                  return (
                    <button
                      key={format}
                      type="button"
                      role="radio"
                      aria-checked={isSelected}
                      onClick={() => {
                        if (format === newDocContentFormat) return;
                        setNewDocContentFormat(format);
                      }}
                      className={cn(
                        'rounded-md border px-3 py-2 text-left transition-colors',
                        isSelected
                          ? 'border-app-accent bg-app-accent/10 text-app-accent'
                          : 'border-app-border bg-app-bg text-app-ink hover:bg-app-surface-hover',
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Icon size={16} />
                        <span className="app-text-control">
                          {t(`docs.contentFormat.${format}`)}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <label className="app-text-caption text-app-ink/55 mb-1.5 block">
                {t('ai.search.metadataLocation')}
              </label>
              <LocationPicker
                value={newDocLocation}
                onChange={setNewDocLocation}
                options={locationOptions}
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="app-text-control rounded-md border border-app-border px-4 py-2 text-app-ink hover:bg-app-surface-hover"
              >
                {t('common:actions.cancel')}
              </button>
              <button
                type="button"
                onClick={() => void handleCreateDoc()}
                disabled={creating || !newDocTitle.trim()}
                className="app-text-control rounded-md bg-app-accent px-4 py-2 text-app-accent-fg hover:opacity-90 disabled:opacity-50"
              >
                {creating ? t('pms.creating') : t('common:actions.create')}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {showCreatePageModal && selectedDoc ? (
        <div className="fixed inset-0 z-[105] flex items-center justify-center">
          <button
            type="button"
            aria-label={t('common:actions.cancel')}
            className="absolute inset-0 bg-black/50"
            onClick={() => setShowCreatePageModal(false)}
          />
          <div className="relative w-full max-w-lg rounded-lg border border-app-border bg-app-surface-sidebar p-6 space-y-4">
            <h2 className="app-text-title-md text-app-ink">
              {t('docs.newPage')}
            </h2>
            <div>
              <label className="app-text-caption text-app-ink/55 mb-1 block">
                {t('planner.title')}
              </label>
              <input
                type="text"
                aria-label={t('planner.title')}
                value={newPageTitle}
                onChange={(event) => setNewPageTitle(event.target.value)}
                placeholder={t('docs.untitled')}
                className="app-text-body w-full rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    void handleCreatePage();
                  }
                }}
              />
            </div>
            <div>
              <label className="app-text-caption text-app-ink/55 mb-1.5 block">
                {t('docs.contentFormat.pageLabel')}
              </label>
              <div
                className="grid gap-2 sm:grid-cols-2"
                role="radiogroup"
                aria-label={t('docs.contentFormat.pageLabel')}
              >
                {DOC_CONTENT_FORMAT_OPTIONS.map((format) => {
                  const Icon = format === 'html' ? FileCode2 : FileText;
                  const isSelected = newPageContentFormat === format;
                  return (
                    <button
                      key={format}
                      type="button"
                      role="radio"
                      aria-checked={isSelected}
                      onClick={() => setNewPageContentFormat(format)}
                      className={cn(
                        'rounded-md border px-3 py-2 text-left transition-colors',
                        isSelected
                          ? 'border-app-accent bg-app-accent/10 text-app-accent'
                          : 'border-app-border bg-app-bg text-app-ink hover:bg-app-surface-hover',
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <Icon size={16} />
                        <span className="app-text-control">
                          {t(`docs.contentFormat.${format}`)}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowCreatePageModal(false)}
                className="app-text-control rounded-md border border-app-border px-4 py-2 text-app-ink hover:bg-app-surface-hover"
              >
                {t('common:actions.cancel')}
              </button>
              <button
                type="button"
                onClick={() => void handleCreatePage()}
                disabled={creatingPage || !newPageTitle.trim()}
                className="app-text-control rounded-md bg-app-accent px-4 py-2 text-app-accent-fg hover:opacity-90 disabled:opacity-50"
              >
                {creatingPage ? t('pms.creating') : t('common:actions.create')}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {showShareModal && selectedDoc ? (
        <div className="fixed inset-0 z-[110] flex items-center justify-center">
          <button
            type="button"
            aria-label={t('common:actions.cancel')}
            className="absolute inset-0 bg-black/50"
            onClick={() => setShowShareModal(false)}
          />
          <div className="relative w-full max-w-2xl rounded-lg border border-app-border bg-app-surface-sidebar p-6 space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="app-text-title-md text-app-ink">
                  {t('docs.share.title')}
                </h2>
                <p className="app-text-caption text-app-ink/55">
                  {selectedDoc.title}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowShareModal(false)}
                className="rounded p-1.5 text-app-ink/55 hover:bg-app-surface-hover"
              >
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
                      <Search
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/55"
                        size={14}
                      />
                      <input
                        type="text"
                        aria-label={t('docs.share.invitePlaceholder')}
                        value={inviteQuery}
                        onChange={(event) => setInviteQuery(event.target.value)}
                        onFocus={() => setInviteFocused(true)}
                        onBlur={() =>
                          window.setTimeout(() => setInviteFocused(false), 150)
                        }
                        placeholder={t('docs.share.invitePlaceholder')}
                        className="app-text-body w-full rounded-md border border-app-border bg-app-bg py-2 pl-9 pr-3 text-app-ink focus:border-app-accent focus:outline-none"
                      />
                      {inviteFocused && inviteSuggestions.length > 0 ? (
                        <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-60 overflow-y-auto rounded-md border border-app-border bg-app-surface-sidebar shadow-lg">
                          {inviteSuggestions.map((user: ShareableUserItem) => (
                            <button
                              key={user.id}
                              type="button"
                              onMouseDown={(event) => {
                                event.preventDefault();
                                void handleInviteUser(user.id);
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-app-surface-hover"
                            >
                              <div className="app-text-micro flex size-7 items-center justify-center rounded-full bg-app-accent/20 font-bold text-app-accent">
                                {user.full_name
                                  .split(' ')
                                  .map((name: string) => name[0])
                                  .join('')
                                  .slice(0, 2)}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="app-text-control text-app-ink truncate">
                                  {user.full_name}
                                </div>
                                <div className="app-text-micro text-app-ink/55 truncate">
                                  {user.email}
                                </div>
                              </div>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <select
                      aria-label={t('docs.share.access.label')}
                      value={shareAccessLevel}
                      onChange={(event) =>
                        setShareAccessLevel(
                          event.target.value as 'read' | 'edit',
                        )
                      }
                      className="app-field-input w-auto"
                    >
                      <option value="read">
                        {t('docs.share.access.read')}
                      </option>
                      <option value="edit">
                        {t('docs.share.access.edit')}
                      </option>
                    </select>
                  </div>

                  {sharingState?.users.length ? (
                    <div className="space-y-1.5">
                      <div className="app-text-overline text-app-ink/55">
                        {t('docs.share.peopleWithAccess')}
                      </div>
                      {sharingState.users.map((user: NativeDocShareUser) => (
                        <div
                          key={user.user_id}
                          className="flex items-center justify-between rounded-md border border-app-border bg-app-bg px-3 py-2"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <div className="app-text-micro flex size-7 items-center justify-center rounded-full bg-app-accent/20 font-bold text-app-accent shrink-0">
                              {user.full_name
                                .split(' ')
                                .map((name: string) => name[0])
                                .join('')
                                .slice(0, 2)}
                            </div>
                            <div className="min-w-0">
                              <div className="app-text-control text-app-ink truncate">
                                {user.full_name}
                              </div>
                              <div className="app-text-micro text-app-ink/55 truncate">
                                {user.email}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <select
                              aria-label={t('docs.share.access.label')}
                              value={user.access_level}
                              onChange={(event) =>
                                void handleChangeUserAccess(
                                  user.user_id,
                                  event.target.value as 'read' | 'edit',
                                )
                              }
                              className="app-field-input-sm w-auto"
                            >
                              <option value="read">
                                {t('docs.share.access.read')}
                              </option>
                              <option value="edit">
                                {t('docs.share.access.edit')}
                              </option>
                            </select>
                            <button
                              type="button"
                              onClick={() =>
                                void handleRemoveUserShare(user.user_id)
                              }
                              className="app-text-caption rounded border border-app-border px-2 py-1 text-app-ink hover:bg-app-surface-hover"
                            >
                              {t('pms.bulk.remove')}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>

                {/* 2. Who can access — target visibility */}
                <div className="rounded-lg border border-app-border bg-app-bg p-4 space-y-3">
                  <div>
                    <div className="app-text-control text-app-ink">
                      {t('docs.share.whoCanAccess')}
                    </div>
                    <div className="app-text-caption text-app-ink/55">
                      {t('docs.share.visibilityDescription')}
                    </div>
                  </div>
                  <LocationPicker
                    value={resolveLocationValueFromTarget(
                      selectedDoc.primary_target,
                    )}
                    onChange={(value) => void handleChangeLocation(value)}
                    options={locationOptions}
                    busy={changingLocation || !selectedDoc.can_manage}
                  />
                  {!selectedDoc.can_manage ? (
                    <div className="app-text-micro text-app-ink/55">
                      {t('docs.share.manageOnlyNotice')}
                    </div>
                  ) : null}
                </div>

                {/* 3. Copy link — always visible direct doc URL */}
                <div className="flex items-center gap-2 rounded-lg border border-app-border bg-app-bg px-3 py-2">
                  <Link2 size={16} className="text-app-ink/55 shrink-0" />
                  <input
                    type="text"
                    aria-label={t('docs.copyLink')}
                    readOnly
                    value={docUrlFor(selectedDoc)}
                    className="app-text-body-sm flex-1 min-w-0 bg-transparent text-app-ink focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => void copyDirectLink()}
                    className="app-text-control-sm flex items-center gap-1 rounded-md border border-app-border px-2.5 py-1 text-app-ink hover:bg-app-surface-hover"
                  >
                    <Copy size={12} />
                    <span>
                      {linkCopied ? t('docs.copied') : t('docs.copyLink')}
                    </span>
                  </button>
                </div>

                {/* 4. Internal share link — token-based toggle */}
                <div className="rounded-lg border border-app-border bg-app-bg p-4 space-y-3">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="app-text-control text-app-ink">
                        {t('docs.share.internalLink')}
                      </div>
                      <div className="app-text-caption text-app-ink/55">
                        {t('docs.share.internalLinkDescription')}
                      </div>
                    </div>
                    {sharingState?.link_share?.active ? (
                      <button
                        type="button"
                        onClick={() => void handleDisableLinkShare()}
                        className="app-text-control rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
                      >
                        {t('docs.share.disable')}
                      </button>
                    ) : (
                      <div className="flex items-center gap-2">
                        <select
                          aria-label={t('docs.share.access.label')}
                          value={
                            sharingState?.link_share?.access_level ?? 'read'
                          }
                          onChange={(event) =>
                            void handleEnableLinkShare(
                              event.target.value as 'read' | 'edit',
                            )
                          }
                          className="app-field-input w-auto"
                        >
                          <option value="read">
                            {t('docs.share.access.read')}
                          </option>
                          <option value="edit">
                            {t('docs.share.access.edit')}
                          </option>
                        </select>
                        <button
                          type="button"
                          onClick={() =>
                            void handleEnableLinkShare(
                              sharingState?.link_share?.access_level ?? 'read',
                            )
                          }
                          className="app-text-control rounded-md bg-app-accent px-3 py-2 text-app-accent-fg hover:opacity-90"
                        >
                          {t('docs.share.enableLink')}
                        </button>
                      </div>
                    )}
                  </div>

                  {sharingState?.link_share?.active ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        aria-label={t('docs.share.copy')}
                        readOnly
                        value={`${window.location.origin}${sharingState.link_share.share_path}`}
                        className="app-text-body flex-1 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink"
                      />
                      <button
                        type="button"
                        onClick={() => void copyShareLink()}
                        className="app-text-control flex items-center gap-1 rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
                      >
                        <Copy size={14} />
                        <span>
                          {shareLinkCopied
                            ? t('docs.copied')
                            : t('docs.share.copy')}
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          void handleEnableLinkShare(
                            sharingState.link_share?.access_level ?? 'read',
                            true,
                          )
                        }
                        className="app-text-control rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
                      >
                        {t('docs.share.regenerate')}
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
                <h1 className="app-text-title-lg text-app-ink">
                  {activeCategoryLabel}
                </h1>
                <p className="app-text-caption text-app-ink/55">
                  {t('docs.documentCount', { count: total })}
                </p>
              </div>
              <button
                type="button"
                onClick={() => openCreateModal()}
                className="app-text-control flex items-center gap-2 rounded-md bg-app-accent px-4 py-2 text-app-accent-fg shadow-sm transition-opacity hover:opacity-90"
              >
                <Plus size={16} />
                <span>{t('home.actionNewDoc')}</span>
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-3 border-b border-app-border pb-2">
              <button
                type="button"
                className="app-text-control-sm flex items-center gap-1.5 rounded px-2 py-1 text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink"
              >
                <Filter size={14} />
                <span>{t('pms.filter.filters')}</span>
              </button>
              <select
                aria-label={t('docs.filters.spaceLabel')}
                value={activeSpaceFilterId ?? ''}
                onChange={(event) =>
                  updateDocsSpaceFilterParam(event.target.value)
                }
                className="app-field-input-sm w-auto text-app-ink/70"
              >
                <option value="">{t('docs.filters.allSpaces')}</option>
                {activeSpaceFilterId &&
                !availableSpaces.some(
                  (space: { id: string }) => space.id === activeSpaceFilterId,
                ) ? (
                  <option value={activeSpaceFilterId}>
                    {t('docs.filters.selectedSpace')}
                  </option>
                ) : null}
                {availableSpaces.map((space: { id: string; name: string }) => (
                  <option key={space.id} value={space.id}>
                    {space.name}
                  </option>
                ))}
              </select>
              {hasActiveRefinement ? (
                <button
                  type="button"
                  onClick={resetDocsFilters}
                  className="app-text-control-sm rounded px-2 py-1 text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink"
                >
                  {t('docs.filters.reset')}
                </button>
              ) : null}
              <div className="app-text-caption ml-auto flex items-center gap-2 text-app-ink/55">
                {searchOpen ? (
                  <div className="relative">
                    <Search
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/55"
                      size={14}
                    />
                    <input
                      type="text"
                      aria-label={t('docs.searchPlaceholder')}
                      defaultValue={searchQuery}
                      placeholder={t('docs.searchPlaceholder')}
                      onChange={(event) =>
                        handleSearchChange(event.target.value)
                      }
                      className="app-text-body-sm w-64 rounded-md border border-app-border bg-app-surface-sidebar py-1.5 pl-9 pr-4 text-app-ink focus:border-app-accent focus:outline-none"
                      onBlur={(event) => {
                        if (!event.target.value) {
                          setSearchOpen(false);
                        }
                      }}
                    />
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setSearchOpen(true)}
                    className="p-1.5 rounded text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink"
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
                <div className="size-24 bg-app-surface-sidebar rounded-full flex items-center justify-center mb-6">
                  <FileText size={48} className="text-app-ink/70 opacity-20" />
                </div>
                <h2 className="app-text-title-md mb-2 text-app-ink">
                  {t('docs.noDocsFound')}
                </h2>
                <p className="app-text-body mb-8 max-w-xs mx-auto text-app-ink/55">
                  {t('docs.noDocsDescription')}
                </p>
                <button
                  type="button"
                  onClick={() => openCreateModal()}
                  className="app-text-control rounded-md bg-app-accent px-6 py-2 font-bold text-app-accent-fg transition-opacity hover:opacity-90"
                >
                  {t('home.actionNewDoc')}
                </button>
              </div>
            ) : (
              <div className="border border-app-border rounded-lg overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-app-border bg-app-surface-sidebar">
                      <th
                        className="app-text-overline text-left px-4 py-2.5 text-app-ink/55 cursor-pointer hover:text-app-ink"
                        aria-sort={
                          sortBy === 'title'
                            ? sortDir === 'asc'
                              ? 'ascending'
                              : 'descending'
                            : 'none'
                        }
                        onClick={() => {
                          if (sortBy === 'title')
                            setSortDir((current: 'asc' | 'desc') =>
                              current === 'asc' ? 'desc' : 'asc',
                            );
                          else {
                            setSortBy('title');
                            setSortDir('asc');
                          }
                        }}
                      >
                        {t('pms.name')}
                      </th>
                      <th className="app-text-overline text-left px-4 py-2.5 text-app-ink/55">
                        {t('ai.search.metadataLocation')}
                      </th>
                      <th className="app-text-overline text-left px-4 py-2.5 text-app-ink/55">
                        {t('docs.share.sharing')}
                      </th>
                      <th
                        className="app-text-overline text-left px-4 py-2.5 text-app-ink/55 cursor-pointer hover:text-app-ink"
                        aria-sort={
                          sortBy === 'updated_at'
                            ? sortDir === 'asc'
                              ? 'ascending'
                              : 'descending'
                            : 'none'
                        }
                        onClick={() => {
                          if (sortBy === 'updated_at')
                            setSortDir((current: 'asc' | 'desc') =>
                              current === 'asc' ? 'desc' : 'asc',
                            );
                          else {
                            setSortBy('updated_at');
                            setSortDir('desc');
                          }
                        }}
                      >
                        {t('docs.updatedHeader')}
                      </th>
                      <th
                        className="w-12"
                        aria-label={t('apps:docs.moreActions')}
                      />
                    </tr>
                  </thead>
                  <tbody>
                    {docs.map((item: DocsHubItem) => {
                      const itemContentFormat =
                        resolveDocsHubContentFormat(item);
                      const ItemIcon =
                        itemContentFormat === 'html' ? FileCode2 : FileText;
                      const itemDocPath = docNavigationPathFor(item.id);
                      return (
                        <tr
                          key={item.id}
                          onClick={() => openDoc(item.id)}
                          className="cursor-pointer border-b border-app-border last:border-b-0 hover:bg-app-surface-sidebar/60"
                        >
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3 min-w-0">
                              <ItemIcon
                                size={16}
                                className="text-app-accent shrink-0"
                              />
                              <div className="min-w-0">
                                <Link
                                  to={itemDocPath}
                                  onClick={(event) => event.stopPropagation()}
                                  className="app-text-control block truncate text-app-ink hover:text-app-accent"
                                >
                                  {item.title}
                                </Link>
                                <div className="app-text-caption flex flex-wrap items-center gap-x-2 gap-y-1 text-app-ink/55">
                                  <DocsContentFormatBadge
                                    format={itemContentFormat}
                                    label={t(
                                      `docs.contentFormat.${itemContentFormat}`,
                                    )}
                                    compact
                                  />
                                  <span>
                                    {t('docs.pageCount', {
                                      count: item.page_count,
                                    })}
                                  </span>
                                </div>
                              </div>
                              <Star
                                size={14}
                                className={cn(
                                  'shrink-0 text-app-ink/70',
                                  item.is_favorite &&
                                    'text-yellow-500 fill-yellow-500',
                                )}
                                onClick={(event) =>
                                  void handleToggleFavorite(event, item)
                                }
                              />
                            </div>
                          </td>
                          <td className="px-4 py-3 app-text-body-sm text-app-ink/45">
                            {item.location_label}
                          </td>
                          <td className="px-4 py-3 app-text-body-sm text-app-ink/45">
                            <div className="flex items-center gap-2">
                              {item.source_type === 'native_doc' &&
                              item.is_private ? (
                                <Lock size={14} />
                              ) : (
                                <Globe size={14} />
                              )}
                              <span>{sharingLabel(item, t)}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 app-text-body-sm text-app-ink/45">
                            {timeAgo(item.updated_at, timeZone, locale)}
                          </td>
                          <td className="px-4 py-3">
                            <DropdownMenu
                              open={menuOpenId === item.id}
                              onOpenChange={(open) =>
                                setMenuOpenId(open ? item.id : null)
                              }
                              side="bottom"
                              sideOffset={6}
                              contentClassName="w-48 min-w-[12rem] max-w-[12rem] rounded-lg border-app-border bg-app-surface-sidebar p-0 py-1 text-app-ink"
                              trigger={
                                <button
                                  type="button"
                                  aria-label={t('apps:docs.moreActions')}
                                  title={t('apps:docs.moreActions')}
                                  onClick={(event) => event.stopPropagation()}
                                  className="rounded p-1.5 text-app-ink/55 hover:bg-app-surface-hover"
                                >
                                  <MoreHorizontal size={16} />
                                </button>
                              }
                              items={[
                                {
                                  id: 'rename',
                                  disabled: !item.can_manage,
                                  onSelect: () => void handleRenameDoc(item),
                                  label: (
                                    <span className="flex items-center gap-2">
                                      <Pencil size={14} />
                                      <span className="app-text-control-sm">
                                        {t('common:actions.rename')}
                                      </span>
                                    </span>
                                  ),
                                },
                                {
                                  id: 'delete',
                                  disabled: !item.can_manage,
                                  tone: 'danger',
                                  onSelect: () => void handleDeleteDoc(item),
                                  label: (
                                    <span className="flex items-center gap-2">
                                      <Trash2 size={14} />
                                      <span className="app-text-control-sm">
                                        {t('common:actions.delete')}
                                      </span>
                                    </span>
                                  ),
                                },
                              ]}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : (
        editorView
      )}
    </div>
  );
};

export const DocsView = () => {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const { toolId, docId, shareToken, workspaceSlug } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedPageId = getDocPageIdFromSearchParams(searchParams);
  const requestedPageIdRef = useRef<string | null>(requestedPageId);
  requestedPageIdRef.current = requestedPageId;
  const auth = useAuth();
  const { token } = auth;
  const { reconnectSeq } = useRealtime();
  const timeZone = normalizeTimeZone(auth.user?.time_zone);
  const { uploadFile, createLinkedUploadFile, resolveFileUrl } =
    useMediaUpload();
  const { confirm, confirmDialog } = useConfirm();
  const { prompt, promptDialog } = usePrompt();

  const docsViewState = useDocsViewState();
  const {
    activeDragId,
    availableSpaces,
    changingLocation,
    contentEditorVersions,
    copiedDocId,
    creating,
    creatingPage,
    docMenuOpen,
    dropIndicator,
    editorLoading,
    htmlEditPageIds,
    inviteFocused,
    inviteQuery,
    linkCopied,
    manualExpandedNodes,
    menuOpenId,
    newDocContentFormat,
    newDocLocation,
    newDocTitle,
    newPageContentFormat,
    newPageTitle,
    pages,
    readModeOpen,
    relatedPmsTaskBusyId,
    relatedPmsTaskState,
    searchOpen,
    selectedDoc,
    shareAccessLevel,
    shareLinkCopied,
    shareLoading,
    shareableUsers,
    sharingState,
    showCreateModal,
    showCreatePageModal,
    showShareModal,
    taskPickerOpen,
  } = docsViewState;
  const {
    setActiveDragId,
    setAvailableSpaces,
    setChangingLocation,
    setContentEditorVersions,
    setCopiedDocId,
    setCreating,
    setCreatingPage,
    setDocMenuOpen,
    setDropIndicator,
    setEditorLoading,
    setHtmlEditPageIds,
    setInviteFocused,
    setInviteQuery,
    setLinkCopied,
    setManualExpandedNodes,
    setMenuOpenId,
    setNewDocContentFormat,
    setNewDocLocation,
    setNewDocTitle,
    setNewPageContentFormat,
    setNewPageTitle,
    setPages,
    setReadModeOpen,
    setRelatedPmsTaskBusyId,
    setRelatedPmsTaskState,
    setSearchOpen,
    setSelectedDoc,
    setShareAccessLevel,
    setShareLoading,
    setShareLinkCopied,
    setShareableUsers,
    setSharingState,
    setShowCreateModal,
    setShowCreatePageModal,
    setShowShareModal,
    setTaskPickerOpen,
  } = docsViewState;
  const docMenuRef = useRef<HTMLDivElement>(null);
  const closeDocMenu = useCallback(
    () => setDocMenuOpen(false),
    [setDocMenuOpen],
  );
  useCloseOnOutsidePointer(docMenuRef, docMenuOpen, closeDocMenu);

  const newPageParentIdRef = useRef<string | null>(null);
  const loadedSharedDocIdRef = useRef<string | null>(null);
  const pendingPageSelectionRef = useRef<string | null>(null);

  const docPagesRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const docPagesPendingParentIdRef = useRef<string | null>(null);

  const requestedCategory = toolId
    ? CATEGORY_MAP[toolId]
    : searchParams.get('view');
  const activeCategory: DocsViewCategory = isDocsViewCategory(requestedCategory)
    ? requestedCategory
    : 'all';
  const activeCategoryLabel = t(
    (toolId && CATEGORY_LABEL_KEYS[toolId]) ||
      VIEW_LABEL_KEYS[activeCategory] ||
      'docs.category.all',
  );
  const activeSourceApp = searchParams.get('source_app') ?? undefined;
  const activeSourceKind = searchParams.get('source_kind') ?? undefined;
  const activeSpaceFilterId =
    searchParams.get(DOCS_SPACE_QUERY_PARAM)?.trim() || undefined;
  const activeFilterQuery = useMemo(
    () => getDocsFilterQueryString(searchParams),
    [searchParams],
  );
  const activeItemId =
    docId ?? (shareToken ? loadedSharedDocIdRef.current : null);
  const activeDocId = activeItemId ?? null;
  const selectedPageId = resolveDocsPageSelection(pages, requestedPageId);
  const selectedPageIdRef = useRef<string | null>(null);
  selectedPageIdRef.current = selectedPageId;
  const selectedPageExpandedNodes = useMemo(
    () => getExpandedDocPageNodeIds(pages, selectedPageId),
    [pages, selectedPageId],
  );
  const expandedNodes = useMemo(() => {
    if (selectedPageExpandedNodes.size === 0) {
      return manualExpandedNodes;
    }
    const next = new Set(manualExpandedNodes);
    for (const pageId of selectedPageExpandedNodes) {
      next.add(pageId);
    }
    return next;
  }, [manualExpandedNodes, selectedPageExpandedNodes]);
  const visibleTree = useMemo(
    () => flattenVisibleTree(pages, expandedNodes),
    [pages, expandedNodes],
  );
  const pagesById = useMemo(() => buildDocsPagesById(pages), [pages]);
  const childCounts = useMemo(() => countDocsPageChildren(pages), [pages]);
  const activePage =
    pages.find((page) => page.id === selectedPageId) ?? pages[0] ?? null;
  const activePageId = activePage?.id ?? null;
  const activeContentFormat = resolveDocsContentFormat(activePage);
  const activePageAuthorName = resolveDocsPageAuthorName(
    activePage,
    selectedDoc,
  );
  const activePageAuthorInitials = docsAuthorInitials(activePageAuthorName);
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
  const isListView = !activeItemId && !shareToken;
  const docsHubController = useDocsHubController({
    token,
    workspaceSlug,
    listEnabled: isListView,
    activeCategory,
    activeSourceApp,
    activeSourceKind,
    activeSpaceId: activeSpaceFilterId,
  });
  const { docs, loadingList, searchQuery, sortBy, sortDir, total } =
    docsHubController.state;
  const { fetchDocs, handleSearchChange, setDocs, setSortBy, setSortDir } =
    docsHubController.actions;
  const relatedPmsTasks = relatedPmsTaskState.items;
  const relatedPmsTaskError = relatedPmsTaskState.error;
  const hasDocsWorkspace = hasWorkspaceMembership(auth.user, workspaceSlug);
  const currentWorkspace = useMemo(
    () =>
      auth.user?.workspaces.find(
        (workspace) => workspace.slug === workspaceSlug,
      ) ??
      auth.user?.workspaces[0] ??
      null,
    [auth.user, workspaceSlug],
  );
  const docsRoot = workspaceSlug
    ? buildWorkspaceAppPath(workspaceSlug, 'docs')
    : resolveDefaultWorkspaceAppPath(auth.user, 'docs');
  const docPathFor = useCallback(
    (itemId: string, pageId?: string | null) => {
      const path = workspaceSlug
        ? buildWorkspaceAppPath(workspaceSlug, 'docs', `/${itemId}`)
        : resolveDefaultWorkspaceAppPath(auth.user, 'docs', `/${itemId}`);
      return appendDocPageQuery(path, pageId);
    },
    [auth.user, workspaceSlug],
  );
  const htmlRenderPathFor = useCallback(
    (itemId: string, pageId: string) =>
      workspaceSlug
        ? buildWorkspaceAppPath(
            workspaceSlug,
            'docs',
            `/${itemId}/html/${pageId}`,
          )
        : resolveDefaultWorkspaceAppPath(
            auth.user,
            'docs',
            `/${itemId}/html/${pageId}`,
          ),
    [auth.user, workspaceSlug],
  );

  const selectDocPage = useCallback(
    (pageId: string | null) => {
      pendingPageSelectionRef.current = pageId;
      setSearchParams(withDocPageSearchParam(searchParams, pageId), {
        replace: true,
      });
    },
    [searchParams, setSearchParams],
  );

  const setHtmlPageEditMode = useCallback(
    (pageId: string, editing: boolean) => {
      setHtmlEditPageIds((current) => {
        const next = new Set(current);
        if (editing) {
          next.add(pageId);
        } else {
          next.delete(pageId);
        }
        return next;
      });
    },
    [setHtmlEditPageIds],
  );

  const loadDoc = useCallback(
    async (itemId: string, currentShareToken?: string | null) => {
      if (!token) return;
      setEditorLoading(true);
      try {
        const [item, pageResponse] = await Promise.all([
          getDocsItem(token, itemId, currentShareToken, workspaceSlug),
          listDocPages(token, itemId, currentShareToken, workspaceSlug),
        ]);
        loadedSharedDocIdRef.current = currentShareToken ? item.id : null;
        setSelectedDoc(item);
        setPages(pageResponse.items);
        pendingPageSelectionRef.current = null;
        setManualExpandedNodes(new Set());
      } catch {
        loadedSharedDocIdRef.current = null;
        setSelectedDoc(null);
        setPages([]);
        pendingPageSelectionRef.current = null;
      } finally {
        setEditorLoading(false);
      }
    },
    [
      setEditorLoading,
      setManualExpandedNodes,
      setPages,
      setSelectedDoc,
      token,
      workspaceSlug,
    ],
  );

  const clearLoadedDoc = useCallback(() => {
    loadedSharedDocIdRef.current = null;
    setSelectedDoc(null);
    setPages([]);
    pendingPageSelectionRef.current = null;
    setEditorLoading(false);
  }, [setEditorLoading, setPages, setSelectedDoc]);

  const loadSharedDoc = useCallback(
    async (currentShareToken: string) => {
      if (!token) return;
      setEditorLoading(true);
      try {
        const response = await resolveSharedLink(token, currentShareToken);
        await loadDoc(response.item.id, currentShareToken);
      } catch {
        clearLoadedDoc();
      }
    },
    [clearLoadedDoc, loadDoc, setEditorLoading, token],
  );

  const clearRelatedPmsTaskState = useCallback(() => {
    setRelatedPmsTaskState({ error: null, items: [] });
  }, [setRelatedPmsTaskState]);

  const loadRelatedPmsTasks = useCallback(
    async (itemId: string, isCancelled: () => boolean) => {
      if (!token) return;
      setRelatedPmsTaskState((current) => ({ ...current, error: null }));
      try {
        const response = await listDocPmsTasks(token, itemId, workspaceSlug);
        if (isCancelled()) return;
        setRelatedPmsTaskState({ error: null, items: response.items });
      } catch (error) {
        if (isCancelled()) return;
        setRelatedPmsTaskState({
          error:
            error instanceof Error
              ? error.message
              : t('docs.relatedPms.loadFailed'),
          items: [],
        });
      }
    },
    [setRelatedPmsTaskState, t, token, workspaceSlug],
  );

  const refreshDocPages = useCallback(
    async (
      itemId: string,
      currentShareToken?: string | null,
      expandedParentId?: string | null,
    ) => {
      if (!token) return;
      try {
        const pageResponse = await listDocPages(
          token,
          itemId,
          currentShareToken,
          workspaceSlug,
        );
        const nextPages = pageResponse.items;
        const nextDocSummary = summarizeDocsPageCollection(nextPages);
        setPages(nextPages);
        setSelectedDoc((currentDoc) =>
          currentDoc?.id === itemId
            ? {
                ...currentDoc,
                ...nextDocSummary,
              }
            : currentDoc,
        );
        setDocs((current) =>
          current.map((doc) =>
            doc.id === itemId ? { ...doc, ...nextDocSummary } : doc,
          ),
        );
        const nextSelection = resolveDocsRefreshSelection({
          currentPageId: selectedPageIdRef.current,
          pages: nextPages,
          requestedPageId: requestedPageIdRef.current,
        });
        if (nextSelection.shouldSelect) {
          pendingPageSelectionRef.current = nextSelection.pageId;
          selectDocPage(nextSelection.pageId);
        }
        if (expandedParentId) {
          setManualExpandedNodes((current) =>
            new Set(current).add(expandedParentId),
          );
        }
      } catch {
        // The stream is advisory; keep the existing page tree if a refresh fails.
      }
    },
    [
      selectDocPage,
      setDocs,
      setManualExpandedNodes,
      setPages,
      setSelectedDoc,
      token,
      workspaceSlug,
    ],
  );

  const scheduleDocPagesRefresh = useCallback(
    (expandedParentId?: string | null) => {
      if (!activeDocId) {
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
        void refreshDocPages(activeDocId, shareToken, parentId);
      }, 150);
    },
    [activeDocId, refreshDocPages, shareToken],
  );

  useRealtimeSubscription(
    activeDocId && token
      ? createDocsPagesRealtimeSubscriptionMessage({
          key: activeDocId,
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
          !activeDocId ||
          (payload?.doc_id && payload.doc_id !== activeDocId)
        ) {
          return;
        }
        scheduleDocPagesRefresh(payload?.parent_id ?? null);
      },
      [activeDocId, scheduleDocPagesRefresh],
    ),
  );

  useEffect(() => {
    if (!activeDocId || !token) {
      return;
    }
    scheduleDocPagesRefresh(null);
  }, [activeDocId, reconnectSeq, scheduleDocPagesRefresh, token]);

  useEffect(
    () => () => {
      if (docPagesRefreshTimerRef.current !== null) {
        clearTimeout(docPagesRefreshTimerRef.current);
        docPagesRefreshTimerRef.current = null;
      }
      docPagesPendingParentIdRef.current = null;
    },
    [activeDocId, setHtmlEditPageIds],
  );

  useEffect(() => {
    const next = removeLegacyDocsSearchParams(searchParams);
    if (!next) return;
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (!token) return;
    if (!shareToken) {
      loadedSharedDocIdRef.current = null;
      return;
    }
    void loadSharedDoc(shareToken);
  }, [loadSharedDoc, shareToken, token]);

  useEffect(() => {
    if (!token || !docId || shareToken) return;
    void loadDoc(docId, null);
  }, [docId, loadDoc, shareToken, token]);

  useEffect(() => {
    setHtmlEditPageIds(new Set());
  }, [activeDocId, setHtmlEditPageIds]);

  useEffect(() => {
    if (!token || !activeDocId || !activePageId) return;
    void recordDocView(
      token,
      activeDocId,
      activePageId,
      shareToken,
      workspaceSlug,
    );
  }, [activeDocId, activePageId, shareToken, token, workspaceSlug]);

  useEffect(() => {
    if (!token || !activeDocId || shareToken) {
      clearRelatedPmsTaskState();
      return;
    }
    let cancelled = false;
    void loadRelatedPmsTasks(activeDocId, () => cancelled);
    return () => {
      cancelled = true;
    };
  }, [
    activeDocId,
    clearRelatedPmsTaskState,
    loadRelatedPmsTasks,
    shareToken,
    token,
  ]);

  useEffect(() => {
    if (!token || !isListView) return;
    let cancelled = false;
    void listSpaces(token, workspaceSlug)
      .then((spaces) => {
        if (!cancelled) {
          setAvailableSpaces(Array.isArray(spaces) ? spaces : []);
        }
      })
      .catch(() => {
        if (!cancelled) setAvailableSpaces([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isListView, setAvailableSpaces, token, workspaceSlug]);

  const docNavigationPathFor = (itemId: string) => {
    const basePath = toolId ? `/tool/${toolId}/${itemId}` : docPathFor(itemId);
    return activeFilterQuery ? `${basePath}?${activeFilterQuery}` : basePath;
  };

  const openDoc = (itemId: string) => {
    navigate(docNavigationPathFor(itemId));
  };

  const handleBack = () => {
    if (shareToken && !hasDocsWorkspace) {
      navigate('/');
      return;
    }
    const basePath = toolId ? `/tool/${toolId}` : docsRoot;
    navigate(activeFilterQuery ? `${basePath}?${activeFilterQuery}` : basePath);
  };

  const openCreateModal = useCallback(
    (templateTitle?: string) => {
      const defaultLocation = resolveDefaultDocsCreateLocation(activeCategory);
      setNewDocTitle(templateTitle ?? '');
      setNewDocLocation(defaultLocation);
      setNewDocContentFormat('block');
      setShowCreateModal(true);
      if (token) {
        void listSpaces(token, workspaceSlug)
          .then((spaces) =>
            setAvailableSpaces(Array.isArray(spaces) ? spaces : []),
          )
          .catch(() => setAvailableSpaces([]));
      }
    },
    [
      activeCategory,
      setAvailableSpaces,
      setNewDocContentFormat,
      setNewDocLocation,
      setNewDocTitle,
      setShowCreateModal,
      token,
      workspaceSlug,
    ],
  );

  useEffect(() => {
    const handler = () => openCreateModal();
    window.addEventListener('docs:create', handler);
    return () => window.removeEventListener('docs:create', handler);
  }, [openCreateModal]);

  useEffect(() => {
    if (shareToken) {
      return;
    }
    const createState = consumeDocsCreateSearchParam(searchParams);
    if (!createState.shouldOpen || !createState.searchParams) return;
    setShowCreateModal(true);
    setSearchParams(createState.searchParams, { replace: true });
  }, [searchParams, setSearchParams, setShowCreateModal, shareToken]);

  const updateDocsSpaceFilterParam = useCallback(
    (spaceId: string) => {
      setSearchParams(withDocsSpaceFilterSearchParam(searchParams, spaceId), {
        replace: true,
      });
    },
    [searchParams, setSearchParams],
  );

  const resetDocsFilters = useCallback(() => {
    setSearchParams(resetDocsFilterSearchParams(searchParams), {
      replace: true,
    });
  }, [searchParams, setSearchParams]);

  const hasActiveRefinement = Boolean(
    activeSourceApp || activeSourceKind || activeSpaceFilterId,
  );

  const locationOptions = useMemo<LocationOption[]>(
    () => [
      {
        value: 'workspace',
        icon: Globe,
        title: currentWorkspace
          ? t('docs.location.workspaceNamed', { name: currentWorkspace.name })
          : t('docs.location.workspace'),
        desc: t('docs.location.workspaceDesc'),
      },
      ...availableSpaces.map((space) => ({
        value: `space:${space.id}`,
        icon: Users,
        title: space.name,
        desc: t('docs.location.spaceDesc'),
      })),
      {
        value: 'private',
        icon: Lock,
        title: t('docs.category.private'),
        desc: t('docs.location.privateDesc'),
      },
    ],
    [availableSpaces, currentWorkspace, t],
  );

  const resolveTargetFromLocationValue = useCallback(
    (locationValue: string) => {
      return resolveDocsCreatePrimaryTarget(
        locationValue,
        currentWorkspace?.id,
      );
    },
    [currentWorkspace?.id],
  );

  const resolveLocationValueFromTarget = useCallback(
    (target: { app: string; type: string; id: string } | null) => {
      return resolveDocsCreateLocationValue(target);
    },
    [],
  );

  const handleCreateDoc = async () => {
    if (!token || !newDocTitle.trim()) return;
    setCreating(true);
    try {
      const item = await createNativeDoc(
        token,
        {
          title: newDocTitle.trim(),
          content_format: newDocContentFormat,
          primary_target: resolveTargetFromLocationValue(newDocLocation),
        },
        workspaceSlug,
      );
      setShowCreateModal(false);
      setNewDocTitle('');
      setNewDocContentFormat('block');
      openDoc(item.id);
    } finally {
      setCreating(false);
    }
  };

  const handleToggleFavorite = async (
    event: React.MouseEvent,
    item: DocsHubItem,
  ) => {
    event.stopPropagation();
    if (!token) return;
    try {
      const response = await toggleDocFavorite(token, item.id, workspaceSlug);
      setDocs((current) =>
        current.map((doc) =>
          doc.id === item.id
            ? { ...doc, is_favorite: response.is_favorite }
            : doc,
        ),
      );
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
    const nextTitle = await prompt({
      title: t('docs.renameDocument'),
      defaultValue: item.title,
      submitLabel: t('common:actions.save'),
      cancelLabel: t('common:actions.cancel'),
    });
    if (!nextTitle || nextTitle.trim() === item.title) return;
    try {
      const updated = await updateDocsItem(
        token,
        item.id,
        { title: nextTitle.trim() },
        shareToken,
        workspaceSlug,
      );
      setDocs((current) =>
        current.map((doc) => (doc.id === updated.id ? updated : doc)),
      );
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
      title: t('docs.deleteDocumentConfirm', { title: item.title }),
      description:
        item.source_type === 'native_doc'
          ? t('docs.deleteDocDescription')
          : t('docs.removeFromDocsDescription'),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await deleteDocsItem(token, item.id, shareToken, workspaceSlug);
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
      const duplicate = await duplicateDocsItem(
        token,
        item.id,
        shareToken,
        workspaceSlug,
      );
      void fetchDocs();
      const basePath = toolId
        ? `/tool/${toolId}/${duplicate.id}`
        : docPathFor(duplicate.id);
      navigate(
        activeFilterQuery ? `${basePath}?${activeFilterQuery}` : basePath,
      );
    } catch {
      // no-op
    }
  };

  const docUrlFor = (item: DocsHubItem): string => {
    const pageId = item.id === activeDocId ? activePageId : null;
    const path = toolId
      ? appendDocPageQuery(`/tool/${toolId}/${item.id}`, pageId)
      : docPathFor(item.id, pageId);
    return `${window.location.origin}${path}`;
  };

  const handleCopyLink = async (item: DocsHubItem) => {
    setDocMenuOpen(false);
    try {
      await navigator.clipboard.writeText(docUrlFor(item));
      setCopiedDocId(item.id);
      window.setTimeout(
        () =>
          setCopiedDocId((current) => (current === item.id ? null : current)),
        1500,
      );
    } catch {
      // no-op
    }
  };

  const handleOpenInNewTab = (item: DocsHubItem) => {
    setDocMenuOpen(false);
    window.open(docUrlFor(item), '_blank', 'noopener,noreferrer');
  };

  const handleOpenHtmlPage = async (page: DocsPageItem) => {
    if (!selectedDoc) return;
    if (shareToken) {
      await flushPendingContentTextSave();
      window.open(
        `/docs/shared/${shareToken}/html/${page.id}`,
        '_blank',
        'noopener,noreferrer',
      );
      return;
    }
    await flushPendingContentTextSave();
    window.open(
      htmlRenderPathFor(selectedDoc.id, page.id),
      '_blank',
      'noopener,noreferrer',
    );
  };

  const handlePrintDoc = () => {
    setDocMenuOpen(false);
    window.print();
  };

  const handleAddPage = (parentId?: string | null) => {
    if (!token || !selectedDoc || !selectedDoc.can_edit) return;
    setNewPageTitle(t('apps:docs.untitled'));
    newPageParentIdRef.current = parentId ?? null;
    setNewPageContentFormat('block');
    setShowCreatePageModal(true);
  };

  const handleCreatePage = async () => {
    if (!token || !selectedDoc || !selectedDoc.can_edit || !newPageTitle.trim())
      return;
    setCreatingPage(true);
    try {
      const parentId = newPageParentIdRef.current;
      const page = await createDocPage(
        token,
        selectedDoc.id,
        {
          title: newPageTitle.trim(),
          parent_id: parentId,
          content_format: newPageContentFormat,
          ...(newPageContentFormat === 'block'
            ? { content_blocks: [] }
            : { content_text: null }),
        },
        shareToken,
        workspaceSlug,
      );
      const nextPages = [...pages, page];
      const nextDocSummary = summarizeDocsPageCollection(nextPages);
      setPages(nextPages);
      setSelectedDoc((currentDoc) =>
        currentDoc
          ? {
              ...currentDoc,
              ...nextDocSummary,
            }
          : currentDoc,
      );
      setDocs((current) =>
        current.map((doc) =>
          doc.id === selectedDoc.id ? { ...doc, ...nextDocSummary } : doc,
        ),
      );
      selectDocPage(page.id);
      if (parentId) {
        setManualExpandedNodes((current) => new Set(current).add(parentId));
      }
      setShowCreatePageModal(false);
      setNewPageTitle('');
    } catch {
      // no-op
    } finally {
      setCreatingPage(false);
    }
  };

  const handleDeletePage = async (page: DocsPageItem) => {
    if (!token || !page.can_edit) return;
    if (
      resolveDocsContentFormat(page) === 'html' &&
      pages.filter((item) => item.trashed_at === null).length <= 1
    ) {
      return;
    }
    const ok = await confirm({
      title: t('docs.deletePageConfirm', { title: page.title }),
      description: t('docs.deletePageDescription'),
      confirmLabel: t('common:actions.delete'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await deleteDocPage(token, page.id, shareToken, workspaceSlug);
      const {
        pages: nextPages,
        removedIds,
        summary: nextDocSummary,
      } = removeDocsPageSubtree(pages, page.id);
      setPages(nextPages);
      setSelectedDoc((currentDoc) =>
        currentDoc
          ? {
              ...currentDoc,
              ...nextDocSummary,
            }
          : currentDoc,
      );
      setDocs((current) =>
        current.map((doc) =>
          doc.id === page.doc_id ? { ...doc, ...nextDocSummary } : doc,
        ),
      );
      if (selectedPageId && removedIds.has(selectedPageId)) {
        selectDocPage(nextPages[0]?.id ?? null);
      }
    } catch {
      // no-op
    }
  };

  const updatePageContentBlocksLocally = useCallback(
    (pageId: string, blocks: Record<string, unknown>[]) => {
      setPages((current) =>
        updateDocsPageContentBlocks(current, pageId, blocks),
      );
    },
    [setPages],
  );

  const {
    cancelQueuedSave,
    flushTextSave: flushPendingContentTextSave,
    queueBlockSave,
    queueTextSave,
  } = useDocsPageContentSaveController({
    token,
    shareToken,
    workspaceSlug,
    savePage: updateDocPage,
    onSavedPage: (updated) => {
      setPages((current) => applyUpdatedDocsPage(current, updated));
    },
  });
  const handleEditorChange = (
    pageId: string,
    blocks: Record<string, unknown>[],
  ) => {
    const target = pagesById.get(pageId);
    if (!token || !target?.can_edit) return;
    updatePageContentBlocksLocally(pageId, blocks);
    queueBlockSave(pageId, blocks);
  };

  const updatePageContentTextLocally = (
    pageId: string,
    contentText: string,
  ) => {
    setPages((current) =>
      updateDocsPageContentText(current, pageId, contentText),
    );
  };

  const bumpContentEditorVersion = (pageId: string) => {
    setContentEditorVersions((current) =>
      bumpDocsContentEditorVersion(current, pageId),
    );
  };

  const handleContentTextChange = (contentText: string) => {
    if (!token || !activePage?.can_edit) return;
    updatePageContentTextLocally(activePage.id, contentText);
    queueTextSave(activePage.id, contentText);
  };

  const handleContentTextFileUpload = async (
    page: DocsPageItem,
    file: File | null,
  ) => {
    if (!token || !page.can_edit || !file) return;
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
      setPages((current) => applyUpdatedDocsPage(current, updated));
    } catch {
      // no-op
    }
  };

  const handleBlockMarkdownImportFile = async (
    page: DocsPageItem,
    file: File | null,
  ) => {
    if (!token || !page.can_edit || !file) return;
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
      setPages((current) => applyUpdatedDocsPage(current, updated));
      bumpContentEditorVersion(page.id);
    } catch {
      window.alert(t('apps:docs.blockMarkdown.importFailed'));
    }
  };

  const handlePageTitleSave = async (pageId: string, nextTitle: string) => {
    if (!token) return;
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
      setPages((current) =>
        current.map((page) => (page.id === updated.id ? updated : page)),
      );
    } catch {
      // no-op
    }
  };

  const handleCollabChange = useCallback(
    (pageId: string, content: Record<string, unknown>[]) => {
      updatePageContentBlocksLocally(pageId, content);
    },
    [updatePageContentBlocksLocally],
  );

  const toggleExpand = (nodeId: string) => {
    setManualExpandedNodes((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  const refreshSharing = useCallback(
    async (itemId: string) => {
      if (!token) return;
      const [sharing, users] = await Promise.all([
        getDocSharing(token, itemId, workspaceSlug),
        listShareableUsers(token, undefined, workspaceSlug),
      ]);
      setSharingState(sharing);
      setShareableUsers(users);
    },
    [setShareableUsers, setSharingState, token, workspaceSlug],
  );

  const openShareModal = async () => {
    if (!selectedDoc?.can_share || !token) return;
    setShareLoading(true);
    setShowShareModal(true);
    void listSpaces(token, workspaceSlug)
      .then((spaces) => setAvailableSpaces(Array.isArray(spaces) ? spaces : []))
      .catch(() => setAvailableSpaces([]));
    try {
      await refreshSharing(selectedDoc.id);
    } finally {
      setShareLoading(false);
    }
  };

  const handleChangeLocation = async (nextLocation: string) => {
    if (!token || !selectedDoc || !selectedDoc.can_manage) return;
    const current = resolveLocationValueFromTarget(selectedDoc.primary_target);
    if (current === nextLocation) return;
    setChangingLocation(true);
    try {
      const nextTarget = resolveTargetFromLocationValue(nextLocation);
      const updated =
        nextTarget === null
          ? await deleteDocTarget(token, selectedDoc.id, workspaceSlug)
          : await updateDocTarget(
              token,
              selectedDoc.id,
              nextTarget,
              workspaceSlug,
            );
      setSelectedDoc(updated);
      setDocs((current) =>
        current.map((doc) => (doc.id === updated.id ? updated : doc)),
      );
    } finally {
      setChangingLocation(false);
    }
  };

  const handleRemoveUserShare = async (userId: string) => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await deleteDocUserShare(
        token,
        selectedDoc.id,
        userId,
        workspaceSlug,
      );
      setSharingState(updated);
    } finally {
      setShareLoading(false);
    }
  };

  const handleEnableLinkShare = async (
    accessLevel: 'read' | 'edit',
    regenerateToken = false,
  ) => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await upsertDocLinkShare(
        token,
        selectedDoc.id,
        {
          access_level: accessLevel,
          active: true,
          regenerate_token: regenerateToken,
        },
        workspaceSlug,
      );
      setSharingState(updated);
    } finally {
      setShareLoading(false);
    }
  };

  const handleDisableLinkShare = async () => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await deleteDocLinkShare(
        token,
        selectedDoc.id,
        workspaceSlug,
      );
      setSharingState(updated);
    } finally {
      setShareLoading(false);
    }
  };

  const copyShareLink = async () => {
    const tokenValue = sharingState?.link_share?.token;
    if (!tokenValue) return;
    const path = appendDocPageQuery(`/docs/shared/${tokenValue}`, activePageId);
    const url = `${window.location.origin}${path}`;
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
      .filter(
        (user) =>
          !invitedUserIds.has(user.id) &&
          (user.full_name.toLowerCase().includes(query) ||
            user.email.toLowerCase().includes(query)),
      )
      .slice(0, 6);
  }, [inviteQuery, invitedUserIds, shareableUsers]);

  const handleInviteUser = async (userId: string) => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await upsertDocUserShare(
        token,
        selectedDoc.id,
        userId,
        shareAccessLevel,
        workspaceSlug,
      );
      setSharingState(updated);
      setInviteQuery('');
    } finally {
      setShareLoading(false);
    }
  };

  const handleChangeUserAccess = async (
    userId: string,
    level: 'read' | 'edit',
  ) => {
    if (!token || !selectedDoc) return;
    setShareLoading(true);
    try {
      const updated = await upsertDocUserShare(
        token,
        selectedDoc.id,
        userId,
        level,
        workspaceSlug,
      );
      setSharingState(updated);
    } finally {
      setShareLoading(false);
    }
  };

  const handleAttachPmsTask = async (task: PmsTask) => {
    if (!token || !selectedDoc) return;
    setRelatedPmsTaskBusyId(task.id);
    setRelatedPmsTaskState((current) => ({ ...current, error: null }));
    try {
      const response = await attachDocPmsTask(
        token,
        selectedDoc.id,
        task.id,
        workspaceSlug,
      );
      setRelatedPmsTaskState({ error: null, items: response.items });
    } catch (error) {
      setRelatedPmsTaskState({
        error:
          error instanceof Error
            ? error.message
            : t('docs.relatedPms.attachFailed'),
        items: relatedPmsTasks,
      });
      throw error;
    } finally {
      setRelatedPmsTaskBusyId(null);
    }
  };

  const handleDetachPmsTask = async (taskId: string) => {
    if (!token || !selectedDoc) return;
    setRelatedPmsTaskBusyId(taskId);
    setRelatedPmsTaskState((current) => ({ ...current, error: null }));
    try {
      const response = await detachDocPmsTask(
        token,
        selectedDoc.id,
        taskId,
        workspaceSlug,
      );
      setRelatedPmsTaskState({ error: null, items: response.items });
    } catch (error) {
      setRelatedPmsTaskState({
        error:
          error instanceof Error
            ? error.message
            : t('docs.relatedPms.detachFailed'),
        items: relatedPmsTasks,
      });
    } finally {
      setRelatedPmsTaskBusyId(null);
    }
  };

  const dragDescendantsRef = useRef<Set<string> | null>(null);
  const dragPointerYRef = useRef<number>(0);

  const dndSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const handleDragPointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      dragPointerYRef.current = event.clientY;
    },
    [],
  );

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const activeId = String(event.active.id);
      dragDescendantsRef.current = collectDescendantIds(pages, activeId);
      setActiveDragId(activeId);
      setDropIndicator(null);
    },
    [pages, setActiveDragId, setDropIndicator],
  );

  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
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
      const pointerWithinRow =
        pointerY >= rect.top && pointerY <= rect.top + rect.height;
      let zone: DropZone;
      if (pointerWithinRow) {
        zone = resolveDropZone(pointerY, {
          top: rect.top,
          height: rect.height,
        });
      } else {
        // Keyboard / out-of-row fallback: compare over vs active position.
        const activeRect =
          active.rect?.current?.translated ??
          active.rect?.current?.initial ??
          null;
        if (activeRect && rect.top < activeRect.top) {
          zone = 'before';
        } else {
          zone = 'after';
        }
      }
      setDropIndicator((current) =>
        current && current.overId === overId && current.zone === zone
          ? current
          : { overId, zone },
      );
    },
    [setDropIndicator],
  );

  const resetDragState = useCallback(() => {
    setActiveDragId(null);
    setDropIndicator(null);
    dragDescendantsRef.current = null;
  }, [setActiveDragId, setDropIndicator]);

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
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
        setManualExpandedNodes((current) => {
          const next = new Set(current);
          next.add(target.parentId as string);
          return next;
        });
      }
      try {
        const updated = await Promise.all(
          result.patches.map((patch) =>
            updateDocPage(
              token,
              patch.id,
              { parent_id: patch.parent_id, sort_order: patch.sort_order },
              shareToken,
            ),
          ),
        );
        setPages((current) => {
          const byId = new Map(updated.map((page) => [page.id, page]));
          return current.map((page) => byId.get(page.id) ?? page);
        });
      } catch {
        setPages(snapshot);
      }
    },
    [
      dropIndicator,
      expandedNodes,
      pages,
      resetDragState,
      setManualExpandedNodes,
      setPages,
      shareToken,
      token,
    ],
  );

  const editorView = renderDocsEditor({
    activeContentFormat,
    activeDragId,
    activePage,
    activePageAuthorInitials,
    activePageAuthorName,
    activePageUploadFile,
    childCounts,
    contentEditorVersions,
    copiedDocId,
    dndSensors,
    docMenuOpen,
    docMenuRef,
    dropIndicator,
    editorLoading,
    expandedNodes,
    handleAddPage,
    handleBack,
    handleBlockMarkdownExport,
    handleBlockMarkdownImportFile,
    handleCollabChange,
    handleContentTextChange,
    handleContentTextFileUpload,
    handleCopyLink,
    handleDeleteDoc,
    handleDeletePage,
    handleDetachPmsTask,
    handleDragEnd,
    handleDragOver,
    handleDragPointerMove,
    handleDragStart,
    handleDuplicateDoc,
    handleEditorChange,
    handleOpenHtmlPage,
    handleOpenInNewTab,
    handlePageTitleSave,
    handlePrintDoc,
    handleRenameDoc,
    handleToggleFavorite,
    htmlEditPageIds,
    locale,
    openShareModal,
    pages,
    pagesById,
    relatedPmsTaskBusyId,
    relatedPmsTaskError,
    relatedPmsTasks,
    resetDragState,
    resolveFileUrl,
    selectDocPage,
    selectedDoc,
    selectedPageId,
    setDocMenuOpen,
    setHtmlPageEditMode,
    setReadModeOpen,
    setTaskPickerOpen,
    shareToken,
    t,
    timeZone,
    toggleExpand,
    token,
    visibleTree,
    workspaceSlug,
  });

  return renderDocsShell({
    activeCategoryLabel,
    activeSpaceFilterId,
    availableSpaces,
    changingLocation,
    confirmDialog,
    copyDirectLink,
    copyShareLink,
    creating,
    creatingPage,
    docNavigationPathFor,
    docUrlFor,
    docs,
    editorView,
    handleAttachPmsTask,
    handleChangeLocation,
    handleChangeUserAccess,
    handleCreateDoc,
    handleCreatePage,
    handleDeleteDoc,
    handleDisableLinkShare,
    handleEnableLinkShare,
    handleInviteUser,
    handleRemoveUserShare,
    handleRenameDoc,
    handleSearchChange,
    handleToggleFavorite,
    hasActiveRefinement,
    inviteFocused,
    inviteQuery,
    inviteSuggestions,
    isListView,
    linkCopied,
    loadingList,
    locale,
    locationOptions,
    menuOpenId,
    newDocContentFormat,
    newDocLocation,
    newDocTitle,
    newPageContentFormat,
    newPageTitle,
    openCreateModal,
    openDoc,
    pages,
    promptDialog,
    readModeOpen,
    relatedPmsTasks,
    resetDocsFilters,
    resolveFileUrl,
    resolveLocationValueFromTarget,
    searchOpen,
    searchQuery,
    selectDocPage,
    selectedDoc,
    selectedPageId,
    setInviteFocused,
    setInviteQuery,
    setMenuOpenId,
    setNewDocContentFormat,
    setNewDocLocation,
    setNewDocTitle,
    setNewPageContentFormat,
    setNewPageTitle,
    setReadModeOpen,
    setSearchOpen,
    setShareAccessLevel,
    setShowCreateModal,
    setShowCreatePageModal,
    setShowShareModal,
    setSortBy,
    setSortDir,
    setTaskPickerOpen,
    shareAccessLevel,
    shareLinkCopied,
    shareLoading,
    sharingState,
    showCreateModal,
    showCreatePageModal,
    showShareModal,
    sortBy,
    sortDir,
    t,
    taskPickerOpen,
    timeZone,
    total,
    updateDocsSpaceFilterParam,
    workspaceSlug,
  });
};
