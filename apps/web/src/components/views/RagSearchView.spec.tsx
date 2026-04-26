import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RagSearchView } from './RagSearchView';
import { WorkspaceBootstrapProvider } from '@/src/domains/workspaces/workspace-bootstrap-context';
import { SearchApiError } from '@/src/domains/search/search-api';

const authHarness = vi.hoisted(() => ({
  logout: vi.fn(),
  state: {
    token: 'test-token',
    user: {
      id: 'user-1',
      email: 'member@aidoo.local',
      full_name: 'AIDOO Member',
      display_name: 'AIDOO Member',
      status: 'active',
      theme_preference: 'system',
      primary_org_unit: null,
      workspaces: [
        {
          id: 'workspace-hq',
          slug: 'hq',
          name: 'Aidoo HQ',
          role: 'admin',
        },
      ],
      workspace_roles: [],
      system_roles: [],
      group_ids: [],
      group_slugs: [],
      must_change_password: false,
    },
  },
}));

const searchHarness = vi.hoisted(() => ({
  queryWorkspaceKeywordSearch: vi.fn(),
}));

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({
    ...authHarness.state,
    logout: authHarness.logout,
  }),
}));

vi.mock('@/src/domains/search/search-api', async () => {
  const actual = await vi.importActual<typeof import('@/src/domains/search/search-api')>(
    '@/src/domains/search/search-api',
  );
  return {
    ...actual,
    queryWorkspaceKeywordSearch: searchHarness.queryWorkspaceKeywordSearch,
  };
});

function renderView({
  initialEntry = '/tool/search?workspace=hq',
  workspaceSlug = 'hq',
}: {
  initialEntry?: string;
  workspaceSlug?: string | null;
} = {}) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <WorkspaceBootstrapProvider
        value={{
          data: workspaceSlug
            ? {
                workspace: {
                  id: `workspace-${workspaceSlug}`,
                  slug: workspaceSlug,
                  name: 'Aidoo HQ',
                  role: 'admin',
                },
                apps: [],
                nav: [],
              }
            : null,
          error: null,
          loading: false,
        }}
      >
        <RagSearchView />
        <LocationProbe />
      </WorkspaceBootstrapProvider>
    </MemoryRouter>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function searchHit(overrides = {}) {
  return {
    entity_type: 'pms_issue',
    entity_id: 'issue-1',
    workspace_id: 'workspace-hq',
    title: 'Budget blocker',
    summary: 'Supplier repricing increased the budget risk.',
    snippet: {
      text: 'Supplier repricing increased the budget risk.',
      highlights: [{ start: 36, end: 40 }],
    },
    score: 7.4,
    status: 'in_progress',
    status_label: 'In Progress',
    visibility: 'workspace',
    updated_at: '2026-04-24T00:00:00Z',
    created_at: '2026-04-20T00:00:00Z',
    date_markers: { due_date: '2026-04-30' },
    people: [{ role: 'assignee', user_id: 'user-1', label: 'Kim' }],
    containers: [{ type: 'list', id: 'list-1', label: 'Sprint Backlog' }],
    deep_link: '/tool/pms-list-list-1?workspace=hq&issue=issue-1',
    preview_url: null,
    metadata: { issue_number: 12, priority: 'high' },
    ...overrides,
  };
}

function searchResponse(overrides = {}) {
  return {
    query: 'budget risk',
    hits: [searchHit()],
    facets: {
      entity_types: [
        { value: 'pms_issue', label: 'PMS', count: 1 },
      ],
      status: [
        { entity_type: 'pms_issue', value: 'in_progress', label: 'In Progress', count: 1 },
      ],
      containers: [
        { type: 'list', id: 'list-1', label: 'Sprint Backlog', count: 1 },
      ],
    },
    total: 1,
    has_more: false,
    next_offset: null,
    trace_id: 'trace-1',
    ...overrides,
  };
}

