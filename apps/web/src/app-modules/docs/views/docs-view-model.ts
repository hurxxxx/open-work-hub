import { formatRelativeTime } from '@/src/platform/time/time-utils';
import {
  resolveDocsContentFormat,
  type DocsContentFormat,
  type DocsHubContentFormat,
  type DocsHubItem,
  type DocsPageItem,
  type DocsPrimaryTarget,
} from '../api/docs-api';
import type { Globe } from 'lucide-react';

const DOCS_VIEW_VALUES = [
  'all',
  'mine',
  'shared',
  'private',
  'meeting_notes',
  'recent',
  'archived',
] as const;

export type DocsViewCategory = (typeof DOCS_VIEW_VALUES)[number];

export const CATEGORY_MAP: Record<string, DocsViewCategory> = {
  'docs-all': 'all',
  'docs-my': 'mine',
  'docs-shared': 'shared',
  'docs-private': 'private',
  'docs-notes': 'meeting_notes',
  'docs-recent': 'recent',
  'docs-archived': 'archived',
};

export const CATEGORY_LABEL_KEYS: Record<string, string> = {
  'docs-all': 'docs.category.all',
  'docs-my': 'docs.category.mine',
  'docs-shared': 'docs.category.shared',
  'docs-private': 'docs.category.private',
  'docs-notes': 'docs.category.meetingNotes',
  'docs-recent': 'docs.category.recent',
  'docs-archived': 'docs.category.archived',
};

export const VIEW_LABEL_KEYS: Record<DocsViewCategory, string> = {
  all: 'docs.category.all',
  mine: 'docs.category.createdByMe',
  shared: 'docs.category.shared',
  private: 'docs.category.private',
  meeting_notes: 'docs.category.meetingNotes',
  recent: 'docs.category.recent',
  archived: 'docs.category.archived',
};

export const DOC_CONTENT_FORMAT_OPTIONS: DocsContentFormat[] = [
  'block',
  'html',
];
export const DOC_TEXT_UPLOAD_MAX_BYTES = 2 * 1024 * 1024;
export const DOCS_HTML_ZOOM_MIN = 0.5;
export const DOCS_HTML_ZOOM_MAX = 2;
export const DOCS_HTML_ZOOM_STEP = 0.1;

export interface LocationOption {
  value: string;
  icon: typeof Globe;
  title: string;
  desc: string;
  disabled?: boolean;
  disabledReason?: string;
}

export type DocsCreateLocationValue =
  | 'workspace'
  | 'private'
  | `space:${string}`;

export interface DocsCreatePrimaryTarget {
  app: string;
  type: string;
  id: string;
  sort_order?: number;
}

export type DocsViewerState = {
  doc: DocsHubItem | null;
  pages: DocsPageItem[];
  selectedPageId: string | null;
  expandedNodes: Set<string>;
  contentEditorVersions: Record<string, number>;
  htmlEditPageIds: Set<string>;
  loading: boolean;
  error: string | null;
};

export interface DocsHtmlRenderState {
  doc: DocsHubItem | null;
  pages: DocsPageItem[];
  loading: boolean;
  error: string | null;
}

export interface DocsReadModePageProjection {
  page: DocsPageItem;
  depth: number;
  format: DocsContentFormat;
}

export interface DocsReadModeProjection {
  flatPages: DocsReadModePageProjection[];
  activeIndex: number;
  activePage: DocsPageItem | null;
  activeFormat: DocsContentFormat;
}

export interface DocsHtmlRenderProjection {
  page: DocsPageItem | null;
  content: string;
  title: string;
  canRender: boolean;
}

export interface DocsPageCollectionSummary {
  page_count: number;
  content_format: DocsHubContentFormat;
}

export interface DocsPageRemovalResult {
  pages: DocsPageItem[];
  removedIds: Set<string>;
  summary: DocsPageCollectionSummary;
}

export interface DocsRefreshSelection {
  pageId: string | null;
  shouldSelect: boolean;
}

type DocsAuthorLike = {
  created_by_name?: string | null;
};

export type DocsViewerAction =
  | { type: 'reset' }
  | { type: 'loadStart' }
  | { type: 'loadSuccess'; doc: DocsHubItem; pages: DocsPageItem[] }
  | { type: 'loadError'; message: string }
  | {
      type: 'refreshPages';
      pages: DocsPageItem[];
      expandedParentId?: string | null;
    }
  | { type: 'selectPage'; pageId: string | null }
  | { type: 'toggleExpanded'; pageId: string }
  | { type: 'setHtmlEditMode'; pageId: string; editing: boolean }
  | { type: 'updatePage'; page: DocsPageItem }
  | {
      type: 'updatePageBlocks';
      pageId: string;
      blocks: Record<string, unknown>[];
    }
  | { type: 'updatePageText'; pageId: string; contentText: string }
  | { type: 'bumpContentEditorVersion'; pageId: string };

