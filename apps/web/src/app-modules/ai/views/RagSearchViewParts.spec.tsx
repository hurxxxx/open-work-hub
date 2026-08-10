import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { KeywordSearchHit } from '@/src/platform/search/search-api';
import {
  SearchEntityFilterButton,
  SearchResultPreview,
  SearchResultRow,
} from './RagSearchViewParts';

const hit: KeywordSearchHit = {
  created_at: '2026-07-20T00:00:00Z',
  date_markers: {},
  deep_link: '/w/engineering/quality/issues/issue-1',
  entity_id: 'issue-1',
  entity_type: 'quality_issue',
  metadata: {},
  people: [],
  preview_url: null,
  score: 1,
  snippet: { highlights: [], text: 'Brake vibration investigation' },
  status: null,
  status_label: null,
  summary: 'Brake vibration investigation',
  targets: [],
  title: 'Investigate brake vibration',
  updated_at: '2026-07-20T00:00:00Z',
  visibility: 'shared',
  workspace_id: 'workspace-1',
};

describe('RagSearchViewParts source labels', () => {
  it('uses the bootstrap descriptor label for both result and preview metadata', () => {
    const entityTypeLabels = new Map([['quality_issue', '품질 이슈']]);

    render(
      <MemoryRouter>
        <SearchResultRow
          entityTypeLabels={entityTypeLabels}
          hit={hit}
          isSelected
          onSelect={vi.fn()}
          timeZone="Asia/Seoul"
        />
        <SearchResultPreview
          entityTypeLabels={entityTypeLabels}
          hit={hit}
          timeZone="Asia/Seoul"
          variant="side"
        />
      </MemoryRouter>,
    );

    expect(screen.getAllByText('품질 이슈')).toHaveLength(2);
    expect(screen.queryByText('Quality Issue')).toBeNull();
    expect(
      screen.getByRole('button', {
        name: /품질 이슈.*Investigate brake vibration/,
      }),
    ).not.toBeNull();
    expect(
      screen.getAllByRole('link', {
        name: /품질 이슈.*Investigate brake vibration/,
      }),
    ).toHaveLength(2);
    expect(
      screen.getByRole('region', {
        name: /품질 이슈.*Investigate brake vibration/,
      }),
    ).not.toBeNull();
  });

  it('exposes the active source filter state to assistive technology', () => {
    render(
      <SearchEntityFilterButton
        active
        count={2}
        entityType="quality_issue"
        label="품질 이슈"
        onClick={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('button', { name: '품질 이슈 2', pressed: true }),
    ).not.toBeNull();
  });
});
