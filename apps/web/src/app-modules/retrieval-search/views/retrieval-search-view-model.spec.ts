import { describe, expect, it } from 'vitest';

import {
  buildRetrievalSearchParams,
  parseRetrievalSearchParams,
  toggleRetrievalSourceSelection,
} from './retrieval-search-view-model';

describe('retrieval-search-view-model', () => {
  it('parses retrieval URL criteria with safe defaults', () => {
    const parsed = parseRetrievalSearchParams(
      new URLSearchParams(
        'q=release&strategy=semantic&answer_mode=grounded-answer&top_k=12&source=keyword&source=generic_rag&source=bad source',
      ),
    );

    expect(parsed).toEqual({
      answerMode: 'grounded-answer',
      query: 'release',
      selectedSources: ['generic_rag', 'keyword'],
      strategy: 'semantic',
      topK: 12,
    });
  });

  it('falls back for invalid strategy, answer mode, and top k', () => {
    const parsed = parseRetrievalSearchParams(
      new URLSearchParams('strategy=graph&answer_mode=full&top_k=999'),
    );

    expect(parsed.strategy).toBe('hybrid');
    expect(parsed.answerMode).toBe('search-only');
    expect(parsed.topK).toBe(8);
  });

  it('builds compact retrieval URL params', () => {
    const params = buildRetrievalSearchParams({
      answerMode: 'search-only',
      query: '  roadmap  ',
      selectedSources: ['keyword'],
      strategy: 'hybrid',
      topK: 8,
      workspaceSlug: 'delivery-hub',
    });

    expect(params.toString()).toBe(
      'workspace=delivery-hub&q=roadmap&source=keyword',
    );
  });

  it('toggles source selection deterministically', () => {
    expect(toggleRetrievalSourceSelection(['keyword'], 'generic_rag')).toEqual([
      'generic_rag',
      'keyword',
    ]);
    expect(
      toggleRetrievalSourceSelection(['generic_rag', 'keyword'], 'keyword'),
    ).toEqual(['generic_rag']);
  });
});
