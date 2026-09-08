import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { DocsHubItem } from '../api/docs-api';
import {
  useDocsHubController,
  type DocsHubControllerClient,
} from './useDocsHubController';

function doc(overrides: Partial<DocsHubItem> = {}): DocsHubItem {
  return {
    id: 'doc-1',
    title: 'Doc',
    doc_type: 'native_doc',
    source_type: 'native_doc',
    source_ref: null,
    collection: null,
    primary_target: null,
    source_deeplink: null,
    trashed_at: null,
    last_viewed_at: null,
    sharing_summary: null,
    page_count: 1,
    content_format: 'block',
    can_edit: true,
    can_manage: true,
    is_favorite: false,
    created_by_name: 'Ada',
    created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
    ...overrides,
  } as DocsHubItem;
}

function client(
  overrides: Partial<DocsHubControllerClient> = {},
): DocsHubControllerClient {
  return {
    listDocsHub: vi.fn().mockResolvedValue({
      items: [doc()],
      total: 1,
      limit: 20,
      offset: 0,
    }),
    ...overrides,
  };
}

describe('useDocsHubController', () => {
  it('loads docs with the current hub filters', async () => {
    const testClient = client();
    const { result } = renderHook(() =>
      useDocsHubController({
        token: 'token-1',
        listEnabled: true,
        activeCategory: 'mine',
        activeSourceApp: 'meeting',
        activeSourceKind: 'minutes',
        activeSpaceId: 'space-1',
        client: testClient,
      }),
    );

    await waitFor(() => expect(result.current.state.docs).toHaveLength(1));

    expect(testClient.listDocsHub).toHaveBeenCalledWith('token-1', {
      view: 'mine',
      q: undefined,
      sort_by: 'updated_at',
      sort_dir: 'desc',
      source_app: 'meeting',
      source_kind: 'minutes',
      space_id: 'space-1',
    });
    expect(result.current.state.total).toBe(1);
    expect(result.current.state.loadingList).toBe(false);
  });

  it('debounces search changes into a list reload', async () => {
    const testClient = client();
    const { result } = renderHook(() =>
      useDocsHubController({
        token: 'token-1',
        listEnabled: true,
        activeCategory: 'all',
        client: testClient,
        searchDebounceMs: 0,
      }),
    );

    await waitFor(() => expect(result.current.state.docs).toHaveLength(1));
    vi.mocked(testClient.listDocsHub).mockClear();

    act(() => {
      result.current.actions.handleSearchChange('roadmap');
    });

    await waitFor(() => {
      expect(testClient.listDocsHub).toHaveBeenCalledWith(
        'token-1',
        expect.objectContaining({ q: 'roadmap' }),
      );
    });
  });

  it('does not load the hub list when list view is disabled', () => {
    const testClient = client();
    renderHook(() =>
      useDocsHubController({
        token: 'token-1',
        listEnabled: false,
        activeCategory: 'all',
        client: testClient,
      }),
    );

    expect(testClient.listDocsHub).not.toHaveBeenCalled();
  });

  it('clears list state when hub loading fails', async () => {
    const testClient = client({
      listDocsHub: vi.fn().mockRejectedValue(new Error('failed')),
    });
    const { result } = renderHook(() =>
      useDocsHubController({
        token: 'token-1',
        listEnabled: true,
        activeCategory: 'all',
        client: testClient,
      }),
    );

    await waitFor(() => expect(result.current.state.loadingList).toBe(false));

    expect(result.current.state.docs).toEqual([]);
    expect(result.current.state.total).toBe(0);
  });
});
