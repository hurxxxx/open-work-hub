import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RagSearchView } from './RagSearchView';
import { WorkspaceBootstrapProvider } from '@/src/domains/workspaces/workspace-bootstrap-context';
import { RagApiError } from '@/src/domains/rag/rag-api';

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
        {
          id: 'workspace-lab',
          slug: 'lab',
          name: 'Aidoo Lab',
          role: 'member',
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

const ragHarness = vi.hoisted(() => ({
  listWorkspaceRagSources: vi.fn(),
  queryWorkspaceRag: vi.fn(),
}));

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({
    ...authHarness.state,
    logout: authHarness.logout,
  }),
}));

vi.mock('@/src/domains/rag/rag-api', async () => {
  const actual = await vi.importActual<typeof import('@/src/domains/rag/rag-api')>(
    '@/src/domains/rag/rag-api',
  );
  return {
    ...actual,
    listWorkspaceRagSources: ragHarness.listWorkspaceRagSources,
    queryWorkspaceRag: ragHarness.queryWorkspaceRag,
  };
});

function renderView({
  initialEntry = '/tool/search',
  workspaceSlug = 'hq',
  workspaceName = 'Aidoo HQ',
}: {
  initialEntry?: string;
  workspaceSlug?: string | null;
  workspaceName?: string;
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
                  name: workspaceName,
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
      </WorkspaceBootstrapProvider>
    </MemoryRouter>,
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('RagSearchView', () => {
  beforeEach(() => {
    ragHarness.listWorkspaceRagSources.mockReset();
    ragHarness.queryWorkspaceRag.mockReset();
    authHarness.logout.mockReset();
    authHarness.state.token = 'test-token';
    authHarness.state.user.workspaces = [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'Aidoo HQ',
        role: 'admin',
      },
      {
        id: 'workspace-lab',
        slug: 'lab',
        name: 'Aidoo Lab',
        role: 'member',
      },
    ];
    ragHarness.listWorkspaceRagSources.mockResolvedValue({
      sources: [
        {
          source_kind: 'manual',
          resource_type: 'docs_native_doc',
          label: 'Docs / Manual',
          app_id: 'docs',
        },
        {
          source_kind: 'meeting',
          resource_type: 'meeting',
          label: 'Meetings',
          app_id: 'meeting',
        },
        {
          source_kind: 'pms_issue',
          resource_type: 'pms_issue',
          label: 'PMS Issues',
          app_id: 'pms',
        },
        {
          source_kind: 'planner_event',
          resource_type: 'planner_event',
          label: 'Planner',
          app_id: 'planner',
        },
      ],
    });
    ragHarness.queryWorkspaceRag.mockResolvedValue({
      query: 'budget risk',
      answer_mode: 'grounded-answer',
      hits: [
        {
          source_kind: 'manual',
          resource_type: 'docs_native_doc',
          resource_id: 'doc-1',
          workspace_id: 'hq',
          title: 'Budget Review',
          summary: 'Supplier repricing increased the budget risk.',
          score: 0.91,
          citation: 'doc-1:0',
          owner_label: 'Kim',
          acl_summary: [],
          origin_ref: 'docs:doc-1',
          metadata: {},
        },
      ],
      grounded_answer: {
        text: 'Budget risk is currently elevated because supplier repricing changed the expected cost baseline.',
        citations: [
          {
            resource_id: 'doc-1',
            source_kind: 'manual',
            quote: 'Supplier repricing increased the budget risk.',
            locator: 'doc-1:0',
          },
        ],
        unsupported_claims: [],
        sources_used: ['manual'],
      },
      sources_used: ['manual'],
      query_profile: {},
      trace_id: 'trace-1',
      latency_ms: 143,
    });
  });

  it('hydrates from URL, auto-runs a workspace-scoped search, and keeps search-only mode', async () => {
    ragHarness.queryWorkspaceRag.mockResolvedValueOnce({
      query: 'budget risk',
      answer_mode: 'search-only',
      hits: [
        {
          source_kind: 'meeting',
          resource_type: 'meeting',
          resource_id: 'meeting-1',
          workspace_id: 'hq',
          title: 'Budget Review Meeting',
          summary: 'Supplier repricing increased the budget risk.',
          score: 0.81,
          citation: 'meeting-1:0',
          owner_label: 'Kim',
          acl_summary: [],
          origin_ref: 'meeting:meeting-1',
          metadata: {},
        },
      ],
      grounded_answer: null,
      sources_used: ['meeting'],
      query_profile: {},
      trace_id: 'trace-search-only',
      latency_ms: 121,
    });

    renderView({
      initialEntry: '/tool/search?workspace=hq&q=budget%20risk&mode=search-only&source=meeting',
    });

    await waitFor(() => {
      expect(ragHarness.listWorkspaceRagSources).toHaveBeenCalledWith(
        'test-token',
        'hq',
        expect.any(Object),
      );
    });
    await waitFor(() => {
      expect(ragHarness.queryWorkspaceRag).toHaveBeenCalledWith(
        expect.objectContaining({
          query: 'budget risk',
          answer_mode: 'search-only',
          source_kinds: ['meeting'],
          top_k: 8,
        }),
        'test-token',
        'hq',
        expect.any(Object),
      );
    });

    expect(screen.getByDisplayValue('budget risk')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: '검색 결과만' }).className.includes('bg-app-accent'),
    ).toBe(true);
    expect(screen.queryByText(/Budget risk is currently elevated/i)).toBeNull();
  });

  it('submits selected source filters and renders grounded results', async () => {
    renderView();

    await screen.findByText('Docs / Manual');

    fireEvent.change(
      screen.getByLabelText('질문 또는 검색어'),
      { target: { value: 'budget risk' } },
    );
    const meetingCheckbox = screen.getByText('Meetings').closest('label')?.querySelector('input');
    expect(meetingCheckbox).toBeTruthy();
    fireEvent.click(meetingCheckbox as HTMLInputElement);
    fireEvent.click(screen.getByRole('button', { name: '검색 실행' }));

    await waitFor(() => {
      expect(ragHarness.queryWorkspaceRag).toHaveBeenCalledWith(
        expect.objectContaining({
          query: 'budget risk',
          answer_mode: 'grounded-answer',
          source_kinds: ['manual', 'pms_issue', 'planner_event'],
          top_k: 8,
        }),
        'test-token',
        'hq',
        expect.any(Object),
      );
    });

    expect(
      await screen.findByText(/supplier repricing changed the expected cost baseline/i),
    ).toBeTruthy();
    expect(
      screen.getByRole('link', { name: '원문 열기' }).getAttribute('href'),
    ).toBe('/w/hq/docs/doc-1');
  });

  it('surfaces API validation errors inline', async () => {
    ragHarness.queryWorkspaceRag.mockRejectedValueOnce(
      new RagApiError(422, 'body > query: Field required'),
    );

    renderView();
    await screen.findByText('Docs / Manual');

    fireEvent.change(
      screen.getByLabelText('질문 또는 검색어'),
      { target: { value: '   budget risk   ' } },
    );
    fireEvent.click(screen.getByRole('button', { name: '검색 실행' }));

    expect(await screen.findByText('body > query: Field required')).toBeTruthy();
  });

  it('logs out when the session is expired', async () => {
    ragHarness.queryWorkspaceRag.mockRejectedValueOnce(
      new RagApiError(401, '세션이 만료되었습니다. 다시 로그인해주세요.'),
    );

    renderView();
    await screen.findByText('Docs / Manual');

    fireEvent.change(
      screen.getByLabelText('질문 또는 검색어'),
      { target: { value: 'budget risk' } },
    );
    fireEvent.click(screen.getByRole('button', { name: '검색 실행' }));

    await waitFor(() => {
      expect(authHarness.logout).toHaveBeenCalledTimes(1);
    });
  });

  it('ignores stale in-flight responses after workspace changes', async () => {
    const pending = deferred<Awaited<ReturnType<typeof ragHarness.queryWorkspaceRag>>>();
    ragHarness.queryWorkspaceRag.mockReturnValueOnce(pending.promise);

    const view = renderView({
      initialEntry: '/tool/search?workspace=hq&q=budget%20risk&source=manual',
      workspaceSlug: 'hq',
      workspaceName: 'Aidoo HQ',
    });

    await waitFor(() => {
      expect(ragHarness.queryWorkspaceRag).toHaveBeenCalledWith(
        expect.any(Object),
        'test-token',
        'hq',
        expect.any(Object),
      );
    });

    view.rerender(
      <MemoryRouter
        key="lab"
        initialEntries={['/tool/search?workspace=lab&q=budget%20risk&source=manual']}
      >
        <WorkspaceBootstrapProvider
          value={{
            data: {
              workspace: {
                id: 'workspace-lab',
                slug: 'lab',
                name: 'Aidoo Lab',
                role: 'member',
              },
              apps: [],
              nav: [],
            },
            error: null,
            loading: false,
          }}
        >
          <RagSearchView />
        </WorkspaceBootstrapProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(ragHarness.listWorkspaceRagSources).toHaveBeenLastCalledWith(
        'test-token',
        'lab',
        expect.any(Object),
      );
    });

    pending.resolve({
      query: 'budget risk',
      answer_mode: 'grounded-answer',
      hits: [
        {
          source_kind: 'manual',
          resource_type: 'docs_native_doc',
          resource_id: 'doc-old',
          workspace_id: 'hq',
          title: 'Old Workspace Result',
          summary: 'Should not be shown.',
          score: 0.9,
          citation: null,
          owner_label: null,
          acl_summary: [],
          origin_ref: null,
          metadata: {},
        },
      ],
      grounded_answer: {
        text: 'Should not be shown.',
        citations: [],
        unsupported_claims: [],
        sources_used: ['manual'],
      },
      sources_used: ['manual'],
      query_profile: {},
      trace_id: 'trace-old',
      latency_ms: 99,
    });

    await waitFor(() => {
      expect(screen.queryByText('Old Workspace Result')).toBeNull();
    });
  });

  it('builds workspace-aware PMS and planner links', async () => {
    ragHarness.queryWorkspaceRag.mockResolvedValueOnce({
      query: 'follow ups',
      answer_mode: 'grounded-answer',
      hits: [
        {
          source_kind: 'pms_issue',
          resource_type: 'pms_issue',
          resource_id: 'issue-1',
          workspace_id: 'hq',
          title: 'Blocked task',
          summary: null,
          score: 0.77,
          citation: null,
          owner_label: null,
          acl_summary: [],
          origin_ref: null,
          metadata: { list_id: 'list-1' },
        },
        {
          source_kind: 'planner_event',
          resource_type: 'planner_event',
          resource_id: 'event-1',
          workspace_id: 'hq',
          title: 'Review meeting',
          summary: null,
          score: 0.72,
          citation: null,
          owner_label: null,
          acl_summary: [],
          origin_ref: null,
          metadata: {},
        },
      ],
      grounded_answer: null,
      sources_used: ['pms_issue', 'planner_event'],
      query_profile: {},
      trace_id: 'trace-links',
      latency_ms: 120,
    });

    renderView();
    await screen.findByText('Docs / Manual');

    fireEvent.change(
      screen.getByLabelText('질문 또는 검색어'),
      { target: { value: 'follow ups' } },
    );
    fireEvent.click(screen.getByRole('button', { name: '검색 실행' }));

    await screen.findByText('Blocked task');

    const links = screen.getAllByRole('link', { name: '원문 열기' });
    expect(links[0]?.getAttribute('href')).toBe('/tool/pms-list-list-1?workspace=hq&issue=issue-1');
    expect(links[1]?.getAttribute('href')).toBe('/w/hq/planner?event=event-1');
  });

  it('renders a workspace guidance state when no workspace context is available', () => {
    authHarness.state.user.workspaces = [];

    renderView({ workspaceSlug: null });

    expect(
      screen.getByText('검색할 workspace를 찾을 수 없습니다. workspace를 먼저 선택한 뒤 다시 시도해주세요.'),
    ).toBeTruthy();
    expect(ragHarness.listWorkspaceRagSources).not.toHaveBeenCalled();
  });
});
