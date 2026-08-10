import { describe, expect, it } from 'vitest';

import {
  appendDocPageQuery,
  consumeDocsCreateSearchParam,
  getDocPageIdFromSearchParams,
  getDocsFilterQueryString,
  getExpandedDocPageNodeIds,
  removeLegacyDocsSearchParams,
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
  it('reads and strips the selected page query without touching list filters', () => {
    const params = new URLSearchParams(
      'view=shared&page=child&source_app=pms&collection_id=old',
    );

    expect(getDocPageIdFromSearchParams(params)).toBe('child');
    expect(getDocsFilterQueryString(params)).toBe('view=shared&source_app=pms');
  });

  it('appends the selected page query to paths with existing params', () => {
    expect(appendDocPageQuery('/w/hq/docs/doc-1', 'page 1')).toBe(
      '/w/hq/docs/doc-1?page=page%201',
    );
    expect(appendDocPageQuery('/w/hq/docs/doc-1?view=shared', 'page-1')).toBe(
      '/w/hq/docs/doc-1?view=shared&page=page-1',
    );
    expect(appendDocPageQuery('/w/hq/docs/doc-1#comments', 'page-1')).toBe(
      '/w/hq/docs/doc-1?page=page-1#comments',
    );
  });

  it('updates selected page query state without mutating the caller params', () => {
    const params = new URLSearchParams('view=shared&page=old');

    expect(withDocPageSearchParam(params, 'new').toString()).toBe(
      'view=shared&page=new',
    );
    expect(withDocPageSearchParam(params, null).toString()).toBe('view=shared');
    expect(params.toString()).toBe('view=shared&page=old');
  });

  it('removes legacy docs params only when present', () => {
    expect(removeLegacyDocsSearchParams(new URLSearchParams('view=all'))).toBe(
      null,
    );
    expect(
      removeLegacyDocsSearchParams(
        new URLSearchParams('view=all&doc_type=native'),
      )?.toString(),
    ).toBe('view=all');
    expect(
      removeLegacyDocsSearchParams(
        new URLSearchParams('view=all&collection_id=old'),
      )?.toString(),
    ).toBe('view=all');
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

  it('resets docs filter params while clearing selected page and legacy collection', () => {
    const params = new URLSearchParams(
      'view=all&page=p1&source_app=pms&source_kind=task&collection_id=old&doc_type=native&space_id=space-1',
    );

    expect(resetDocsFilterSearchParams(params).toString()).toBe('view=all');
  });

  it('updates and clears the PMS space filter', () => {
    const params = new URLSearchParams('view=all&page=p1&collection_id=old');

    expect(withDocsSpaceFilterSearchParam(params, 'space-1').toString()).toBe(
      'view=all&space_id=space-1',
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
