import { describe, expect, it } from 'vitest';

import {
  buildSearchEntityLabelMap,
  buildWorkspaceSearchSubtitle,
  resolveSearchEntityLabel,
} from './RagSearchViewPresentation';

describe('RagSearchView presentation', () => {
  it('resolves an extension entity label through its bootstrap i18n key', () => {
    expect(
      resolveSearchEntityLabel(
        {
          label: 'Quality Record',
          label_key: 'quality.search.entityRecord',
        },
        (key, options) =>
          key === 'quality.search.entityRecord'
            ? '품질 기록'
            : options.defaultValue,
      ),
    ).toBe('품질 기록');
  });

  it('uses the bootstrap label when the locale has no matching key', () => {
    expect(
      resolveSearchEntityLabel(
        {
          label: 'Quality Record',
          label_key: 'quality.search.entityRecord',
        },
        (_key, options) => options.defaultValue,
      ),
    ).toBe('Quality Record');
  });

  it('builds the subtitle from only the active bootstrap source labels', () => {
    const labels = buildSearchEntityLabelMap([
      { id: null, label: 'All' },
      { id: 'doc', label: 'Docs' },
      { id: 'quality_issue', label: 'Quality issues' },
    ]);

    expect(
      buildWorkspaceSearchSubtitle({
        entityTypeLabels: labels,
        fallback: 'Search work data.',
        workspaceName: 'Engineering',
      }),
    ).toBe('Engineering · Docs · Quality issues');
  });

  it('keeps an extension entity whose real id is all', () => {
    expect(
      buildSearchEntityLabelMap([
        { id: null, label: 'All sources' },
        { id: 'all', label: 'All records app' },
      ]).get('all'),
    ).toBe('All records app');
  });

  it('uses the existing localized fallback when no context is available', () => {
    expect(
      buildWorkspaceSearchSubtitle({
        entityTypeLabels: new Map(),
        fallback: 'Search work data.',
        workspaceName: '',
      }),
    ).toBe('Search work data.');
  });
});
