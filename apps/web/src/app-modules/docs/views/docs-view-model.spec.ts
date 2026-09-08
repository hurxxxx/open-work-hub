import { describe, expect, it } from 'vitest';

import type { DocsHubItem, DocsPageItem } from '../api/docs-api';
import {
  DOCS_HTML_ZOOM_MAX,
  DOCS_HTML_ZOOM_MIN,
  DOCS_HTML_ZOOM_STEP,
  INITIAL_DOCS_HTML_RENDER_STATE,
  DOCS_VIEWER_INITIAL_STATE,
  applyUpdatedDocsPage,
  buildDocsHtmlRenderProjection,
  buildDocsPagesById,
  buildDocsReadModeProjection,
  bumpDocsContentEditorVersion,
  clampDocsHtmlZoom,
  collectDocsParentPageIds,
  countDocsPageChildren,
  docsAuthorInitials,
  DOC_TEXT_UPLOAD_MAX_BYTES,
  docsHtmlRenderReducer,
  docsPageExists,
  docsViewerReducer,
  flattenDocsReadModePages,
  formatDocsReadPagePosition,
  isDocsTextUploadTooLarge,
  removeDocsPageSubtree,
  resolveDefaultDocsCreateLocation,
  resolveDocsCreateLocationValue,
  resolveDocsPageSelection,
  resolveDocsCreatePrimaryTarget,
  resolveDocsPageAuthorName,
  resolveDocsRefreshSelection,
  summarizeDocsPageCollection,
  updateDocsPageContentBlocks,
  updateDocsPageContentText,
} from './docs-view-model';

function page(overrides: Partial<DocsPageItem> = {}): DocsPageItem {
  return {
    id: 'page-1',
    doc_id: 'doc-1',
    title: 'Page',
    parent_id: null,
    sort_order: 1000,
    depth: 0,
    content_format: 'block',
    content_blocks: [],
    content_text: null,
    can_edit: true,
    trashed_at: null,
    created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
    ...overrides,
  } as DocsPageItem;
}

function doc(overrides: Partial<DocsHubItem> = {}): DocsHubItem {
  return {
    id: 'doc-1',
    title: 'Doc',
    page_count: 0,
    content_format: 'block',
    can_edit: true,
    ...overrides,
  } as DocsHubItem;
}