export type DocsHtmlRenderAction =
  | { type: 'loading' }
  | { type: 'success'; doc: DocsHubItem; pages: DocsPageItem[] }
  | { type: 'failure'; error: string };

export const DOCS_VIEWER_INITIAL_STATE: DocsViewerState = {
  doc: null,
  pages: [],
  selectedPageId: null,
  expandedNodes: new Set(),
  contentEditorVersions: {},
  htmlEditPageIds: new Set(),
  loading: false,
  error: null,
};

export const INITIAL_DOCS_HTML_RENDER_STATE: DocsHtmlRenderState = {
  doc: null,
  pages: [],
  loading: true,
  error: null,
};

export function docsViewerReducer(
  state: DocsViewerState,
  action: DocsViewerAction,
): DocsViewerState {
  switch (action.type) {
    case 'reset':
      return DOCS_VIEWER_INITIAL_STATE;
    case 'loadStart':
      return { ...state, loading: true, error: null };
    case 'loadSuccess':
      return {
        ...state,
        doc: action.doc,
        pages: action.pages,
        selectedPageId: docsPageExists(action.pages, state.selectedPageId)
          ? state.selectedPageId
          : (action.pages[0]?.id ?? null),
        expandedNodes: collectDocsParentPageIds(action.pages),
        contentEditorVersions: {},
        htmlEditPageIds: new Set(),
        loading: false,
        error: null,
      };
    case 'loadError':
      return { ...state, error: action.message, loading: false };
    case 'refreshPages': {
      const expandedNodes = new Set(state.expandedNodes);
      if (action.expandedParentId) expandedNodes.add(action.expandedParentId);
      const nextDocSummary = summarizeDocsPageCollection(action.pages);
      return {
        ...state,
        pages: action.pages,
        doc: state.doc ? { ...state.doc, ...nextDocSummary } : state.doc,
        selectedPageId: docsPageExists(action.pages, state.selectedPageId)
          ? state.selectedPageId
          : (action.pages[0]?.id ?? null),
        expandedNodes,
      };
    }
    case 'selectPage':
      return { ...state, selectedPageId: action.pageId };
    case 'toggleExpanded': {
      const expandedNodes = new Set(state.expandedNodes);
      if (expandedNodes.has(action.pageId)) expandedNodes.delete(action.pageId);
      else expandedNodes.add(action.pageId);
      return { ...state, expandedNodes };
    }
    case 'setHtmlEditMode': {
      const htmlEditPageIds = new Set(state.htmlEditPageIds);
      if (action.editing) htmlEditPageIds.add(action.pageId);
      else htmlEditPageIds.delete(action.pageId);
      return { ...state, htmlEditPageIds };
    }
    case 'updatePage':
      return {
        ...state,
        pages: applyUpdatedDocsPage(state.pages, action.page),
      };
    case 'updatePageBlocks':
      return {
        ...state,
        pages: updateDocsPageContentBlocks(
          state.pages,
          action.pageId,
          action.blocks,
        ),
      };
    case 'updatePageText':
      return {
        ...state,
        pages: updateDocsPageContentText(
          state.pages,
          action.pageId,
          action.contentText,
        ),
      };
    case 'bumpContentEditorVersion':
      return {
        ...state,
        contentEditorVersions: bumpDocsContentEditorVersion(
          state.contentEditorVersions,
          action.pageId,
        ),
      };
  }
}

export function docsHtmlRenderReducer(
  state: DocsHtmlRenderState,
  action: DocsHtmlRenderAction,
): DocsHtmlRenderState {
  switch (action.type) {
    case 'loading':
      return {
        ...state,
        loading: true,
        error: null,
      };
    case 'success':
      return {
        doc: action.doc,
        pages: action.pages,
        loading: false,
        error: null,
      };
    case 'failure':
      return {
        ...state,
        loading: false,
        error: action.error,
      };
  }
}

export function buildDocsHtmlRenderProjection(args: {
  doc: DocsHubItem | null;
  pages: DocsPageItem[];
  pageId: string | null | undefined;
  fallbackTitle: string;
}): DocsHtmlRenderProjection {
  const page = args.pages.find((item) => item.id === args.pageId) ?? null;
  const content = page?.content_text?.trim() ?? '';
  return {
    page,
    content,
    title: page?.title || args.doc?.title || args.fallbackTitle,
    canRender: Boolean(args.doc && page?.content_format === 'html' && content),
  };
}

