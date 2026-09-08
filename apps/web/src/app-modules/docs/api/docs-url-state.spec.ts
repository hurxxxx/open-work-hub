import { describe, expect, it } from 'vitest';

import {
  appendDocPageQuery,
  consumeDocsCreateSearchParam,
  getDocPageIdFromSearchParams,
  getDocsFilterQueryString,
  getExpandedDocPageNodeIds,
  resetDocsFilterSearchParams,
  resolveInitialDocPageId,
  withDocPageSearchParam,
  withDocsSpaceFilterSearchParam,
} from './docs-url-state';

const pages = [
  { id: 'root', parent_id: null },
  { id: 'child', parent_id: 'root' },
  { id: 'grandchild', parent_id: 'child' },
];

describe('docs URL state', () => {
  it('reads and strips only the selected page query without touching list filters', () => {
    const params = new URLSearchParams(
      'view=shared&page=child&source_app=pms&collection_id=old',
    );

    expect(getDocPageIdFromSearchParams(params)).toBe('child');
    expect(getDocsFilterQueryString(params)).toBe(
      'view=shared&source_app=pms&collection_id=old',
    );
  });

  it('appends the selected page query to paths with existing params', () => {
    expect(appendDocPageQuery('/apps/docs/documents/doc-1', 'page 1')).toBe(
      '/apps/docs/documents/doc-1?page=page%201',
    );
    expect(
      appendDocPageQuery('/apps/docs/documents/doc-1?view=shared', 'page-1'),
    ).toBe('/apps/docs/documents/doc-1?view=shared&page=page-1');
    expect(
      appendDocPageQuery('/apps/docs/documents/doc-1#comments', 'page-1'),
    ).toBe('/apps/docs/documents/doc-1?page=page-1#comments');
  });

  it('updates selected page query state without mutating the caller params', () => {
    const params = new URLSearchParams('view=shared&page=old');

    expect(withDocPageSearchParam(params, 'new').toString()).toBe(
      'view=shared&page=new',
    );
    expect(withDocPageSearchParam(params, null).toString()).toBe('view=shared');
    expect(params.toString()).toBe('view=shared&page=old');
  });

  it('consumes create modal query state once', () => {
    expect(
      consumeDocsCreateSearchParam(new URLSearchParams('view=all')),
    ).toEqual({
      shouldOpen: false,
      searchParams: null,
    });

    const consumed = consumeDocsCreateSearchParam(
      new URLSearchParams('view=all&create=1'),
    );
    expect(consumed.shouldOpen).toBe(true);
    expect(consumed.searchParams?.toString()).toBe('view=all');
  });

  it('resets only current docs filter params', () => {
    const params = new URLSearchParams(
      'view=all&page=p1&source_app=pms&source_kind=task&collection_id=old&doc_type=native&space_id=space-1',
    );

    expect(resetDocsFilterSearchParams(params).toString()).toBe(
      'view=all&collection_id=old&doc_type=native',
    );
  });

  it('updates and clears the PMS space filter', () => {
    const params = new URLSearchParams('view=all&page=p1&collection_id=old');

    expect(withDocsSpaceFilterSearchParam(params, 'space-1').toString()).toBe(
      'view=all&collection_id=old&space_id=space-1',
    );
    expect(
      withDocsSpaceFilterSearchParam(
        new URLSearchParams('view=all&space_id=space-1'),
        '',
      ).toString(),
    ).toBe('view=all');
  });

  it('uses the requested page only when it belongs to the loaded document', () => {
    expect(resolveInitialDocPageId(pages, 'child')).toBe('child');
    expect(resolveInitialDocPageId(pages, 'missing')).toBe('root');
  });

  it('expands the selected page ancestor chain for direct links', () => {
    expect(Array.from(getExpandedDocPageNodeIds(pages, 'grandchild'))).toEqual([
      'root',
      'child',
    ]);
  });
});