describe('docs view model', () => {
  it('defaults standalone creation to personal ownership', () => {
    expect(resolveDefaultDocsCreateLocation('all')).toBe('private');
    expect(resolveDefaultDocsCreateLocation('private')).toBe('private');
  });
  it('uses app-owned targets only for explicit business placement', () => {
    expect(resolveDocsCreatePrimaryTarget('private')).toBeNull();
    expect(resolveDocsCreatePrimaryTarget('company')).toBeNull();
    expect(resolveDocsCreatePrimaryTarget('space:space-1')).toEqual({
      app: 'pms',
      type: 'space',
      id: 'space-1',
    });
    expect(resolveDocsCreatePrimaryTarget('unknown')).toBeNull();
  });
  it('maps app-owned targets back to placement values', () => {
    expect(resolveDocsCreateLocationValue(null)).toBe('private');
    expect(
      resolveDocsCreateLocationValue({
        app: 'pms',
        type: 'space',
        id: 'space-1',
      }),
    ).toBe('space:space-1');
    expect(
      resolveDocsCreateLocationValue({
        app: 'unknown',
        type: 'target',
        id: 'target-1',
      }),
    ).toBe('private');
  });

  it('uses the active page author before the document author', () => {
    expect(
      resolveDocsPageAuthorName(
        page({ created_by_name: 'Page Author' }),
        doc({ created_by_name: 'Doc Owner' }),
      ),
    ).toBe('Page Author');
    expect(
      resolveDocsPageAuthorName(
        page({ created_by_name: '   ' }),
        doc({ created_by_name: 'Doc Owner' }),
      ),
    ).toBe('Doc Owner');
    expect(docsAuthorInitials('Page Author')).toBe('PA');
  });

  it('updates page block content without changing sibling pages', () => {
    const first = page({ id: 'page-1', title: 'First' });
    const second = page({ id: 'page-2', title: 'Second' });
    const blocks = [{ content: 'Updated block' }];

    const updated = updateDocsPageContentBlocks(
      [first, second],
      first.id,
      blocks,
    );

    expect(updated[0]).toEqual({ ...first, content_blocks: blocks });
    expect(updated[1]).toBe(second);
  });

  it('updates page text content and applies server-updated pages', () => {
    const first = page({ id: 'page-1', content_text: 'old' });
    const second = page({ id: 'page-2', content_text: 'sibling' });
    const locallyUpdated = updateDocsPageContentText(
      [first, second],
      first.id,
      'draft',
    );
    const serverUpdated = page({
      ...first,
      content_text: 'saved',
      updated_at: '2026-05-30T00:01:00Z',
    });

    expect(locallyUpdated[0]).toEqual({ ...first, content_text: 'draft' });
    expect(applyUpdatedDocsPage(locallyUpdated, serverUpdated)).toEqual([
      serverUpdated,
      second,
    ]);
  });

  it('bumps editor versions independently per page', () => {
    expect(bumpDocsContentEditorVersion({}, 'page-1')).toEqual({ 'page-1': 1 });
    expect(
      bumpDocsContentEditorVersion({ 'page-1': 2, 'page-2': 4 }, 'page-1'),
    ).toEqual({ 'page-1': 3, 'page-2': 4 });
  });

  it('keeps upload size checks as model policy', () => {
    expect(isDocsTextUploadTooLarge(DOC_TEXT_UPLOAD_MAX_BYTES)).toBe(false);
    expect(isDocsTextUploadTooLarge(DOC_TEXT_UPLOAD_MAX_BYTES + 1)).toBe(true);
  });

  it('builds page lookups without cloning pages', () => {
    const first = page({ id: 'page-1' });
    const second = page({ id: 'page-2' });

    const byId = buildDocsPagesById([first, second]);

    expect(byId.get(first.id)).toBe(first);
    expect(byId.get(second.id)).toBe(second);
  });

  it('counts direct page children only', () => {
    const root = page({ id: 'root' });
    const child = page({ id: 'child', parent_id: root.id });
    const sibling = page({ id: 'sibling', parent_id: root.id });
    const grandchild = page({ id: 'grandchild', parent_id: child.id });

    const counts = countDocsPageChildren([root, child, sibling, grandchild]);

    expect(counts.get(root.id)).toBe(2);
    expect(counts.get(child.id)).toBe(1);
    expect(counts.get(sibling.id)).toBeUndefined();
  });

  it('checks page existence for nullable selected ids', () => {
    const pages = [page({ id: 'page-1' })];

    expect(docsPageExists(pages, 'page-1')).toBe(true);
    expect(docsPageExists(pages, 'missing')).toBe(false);
    expect(docsPageExists(pages, null)).toBe(false);
    expect(resolveDocsPageSelection(pages, 'page-1')).toBe('page-1');
    expect(resolveDocsPageSelection(pages, 'missing')).toBe('page-1');
  });

  it('collects parent page ids without including root nulls', () => {
    const root = page({ id: 'root', parent_id: null });
    const child = page({ id: 'child', parent_id: root.id });
    const grandchild = page({ id: 'grandchild', parent_id: child.id });

    expect(collectDocsParentPageIds([root, child, grandchild])).toEqual(
      new Set([root.id, child.id]),
    );
  });

  it('loads viewer pages while preserving valid selection and resetting edit state', () => {
    const root = page({ id: 'root' });
    const child = page({ id: 'child', parent_id: root.id });
    const loaded = docsViewerReducer(
      {
        ...DOCS_VIEWER_INITIAL_STATE,
        selectedPageId: child.id,
        contentEditorVersions: { child: 3 },
        htmlEditPageIds: new Set([child.id]),
        loading: true,
      },
      { type: 'loadSuccess', doc: doc(), pages: [root, child] },
    );

    expect(loaded.selectedPageId).toBe(child.id);
    expect(loaded.expandedNodes).toEqual(new Set([root.id]));
    expect(loaded.contentEditorVersions).toEqual({});
    expect(loaded.htmlEditPageIds).toEqual(new Set());
    expect(loaded.loading).toBe(false);

    expect(
      docsViewerReducer(
        { ...loaded, selectedPageId: 'missing' },
        { type: 'loadSuccess', doc: doc(), pages: [root, child] },
      ).selectedPageId,
    ).toBe(root.id);
  });

  it('refreshes viewer pages, doc summary, selected page, and expanded parents', () => {
    const root = page({ id: 'root', content_format: 'block' });
    const child = page({
      id: 'child',
      parent_id: root.id,
      content_format: 'html',
    });
    const trashed = page({ id: 'trashed', trashed_at: '2026-05-30T00:00:00Z' });
    const refreshed = docsViewerReducer(
      {
        ...DOCS_VIEWER_INITIAL_STATE,
        doc: doc({ page_count: 99, content_format: 'block' }),
        selectedPageId: 'missing',
        expandedNodes: new Set(['kept-open']),
      },
      {
        type: 'refreshPages',
        pages: [root, child, trashed],
        expandedParentId: root.id,
      },
    );

    expect(refreshed.doc).toMatchObject({
      page_count: 2,
      content_format: 'mixed',
    });
    expect(refreshed.selectedPageId).toBe(root.id);
    expect(refreshed.expandedNodes).toEqual(new Set(['kept-open', root.id]));
  });

  it('summarizes page collections and resolves refresh selection', () => {
    const root = page({ id: 'root', content_format: 'block' });
    const child = page({ id: 'child', content_format: 'html' });
    const trashed = page({ id: 'trashed', trashed_at: '2026-05-30T00:00:00Z' });

    expect(summarizeDocsPageCollection([root, child, trashed])).toEqual({
      page_count: 2,
      content_format: 'mixed',
    });
    expect(
      resolveDocsRefreshSelection({
        currentPageId: 'child',
        pages: [root, child],
        requestedPageId: 'root',
      }),
    ).toEqual({ pageId: 'child', shouldSelect: false });
    expect(
      resolveDocsRefreshSelection({
        currentPageId: 'missing',
        pages: [root, child],
        requestedPageId: 'child',
      }),
    ).toEqual({ pageId: 'child', shouldSelect: true });
  });

  it('removes a page subtree and reports the updated collection summary', () => {
    const root = page({ id: 'root' });
    const child = page({ id: 'child', parent_id: root.id });
    const grandchild = page({ id: 'grandchild', parent_id: child.id });
    const sibling = page({ id: 'sibling', content_format: 'html' });

    const result = removeDocsPageSubtree(
      [root, child, grandchild, sibling],
      root.id,
    );

    expect(result.pages).toEqual([sibling]);
    expect(result.removedIds).toEqual(new Set(['root', 'child', 'grandchild']));
    expect(result.summary).toEqual({
      page_count: 1,
      content_format: 'html',
    });
  });

  it('clones viewer Sets when toggling expansion and html edit mode', () => {
    const expandedNodes = new Set(['open']);
    const htmlEditPageIds = new Set(['editing']);
    const state = {
      ...DOCS_VIEWER_INITIAL_STATE,
      expandedNodes,
      htmlEditPageIds,
    };

    const expanded = docsViewerReducer(state, {
      type: 'toggleExpanded',
      pageId: 'other',
    });
    const collapsed = docsViewerReducer(state, {
      type: 'toggleExpanded',
      pageId: 'open',
    });
    const editing = docsViewerReducer(state, {
      type: 'setHtmlEditMode',
      pageId: 'other',
      editing: true,
    });

    expect(expanded.expandedNodes).toEqual(new Set(['open', 'other']));
    expect(collapsed.expandedNodes).toEqual(new Set());
    expect(editing.htmlEditPageIds).toEqual(new Set(['editing', 'other']));
    expect(expanded.expandedNodes).not.toBe(expandedNodes);
    expect(editing.htmlEditPageIds).not.toBe(htmlEditPageIds);
    expect(expandedNodes).toEqual(new Set(['open']));
    expect(htmlEditPageIds).toEqual(new Set(['editing']));
  });

  it('updates viewer page content and editor versions through reducer actions', () => {
    const first = page({ id: 'page-1', title: 'First', content_text: 'old' });
    const second = page({ id: 'page-2', title: 'Second' });
    const state = {
      ...DOCS_VIEWER_INITIAL_STATE,
      pages: [first, second],
    };
    const blocks = [{ type: 'paragraph', content: 'new' }];

    const withBlocks = docsViewerReducer(state, {
      type: 'updatePageBlocks',
      pageId: first.id,
      blocks,
    });
    const withText = docsViewerReducer(state, {
      type: 'updatePageText',
      pageId: first.id,
      contentText: 'draft',
    });
    const withVersion = docsViewerReducer(state, {
      type: 'bumpContentEditorVersion',
      pageId: first.id,
    });

    expect(withBlocks.pages[0]).toEqual({ ...first, content_blocks: blocks });
    expect(withText.pages[0]).toEqual({ ...first, content_text: 'draft' });
    expect(withVersion.contentEditorVersions).toEqual({ [first.id]: 1 });
    expect(withBlocks.pages[1]).toBe(second);
  });

  it('projects read-mode pages depth-first with sibling sorting', () => {
    const rootB = page({ id: 'root-b', title: 'B', sort_order: 20 });
    const rootA = page({ id: 'root-a', title: 'A', sort_order: 10 });
    const childB = page({
      id: 'child-b',
      parent_id: rootA.id,
      title: 'B',
      sort_order: 1,
    });
    const childA = page({
      id: 'child-a',
      parent_id: rootA.id,
      title: 'A',
      sort_order: 1,
    });
    const grandchild = page({
      id: 'grandchild',
      parent_id: childA.id,
      title: 'Grandchild',
      sort_order: 1,
      content_format: 'html',
    });

    expect(
      flattenDocsReadModePages([rootB, childB, grandchild, rootA, childA]).map(
        ({ page: item, depth, format }) => [item.id, depth, format],
      ),
    ).toEqual([
      ['root-a', 0, 'block'],
      ['child-a', 1, 'block'],
      ['grandchild', 2, 'html'],
      ['child-b', 1, 'block'],
      ['root-b', 0, 'block'],
    ]);
  });

  it('projects read-mode active page fallback and format', () => {
    const blockPage = page({
      id: 'block-page',
      content_format: 'block',
      sort_order: 10,
    });
    const htmlPage = page({
      id: 'html-page',
      content_format: 'html',
      sort_order: 20,
    });

    expect(
      buildDocsReadModeProjection({
        pages: [blockPage, htmlPage],
        selectedPageId: htmlPage.id,
      }),
    ).toMatchObject({
      activeIndex: 1,
      activePage: htmlPage,
      activeFormat: 'html',
    });

    expect(
      buildDocsReadModeProjection({
        pages: [blockPage, htmlPage],
        selectedPageId: 'missing',
      }),
    ).toMatchObject({
      activeIndex: 0,
      activePage: blockPage,
      activeFormat: 'block',
    });

    expect(
      buildDocsReadModeProjection({ pages: [], selectedPageId: null }),
    ).toMatchObject({
      activeIndex: 0,
      activePage: null,
      activeFormat: 'block',
    });
  });

  it('formats read-mode page position and clamps html zoom', () => {
    expect(formatDocsReadPagePosition(1, 5)).toBe('2 / 5');
    expect(clampDocsHtmlZoom(DOCS_HTML_ZOOM_MIN - DOCS_HTML_ZOOM_STEP)).toBe(
      DOCS_HTML_ZOOM_MIN,
    );
    expect(clampDocsHtmlZoom(DOCS_HTML_ZOOM_MAX + DOCS_HTML_ZOOM_STEP)).toBe(
      DOCS_HTML_ZOOM_MAX,
    );
    expect(clampDocsHtmlZoom(1.234)).toBe(1.23);
  });

  it('tracks docs HTML render loading state', () => {
    const loadedDoc = doc({ title: 'Loaded doc' });
    const loadedPage = page({ id: 'html-page', content_format: 'html' });
    const loaded = docsHtmlRenderReducer(INITIAL_DOCS_HTML_RENDER_STATE, {
      type: 'success',
      doc: loadedDoc,
      pages: [loadedPage],
    });

    expect(loaded).toEqual({
      doc: loadedDoc,
      pages: [loadedPage],
      loading: false,
      error: null,
    });
    expect(docsHtmlRenderReducer(loaded, { type: 'loading' })).toMatchObject({
      loading: true,
      error: null,
    });
    expect(
      docsHtmlRenderReducer(loaded, {
        type: 'failure',
        error: 'Load failed',
      }),
    ).toMatchObject({ loading: false, error: 'Load failed' });
  });

  it('projects docs HTML render availability, content, and title fallback', () => {
    const loadedDoc = doc({ title: 'Doc title' });
    const htmlPage = page({
      id: 'html-page',
      title: '',
      content_format: 'html',
      content_text: '  <h1>Report</h1>  ',
    });
    const blockPage = page({
      id: 'block-page',
      title: 'Block page',
      content_format: 'block',
      content_text: '<h1>Not renderable</h1>',
    });

    expect(
      buildDocsHtmlRenderProjection({
        doc: loadedDoc,
        pages: [htmlPage, blockPage],
        pageId: htmlPage.id,
        fallbackTitle: 'Fallback',
      }),
    ).toEqual({
      page: htmlPage,
      content: '<h1>Report</h1>',
      title: 'Doc title',
      canRender: true,
    });

    expect(
      buildDocsHtmlRenderProjection({
        doc: loadedDoc,
        pages: [htmlPage, blockPage],
        pageId: blockPage.id,
        fallbackTitle: 'Fallback',
      }).canRender,
    ).toBe(false);

    expect(
      buildDocsHtmlRenderProjection({
        doc: null,
        pages: [],
        pageId: 'missing',
        fallbackTitle: 'Fallback',
      }),
    ).toEqual({
      page: null,
      content: '',
      title: 'Fallback',
      canRender: false,
    });
  });
});