export function buildDocsReadModeProjection(args: {
  pages: DocsPageItem[];
  selectedPageId: string | null;
}): DocsReadModeProjection {
  const flatPages = flattenDocsReadModePages(args.pages);
  const selectedIndex = flatPages.findIndex(
    (item) => item.page.id === args.selectedPageId,
  );
  const activeIndex = Math.max(0, selectedIndex);
  const activePage = flatPages[activeIndex]?.page ?? flatPages[0]?.page ?? null;
  return {
    flatPages,
    activeIndex,
    activePage,
    activeFormat: resolveDocsContentFormat(activePage),
  };
}

export function flattenDocsReadModePages(
  pages: DocsPageItem[],
): DocsReadModePageProjection[] {
  const byParent = new Map<string | null, DocsPageItem[]>();
  for (const page of pages) {
    const key = page.parent_id ?? null;
    const siblings = byParent.get(key) ?? [];
    siblings.push(page);
    byParent.set(key, siblings);
  }
  for (const siblings of byParent.values()) {
    siblings.sort(
      (a, b) => a.sort_order - b.sort_order || a.title.localeCompare(b.title),
    );
  }

  const result: DocsReadModePageProjection[] = [];
  const visit = (parentId: string | null, depth: number) => {
    for (const page of byParent.get(parentId) ?? []) {
      result.push({
        page,
        depth,
        format: resolveDocsContentFormat(page),
      });
      visit(page.id, depth + 1);
    }
  };
  visit(null, 0);
  return result;
}

export function formatDocsReadPagePosition(
  index: number,
  total: number,
): string {
  return `${index + 1} / ${total}`;
}

export function clampDocsHtmlZoom(value: number): number {
  const bounded = Math.min(
    DOCS_HTML_ZOOM_MAX,
    Math.max(DOCS_HTML_ZOOM_MIN, value),
  );
  return Math.round(bounded * 100) / 100;
}

export function replaceDocsPage(
  pages: DocsPageItem[],
  pageId: string,
  update: (page: DocsPageItem) => DocsPageItem,
): DocsPageItem[] {
  return pages.map((page) => (page.id === pageId ? update(page) : page));
}

export function applyUpdatedDocsPage(
  pages: DocsPageItem[],
  updatedPage: DocsPageItem,
): DocsPageItem[] {
  return replaceDocsPage(pages, updatedPage.id, () => updatedPage);
}

export function updateDocsPageContentBlocks(
  pages: DocsPageItem[],
  pageId: string,
  blocks: Record<string, unknown>[],
): DocsPageItem[] {
  return replaceDocsPage(pages, pageId, (page) => ({
    ...page,
    content_blocks: blocks,
  }));
}

export function updateDocsPageContentText(
  pages: DocsPageItem[],
  pageId: string,
  contentText: string,
): DocsPageItem[] {
  return replaceDocsPage(pages, pageId, (page) => ({
    ...page,
    content_text: contentText,
  }));
}

export function bumpDocsContentEditorVersion(
  versions: Record<string, number>,
  pageId: string,
): Record<string, number> {
  return {
    ...versions,
    [pageId]: (versions[pageId] ?? 0) + 1,
  };
}

export function isDocsTextUploadTooLarge(
  fileSize: number,
  maxBytes = DOC_TEXT_UPLOAD_MAX_BYTES,
): boolean {
  return fileSize > maxBytes;
}

export function buildDocsPagesById(
  pages: DocsPageItem[],
): Map<string, DocsPageItem> {
  const map = new Map<string, DocsPageItem>();
  for (const page of pages) map.set(page.id, page);
  return map;
}

export function countDocsPageChildren(
  pages: DocsPageItem[],
): Map<string, number> {
  const counts = new Map<string, number>();
  for (const page of pages) {
    if (page.parent_id)
      counts.set(page.parent_id, (counts.get(page.parent_id) ?? 0) + 1);
  }
  return counts;
}

export function collectDocsParentPageIds(pages: DocsPageItem[]): Set<string> {
  return new Set(
    pages
      .map((page) => page.parent_id)
      .filter((parentId): parentId is string => Boolean(parentId)),
  );
}

export function docsPageExists(
  pages: DocsPageItem[],
  pageId: string | null,
): boolean {
  return Boolean(pageId && pages.some((page) => page.id === pageId));
}

export function resolveDocsPageSelection(
  pages: readonly DocsPageItem[],
  requestedPageId: string | null | undefined,
): string | null {
  if (requestedPageId && pages.some((page) => page.id === requestedPageId)) {
    return requestedPageId;
  }
  return pages[0]?.id ?? null;
}

