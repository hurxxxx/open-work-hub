import { describe, expect, it } from 'vitest';

import type { DocsHubItem } from './docs-api';
import {
  DOCS_HUB_PICKER_REMOTE_SEARCH_DELAY_MS,
  INITIAL_DOCS_HUB_PICKER_STATE,
  buildDocsHubPickerSelection,
  buildDocsHubPickerParams,
  docsHubPickerReducer,
  getDocsHubPickerDelayMs,
  projectDocsHubPickerItems,
} from './docs-hub-picker-model';

function hubItem(id: string, title: string): DocsHubItem {
  return {
    id,
    title,
    source_app: 'docs',
    source_kind: 'manual',
  } as DocsHubItem;
}

describe('docs hub picker model', () => {
  it('tracks load, success, failure, and reset transitions', () => {
    const state = {
      ...INITIAL_DOCS_HUB_PICKER_STATE,
      query: 'spec',
      submittingId: 'doc-1',
      error: 'Old error',
    };

    expect(
      docsHubPickerReducer(state, { type: 'load', resetQuery: true }),
    ).toEqual({
      ...INITIAL_DOCS_HUB_PICKER_STATE,
      loading: true,
    });

    const loadedItems = [hubItem('doc-1', 'Spec')];
    expect(
      docsHubPickerReducer(INITIAL_DOCS_HUB_PICKER_STATE, {
        type: 'loaded',
        items: loadedItems,
      }),
    ).toMatchObject({ items: loadedItems, loading: false });

    expect(
      docsHubPickerReducer(state, { type: 'failed', message: 'Failed' }),
    ).toMatchObject({ items: [], loading: false, error: 'Failed' });

    expect(docsHubPickerReducer(state, { type: 'reset' })).toBe(
      INITIAL_DOCS_HUB_PICKER_STATE,
    );
  });

  it('tracks query and submit lifecycle', () => {
    const queried = docsHubPickerReducer(INITIAL_DOCS_HUB_PICKER_STATE, {
      type: 'query',
      value: 'manual',
    });
    const submitting = docsHubPickerReducer(queried, {
      type: 'submit',
      docId: 'doc-1',
    });

    expect(queried.query).toBe('manual');
    expect(submitting).toMatchObject({ submittingId: 'doc-1', error: null });
    expect(
      docsHubPickerReducer(submitting, {
        type: 'submit-failed',
        message: 'Attach failed',
      }),
    ).toMatchObject({ submittingId: null, error: 'Attach failed' });
    expect(
      docsHubPickerReducer(submitting, { type: 'submit-finished' }),
    ).toMatchObject({ submittingId: null });
  });

  it('projects local search case-insensitively after exclusion and before limit', () => {
    const items = [
      hubItem('excluded', 'Spec Report'),
      hubItem('doc-1', 'Spec Report'),
      hubItem('doc-2', 'Architecture Note'),
      hubItem('doc-3', 'SPEC Appendix'),
    ];

    expect(
      projectDocsHubPickerItems({
        items,
        query: ' spec ',
        excludeDocIds: ['excluded'],
        searchMode: 'local',
        limit: 2,
      }).map((item) => item.id),
    ).toEqual(['doc-1', 'doc-3']);
  });

  it('projects remote search without client-side query filtering', () => {
    const items = [
      hubItem('excluded', 'Spec Report'),
      hubItem('doc-1', 'Architecture Note'),
      hubItem('doc-2', 'Roadmap'),
    ];

    expect(
      projectDocsHubPickerItems({
        items,
        query: 'spec',
        excludeDocIds: ['excluded'],
        searchMode: 'remote',
        limit: 2,
      }).map((item) => item.id),
    ).toEqual(['doc-1', 'doc-2']);
  });

  it('projects and builds selections with adapter-provided doc ids', () => {
    const items = [
      { ...hubItem('hub-1', 'Spec Report'), source_id: 'doc-1' },
      { ...hubItem('hub-2', 'Roadmap'), source_id: 'doc-2' },
    ] as DocsHubItem[];
    const getDocId = (item: DocsHubItem) => item.source_id;

    expect(
      projectDocsHubPickerItems({
        items,
        query: '',
        excludeDocIds: ['doc-1'],
        searchMode: 'local',
        getDocId,
      }).map(getDocId),
    ).toEqual(['doc-2']);
    expect(buildDocsHubPickerSelection(items[1], getDocId)).toEqual({
      docId: 'doc-2',
      item: items[1],
      title: 'Roadmap',
    });
  });

  it('builds local and remote docs hub query params', () => {
    expect(
      buildDocsHubPickerParams({ query: ' ignored ', searchMode: 'local' }),
    ).toEqual({ page_size: 100 });
    expect(
      buildDocsHubPickerParams({ query: '  motor spec  ', searchMode: 'remote' }),
    ).toEqual({
      page_size: 100,
      q: 'motor spec',
      sort_by: 'updated_at',
      sort_dir: 'desc',
    });
    expect(
      buildDocsHubPickerParams({ query: ' ', searchMode: 'remote' }),
    ).toEqual({
      page_size: 100,
      sort_by: 'updated_at',
      sort_dir: 'desc',
    });
  });

  it('delays only non-empty remote searches', () => {
    expect(getDocsHubPickerDelayMs({ query: ' ', searchMode: 'remote' })).toBe(0);
    expect(getDocsHubPickerDelayMs({ query: 'x', searchMode: 'local' })).toBe(0);
    expect(getDocsHubPickerDelayMs({ query: ' x ', searchMode: 'remote' })).toBe(
      DOCS_HUB_PICKER_REMOTE_SEARCH_DELAY_MS,
    );
  });
});