describe('RagSearchView keyword search', () => {
  beforeEach(() => {
    searchHarness.queryWorkspaceKeywordSearch.mockReset();
    authHarness.logout.mockReset();
    authHarness.state.token = 'test-token';
    authHarness.state.user.workspaces = [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'Aidoo HQ',
        role: 'admin',
      },
    ];
    searchHarness.queryWorkspaceKeywordSearch.mockResolvedValue(searchResponse());
  });

  it('hydrates from URL and calls the keyword search API with workspace scope', async () => {
    renderView({
      initialEntry: '/tool/search?workspace=hq&q=budget%20risk&type=pms_issue&sort=updated_at',
    });

    await waitFor(() => {
      expect(searchHarness.queryWorkspaceKeywordSearch).toHaveBeenCalledWith(
        expect.objectContaining({
          workspace_id: 'workspace-hq',
          query: 'budget risk',
          entity_types: ['pms_issue'],
          sort: { field: 'updated_at', direction: 'desc' },
        }),
        'test-token',
        'hq',
        expect.any(Object),
      );
    });
    expect(screen.getByDisplayValue('budget risk')).toBeTruthy();
    expect(await screen.findByRole('button', { name: /검색 결과 선택: Budget blocker/ })).toBeTruthy();
  });

  it('renders server facets, safe highlights, preview metadata, and explicit deep links', async () => {
    renderView();

    expect(await screen.findByRole('button', { name: /검색 결과 선택: Budget blocker/ })).toBeTruthy();
    expect(screen.getAllByText('PMS').length).toBeGreaterThan(0);
    expect(screen.getByText('1건 중 1건 표시')).toBeTruthy();
    expect(document.querySelector('mark')?.textContent).toBeTruthy();
    expect((await screen.findAllByText('우선순위')).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: /열기: Budget blocker/ })[0].getAttribute('href')).toBe(
      '/tool/pms-list-list-1?workspace=hq&issue=issue-1',
    );
  });

  it('selects a result in place and stores selection in the URL', async () => {
    searchHarness.queryWorkspaceKeywordSearch.mockResolvedValueOnce(searchResponse({
      total: 2,
      hits: [
        searchHit(),
        searchHit({
          entity_type: 'doc',
          entity_id: 'doc-1',
          title: 'Launch notes',
          status: null,
          status_label: null,
          visibility: 'shared',
          containers: [{ type: 'teamspace', id: 'team-1', label: 'Launch' }],
          deep_link: '/w/hq/docs/doc-1',
          metadata: { source_kind: 'manual' },
        }),
      ],
      facets: {
        entity_types: [
          { value: 'pms_issue', label: 'PMS', count: 1 },
          { value: 'doc', label: '문서', count: 1 },
        ],
        status: [],
        containers: [],
      },
    }));

    renderView({ initialEntry: '/tool/search?workspace=hq&q=budget%20risk' });

    const docButton = await screen.findByRole('button', { name: /검색 결과 선택: Launch notes/ });
    fireEvent.click(docButton);

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe(
        '/tool/search?workspace=hq&q=budget+risk&selected_type=doc&selected_id=doc-1',
      );
    });
    expect(docButton.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getAllByRole('link', { name: /열기: Launch notes/ })[0].getAttribute('href')).toBe('/w/hq/docs/doc-1');
  });

  it('hydrates selected_type and selected_id from the URL', async () => {
    searchHarness.queryWorkspaceKeywordSearch.mockResolvedValueOnce(searchResponse({
      total: 2,
      hits: [
        searchHit(),
        searchHit({
          entity_type: 'doc',
          entity_id: 'doc-1',
          title: 'Launch notes',
          status: null,
          status_label: null,
          visibility: 'shared',
          deep_link: '/w/hq/docs/doc-1',
          metadata: { source_kind: 'manual' },
        }),
      ],
    }));

    renderView({
      initialEntry: '/tool/search?workspace=hq&q=budget%20risk&selected_type=doc&selected_id=doc-1',
    });

    const docButton = await screen.findByRole('button', { name: /검색 결과 선택: Launch notes/ });
    await waitFor(() => {
      expect(docButton.getAttribute('aria-pressed')).toBe('true');
    });
    expect(screen.getAllByRole('link', { name: /열기: Launch notes/ })[0].getAttribute('href')).toBe('/w/hq/docs/doc-1');
  });

  it('resets selected URL state when filters trigger a new search', async () => {
    searchHarness.queryWorkspaceKeywordSearch
      .mockResolvedValueOnce(searchResponse({
        total: 2,
        hits: [
          searchHit(),
          searchHit({
            entity_type: 'doc',
            entity_id: 'doc-1',
            title: 'Launch notes',
            status: null,
            status_label: null,
            visibility: 'shared',
            deep_link: '/w/hq/docs/doc-1',
          }),
        ],
      }))
      .mockResolvedValueOnce(searchResponse());

    renderView({
      initialEntry: '/tool/search?workspace=hq&q=budget%20risk&selected_type=doc&selected_id=doc-1',
    });

    await screen.findByRole('button', { name: /검색 결과 선택: Launch notes/ });
    fireEvent.click(screen.getByRole('button', { name: /PMS/ }));

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/tool/search?workspace=hq&q=budget+risk&type=pms_issue');
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /검색 결과 선택: Budget blocker/ }).getAttribute('aria-pressed')).toBe('true');
    });
  });

  it('opens selected rows in a new tab with command or control modifiers', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderView();

    const resultButton = await screen.findByRole('button', { name: /검색 결과 선택: Budget blocker/ });
    fireEvent.click(resultButton, { metaKey: true });
    fireEvent.keyDown(resultButton, { key: 'Enter', ctrlKey: true });

    expect(openSpy).toHaveBeenCalledTimes(2);
    expect(openSpy).toHaveBeenCalledWith('/tool/pms-list-list-1?workspace=hq&issue=issue-1', '_blank', 'noopener,noreferrer');
    openSpy.mockRestore();
  });

  it('submits entity filters and sort changes to the keyword API', async () => {
    renderView();
    await screen.findByRole('button', { name: /검색 결과 선택: Budget blocker/ });

    fireEvent.click(screen.getByRole('button', { name: /문서/ }));
    await waitFor(() => {
      expect(searchHarness.queryWorkspaceKeywordSearch).toHaveBeenCalledWith(
        expect.objectContaining({
          entity_types: ['doc'],
        }),
        'test-token',
        'hq',
        expect.any(Object),
      );
    });
    await waitFor(() => {
      expect(searchHarness.queryWorkspaceKeywordSearch).toHaveBeenLastCalledWith(
        expect.objectContaining({
          entity_types: ['doc'],
        }),
        'test-token',
        'hq',
        expect.any(Object),
      );
    });

    fireEvent.click(screen.getAllByRole('button', { name: '최신순' })[0]);
    await waitFor(() => {
      expect(searchHarness.queryWorkspaceKeywordSearch).toHaveBeenCalledWith(
        expect.objectContaining({
          sort: { field: 'updated_at', direction: 'desc' },
        }),
        'test-token',
        'hq',
        expect.any(Object),
      );
    });
  });

  it('loads more results using next_offset', async () => {
    searchHarness.queryWorkspaceKeywordSearch
      .mockResolvedValueOnce(searchResponse({ has_more: true, next_offset: 20 }))
      .mockResolvedValueOnce(searchResponse({
        hits: [
          {
            ...searchResponse().hits[0],
            entity_id: 'issue-2',
            title: 'Second blocker',
            deep_link: '/tool/pms-list-list-1?workspace=hq&issue=issue-2',
          },
        ],
        has_more: false,
        next_offset: null,
      }));

    renderView();
    await screen.findByRole('button', { name: /검색 결과 선택: Budget blocker/ });
    fireEvent.click(screen.getByRole('button', { name: '더 보기' }));

    await screen.findByRole('button', { name: /검색 결과 선택: Second blocker/ });
    expect(screen.getByRole('button', { name: /검색 결과 선택: Budget blocker/ })).toBeTruthy();
    expect(searchHarness.queryWorkspaceKeywordSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 20 }),
      'test-token',
      'hq',
      expect.any(Object),
    );
  });

  it('logs out on expired sessions', async () => {
    searchHarness.queryWorkspaceKeywordSearch.mockRejectedValueOnce(
      new SearchApiError(401, '세션이 만료되었습니다. 다시 로그인해주세요.'),
    );

    renderView();

    await waitFor(() => {
      expect(authHarness.logout).toHaveBeenCalled();
    });
    expect(await screen.findByText('세션이 만료되었습니다. 다시 로그인해주세요.')).toBeTruthy();
  });

  it('renders a workspace guidance state when no workspace context is available', () => {
    authHarness.state.user.workspaces = [];
    renderView({ initialEntry: '/tool/search', workspaceSlug: null });

    expect(screen.getByText('검색할 workspace를 찾을 수 없습니다.')).toBeTruthy();
    expect(searchHarness.queryWorkspaceKeywordSearch).not.toHaveBeenCalled();
  });
});