export function resolveDocsRefreshSelection({
  currentPageId,
  pages,
  requestedPageId,
}: {
  currentPageId: string | null;
  pages: readonly DocsPageItem[];
  requestedPageId: string | null | undefined;
}): DocsRefreshSelection {
  if (currentPageId && pages.some((page) => page.id === currentPageId)) {
    return {
      pageId: currentPageId,
      shouldSelect: false,
    };
  }
  return {
    pageId: resolveDocsPageSelection(pages, requestedPageId),
    shouldSelect: true,
  };
}

export function resolveDefaultDocsCreateLocation(
  activeCategory: DocsViewCategory,
): DocsCreateLocationValue {
  if (activeCategory === 'private') return 'private';
  return 'workspace';
}

export function resolveDocsCreatePrimaryTarget(
  locationValue: string,
  currentWorkspaceId: string | null | undefined,
): DocsCreatePrimaryTarget | null {
  if (locationValue === 'private') return null;
  if (locationValue === 'workspace') {
    return currentWorkspaceId
      ? { app: 'docs', type: 'workspace_sidebar', id: currentWorkspaceId }
      : null;
  }
  if (locationValue.startsWith('space:')) {
    const spaceId = locationValue.slice('space:'.length);
    return spaceId ? { app: 'pms', type: 'space', id: spaceId } : null;
  }
  return null;
}

export function resolveDocsCreateLocationValue(
  target:
    | Pick<DocsPrimaryTarget, 'app' | 'type' | 'id'>
    | null
    | undefined,
): DocsCreateLocationValue {
  if (!target) return 'private';
  if (target.app === 'docs' && target.type === 'workspace_sidebar') {
    return 'workspace';
  }
  if (target.app === 'pms' && target.type === 'space') {
    return `space:${target.id}`;
  }
  return 'private';
}

export function isDocsViewCategory(
  value: string | null | undefined,
): value is DocsViewCategory {
  return DOCS_VIEW_VALUES.includes(value as DocsViewCategory);
}

export function summarizeDocsPageCollection(
  pages: DocsPageItem[],
): DocsPageCollectionSummary {
  return {
    page_count: pages.filter((item) => item.trashed_at === null).length,
    content_format: summarizePageContentFormats(pages),
  };
}

export function summarizePageContentFormats(
  pages: DocsPageItem[],
): DocsHubContentFormat {
  const formats = new Set(
    pages
      .filter((page) => page.trashed_at === null)
      .map((page) => resolveDocsContentFormat(page)),
  );
  if (formats.size === 0) return 'block';
  if (formats.size === 1) return formats.has('html') ? 'html' : 'block';
  return 'mixed';
}

export function resolveDocsPageAuthorName(
  page: DocsAuthorLike | null | undefined,
  doc: DocsAuthorLike | null | undefined,
): string {
  return page?.created_by_name?.trim() || doc?.created_by_name?.trim() || '';
}

export function docsAuthorInitials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => Array.from(part)[0] ?? '')
    .join('')
    .slice(0, 2);
}

export function removeDocsPageSubtree(
  pages: DocsPageItem[],
  pageId: string,
): DocsPageRemovalResult {
  const removedIds = new Set<string>([pageId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const candidate of pages) {
      if (
        candidate.parent_id &&
        removedIds.has(candidate.parent_id) &&
        !removedIds.has(candidate.id)
      ) {
        removedIds.add(candidate.id);
        changed = true;
      }
    }
  }
  const nextPages = pages.filter((item) => !removedIds.has(item.id));
  return {
    pages: nextPages,
    removedIds,
    summary: summarizeDocsPageCollection(nextPages),
  };
}

export function timeAgo(
  dateStr: string,
  timeZone: string,
  locale: string,
): string {
  return formatRelativeTime(dateStr, { locale, timeZone });
}

export function sharingLabel(
  item: DocsHubItem,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (item.source_type !== 'native_doc') {
    return item.source_app.toUpperCase();
  }
  if (item.sharing_summary?.visibility === 'private') {
    return t('apps:docs.category.private');
  }
  const parts = [];
  if ((item.sharing_summary?.user_share_count ?? 0) > 0) {
    parts.push(
      t('apps:docs.share.userCount', {
        count: item.sharing_summary?.user_share_count ?? 0,
      }),
    );
  }
  if (item.sharing_summary?.link_active) {
    parts.push(
      t('apps:docs.share.linkAccess', {
        access: t(
          `apps:docs.share.access.${item.sharing_summary.link_access_level}`,
        ),
      }),
    );
  }
  return parts.join(' · ') || t('apps:docs.category.shared');
}
