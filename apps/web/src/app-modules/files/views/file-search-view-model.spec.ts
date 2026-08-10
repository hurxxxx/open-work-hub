import { describe, expect, it } from 'vitest';

import {
  buildFileSearchParams,
  fileSearchSnippetSegments,
  orderFileSearchHits,
  parseFileSearchParams,
} from './file-search-view-model';

describe('file search view model', () => {
  it('round-trips safe Files search URL criteria within the ranked window', () => {
    const parsed = parseFileSearchParams(
      new URLSearchParams('view=search&q= release plan &strategy=semantic&page=3'),
    );

    expect(parsed).toEqual({
      page: 3,
      query: 'release plan',
      strategy: 'semantic',
    });
    expect(
      buildFileSearchParams({
        page: parsed.page,
        query: parsed.query,
        strategy: parsed.strategy,
      }).toString(),
    ).toBe('view=search&q=release+plan&strategy=semantic&page=3');

    expect(
      parseFileSearchParams(
        new URLSearchParams('view=search&strategy=unknown&page=6'),
      ),
    ).toEqual({ page: 1, query: '', strategy: 'hybrid' });
  });

  it('uses UTF-16 highlight offsets and orders result rows deterministically', () => {
    expect(
      fileSearchSnippetSegments({
        text: 'A😀 release plan',
        highlights: [{ start: 4, end: 11 }],
      }),
    ).toEqual([
      { highlighted: false, text: 'A😀 ' },
      { highlighted: true, text: 'release' },
      { highlighted: false, text: ' plan' },
    ]);

    const common = {
      content_type: 'text/plain',
      filename: 'file.txt',
      folder_id: null,
      methods: ['bm25'],
      size_bytes: 10,
      snippet: { text: '', highlights: [] },
      updated_at: '2026-07-23T00:00:00Z',
    };
    expect(
      orderFileSearchHits([
        { ...common, file_id: 'b', rank: 2, score: 0.9 },
        { ...common, file_id: 'c', rank: 1, score: 0.7 },
        { ...common, file_id: 'a', rank: 1, score: 0.7 },
      ]).map((hit) => hit.file_id),
    ).toEqual(['a', 'c', 'b']);
  });
});
