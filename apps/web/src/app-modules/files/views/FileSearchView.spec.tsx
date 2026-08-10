import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { FileSearchController } from './useFileSearchController';
import { FileSearchViewContent } from './FileSearchView';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}:${Object.values(options).join(':')}` : key,
  }),
}));

function controller(): FileSearchController {
  return {
    actions: {
      download: vi.fn(),
      nextPage: vi.fn(),
      previousPage: vi.fn(),
      setQueryInput: vi.fn(),
      setStrategy: vi.fn(),
      submitSearch: vi.fn(),
    },
    state: {
      busyDownloadId: null,
      error: null,
      queryInput: 'release',
      response: {
        query: 'release',
        strategy: 'hybrid',
        page: 2,
        page_size: 20,
        hits: [
          {
            rank: 21,
            file_id: 'file-1',
            filename: 'roadmap.txt',
            folder_id: null,
            content_type: 'text/plain',
            size_bytes: 1024,
            score: 0.8754,
            methods: ['bm25', 'dense_vector', 'rrf'],
            snippet: {
              text: 'A😀 release plan',
              highlights: [{ start: 4, end: 11 }],
            },
            updated_at: '2026-07-23T00:00:00Z',
          },
        ],
        has_more: true,
        max_ranked_results: 100,
        latency_ms: 12,
        trace_id: 'trace-1',
      },
      searching: false,
      strategy: 'hybrid',
    },
  };
}

describe('FileSearchViewContent', () => {
  it('renders ranked highlighted results and exposes paging and download actions', () => {
    const value = controller();
    render(<FileSearchViewContent controller={value} />);

    const row = screen.getByRole('article', { name: 'roadmap.txt' });
    expect(within(row).getByText('release').tagName).toBe('MARK');
    expect(within(row).getByText('files.search.methods.bm25')).toBeTruthy();
    expect(within(row).getByText('files.search.methods.denseVector')).toBeTruthy();
    expect(within(row).getByText('files.search.methods.rrf')).toBeTruthy();
    expect(within(row).getByText('files.search.rank:21')).toBeTruthy();
    expect(within(row).getByText('files.search.score:0.875')).toBeTruthy();

    fireEvent.click(
      screen.getByRole('button', { name: 'files.search.pagination.next' }),
    );
    fireEvent.click(
      within(row).getByRole('button', { name: 'files.actions.download' }),
    );

    expect(value.actions.nextPage).toHaveBeenCalledTimes(1);
    expect(value.actions.download).toHaveBeenCalledWith('file-1');
  });

  it('keeps a very small non-zero relevance score visible', () => {
    const value = controller();
    const hit = value.state.response?.hits[0];
    if (!hit) {
      throw new Error('expected a seeded file search hit');
    }
    hit.score = 0.000131607;
    render(<FileSearchViewContent controller={value} />);

    const row = screen.getByRole('article', { name: 'roadmap.txt' });
    expect(within(row).getByText('files.search.score:0.000132')).toBeTruthy();
  });

  it('announces an active search and disables duplicate submission', () => {
    const value = controller();
    value.state.searching = true;
    value.state.response = null;
    render(<FileSearchViewContent controller={value} />);

    expect(screen.getByRole('status').textContent).toBe(
      'files.search.searching',
    );
    expect(
      (
        screen.getByRole('button', {
          name: 'files.search.actions.search',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
});
