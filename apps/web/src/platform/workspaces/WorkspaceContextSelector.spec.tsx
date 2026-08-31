import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkspaceBootstrapProvider } from '@/src/platform/workspaces/workspace-bootstrap-context';
import {
  getEligibleWorkspaces,
  setAppWorkspacePreference,
} from '@/src/platform/workspaces/workspaces-api';
import { WorkspaceContextSelector } from './WorkspaceContextSelector';

const feedback = vi.hoisted(() => ({
  error: vi.fn(),
  info: vi.fn(),
}));

vi.mock('@open-work-hub/ui', () => ({
  useFeedback: () => feedback,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        'workspaceContext.currentUnavailable': '현재 워크스페이스 사용 불가',
        'workspaceContext.label': '이 앱의 워크스페이스',
        'workspaceContext.loadFailed':
          '워크스페이스 목록을 불러오지 못했습니다.',
        'workspaceContext.retry': '다시 시도',
        'workspaceContext.searchLabel': '워크스페이스 검색',
        'workspaceContext.switchedDescription': '앱 홈으로 이동했습니다.',
        'workspaceContext.switchedTitle': 'General로 전환했습니다.',
      })[key] ?? key,
  }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));

vi.mock('@/src/platform/workspaces/workspaces-api', async (importOriginal) => ({
  ...(await importOriginal<
    typeof import('@/src/platform/workspaces/workspaces-api')
  >()),
  getEligibleWorkspaces: vi.fn(),
  setAppWorkspacePreference: vi.fn(),
}));

function LocationProbe() {
  const location = useLocation();
  return (
    <output data-testid="location">
      {location.pathname}
      {location.search}
      {location.hash}
    </output>
  );
}

describe('WorkspaceContextSelector', () => {
  beforeEach(() => {
    vi.mocked(getEligibleWorkspaces).mockRejectedValue(
      new Error('network unavailable'),
    );
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('keeps the authorized bootstrap workspace visible when discovery fails and allows retry', async () => {
    render(
      <MemoryRouter initialEntries={['/apps/docs/workspaces/administrator']}>
        <WorkspaceBootstrapProvider
          value={{
            data: {
              apps: [],
              nav: [],
              workspace: {
                id: 'workspace-administrator',
                name: 'Administrator',
                role: 'admin',
                slug: 'administrator',
              },
            },
            error: null,
            loading: false,
            reload: vi.fn(),
          }}
        >
          <Routes>
            <Route
              path="/apps/docs/workspaces/:workspaceSlug"
              element={
                <WorkspaceContextSelector
                  appId="docs"
                  workspaceSlug="administrator"
                />
              }
            />
          </Routes>
        </WorkspaceBootstrapProvider>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('button', { name: '이 앱의 워크스페이스' }).textContent,
    ).toContain('Administrator');
    expect(screen.queryByText('현재 워크스페이스 사용 불가')).toBeNull();

    expect(
      await screen.findByText('워크스페이스 목록을 불러오지 못했습니다.'),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));

    await waitFor(() => {
      expect(getEligibleWorkspaces).toHaveBeenCalledTimes(2);
    });
  });

  it('closes with Escape, clears its query, and restores trigger focus', async () => {
    render(
      <MemoryRouter initialEntries={['/apps/docs/workspaces/administrator']}>
        <WorkspaceBootstrapProvider
          value={{
            data: {
              apps: [],
              nav: [],
              workspace: {
                id: 'workspace-administrator',
                name: 'Administrator',
                role: 'admin',
                slug: 'administrator',
              },
            },
            error: null,
            loading: false,
            reload: vi.fn(),
          }}
        >
          <Routes>
            <Route
              path="/apps/docs/workspaces/:workspaceSlug"
              element={
                <WorkspaceContextSelector
                  appId="docs"
                  workspaceSlug="administrator"
                />
              }
            />
          </Routes>
        </WorkspaceBootstrapProvider>
      </MemoryRouter>,
    );

    const trigger = screen.getByRole('button', {
      name: '이 앱의 워크스페이스',
    });
    fireEvent.click(trigger);
    expect(
      screen.getByRole('listbox', { name: '이 앱의 워크스페이스' }),
    ).toBeTruthy();
    const search = screen.getByRole('combobox', {
      name: '워크스페이스 검색',
    });
    fireEvent.change(search, { target: { value: 'General' } });
    search.focus();

    fireEvent.keyDown(search, { key: 'Escape' });

    await waitFor(() => {
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
      expect(document.activeElement).toBe(trigger);
    });
    fireEvent.click(trigger);
    expect((screen.getByRole('combobox') as HTMLInputElement).value).toBe('');
  });

  it('saves an explicit choice, resets a deep route to app home, and announces it', async () => {
    vi.mocked(getEligibleWorkspaces).mockResolvedValue({
      app_id: 'docs',
      items: [
        {
          id: 'workspace-administrator',
          name: 'Administrator',
          slug: 'administrator',
        },
        {
          id: 'workspace-general',
          name: 'General',
          slug: 'general',
        },
      ],
      page: 1,
      page_size: 25,
      total: 2,
    });
    vi.mocked(setAppWorkspacePreference).mockResolvedValue({
      app_id: 'docs',
      updated_at: '2026-08-30T00:00:00Z',
      workspace_id: 'workspace-general',
    });

    render(
      <MemoryRouter
        initialEntries={[
          '/apps/docs/workspaces/administrator/documents/doc-1?view=edit#notes',
        ]}
      >
        <WorkspaceBootstrapProvider
          value={{
            data: {
              apps: [],
              nav: [],
              workspace: {
                id: 'workspace-administrator',
                name: 'Administrator',
                role: 'admin',
                slug: 'administrator',
              },
            },
            error: null,
            loading: false,
            reload: vi.fn(),
          }}
        >
          <Routes>
            <Route
              path="/apps/docs/workspaces/:workspaceSlug/*"
              element={
                <WorkspaceContextSelector
                  appId="docs"
                  workspaceSlug="administrator"
                />
              }
            />
          </Routes>
          <LocationProbe />
        </WorkspaceBootstrapProvider>
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole('button', { name: '이 앱의 워크스페이스' }),
    );
    await screen.findByRole('option', { name: /General/ });
    const combobox = screen.getByRole('combobox', {
      name: '워크스페이스 검색',
    });
    await waitFor(() => {
      expect(combobox.getAttribute('aria-activedescendant')).toMatch(
        /workspace-option-1$/,
      );
    });
    fireEvent.keyDown(combobox, { key: 'Enter' });

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe(
        '/apps/docs/workspaces/general',
      );
    });
    expect(setAppWorkspacePreference).toHaveBeenCalledWith(
      'test-token',
      'docs',
      'workspace-general',
    );
    expect(feedback.info).toHaveBeenCalledWith(
      'General로 전환했습니다.',
      '앱 홈으로 이동했습니다.',
    );
  });

  it('renders one eligible workspace as a static context without a chevron trigger', async () => {
    vi.mocked(getEligibleWorkspaces).mockResolvedValue({
      app_id: 'docs',
      items: [
        {
          id: 'workspace-administrator',
          name: 'Administrator',
          slug: 'administrator',
        },
      ],
      page: 1,
      page_size: 25,
      total: 1,
    });

    render(
      <MemoryRouter>
        <WorkspaceBootstrapProvider
          value={{
            data: {
              apps: [],
              nav: [],
              workspace: {
                id: 'workspace-administrator',
                name: 'Administrator',
                role: 'admin',
                slug: 'administrator',
              },
            },
            error: null,
            loading: false,
            reload: vi.fn(),
          }}
        >
          <WorkspaceContextSelector
            appId="docs"
            workspaceSlug="administrator"
          />
        </WorkspaceBootstrapProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.queryByRole('button', { name: '이 앱의 워크스페이스' }),
      ).toBeNull();
    });
    expect(screen.getByLabelText('이 앱의 워크스페이스').textContent).toBe(
      'Administrator',
    );
  });

  it('closes when focus moves outside the selector surface', async () => {
    render(
      <MemoryRouter>
        <WorkspaceBootstrapProvider
          value={{
            data: {
              apps: [],
              nav: [],
              workspace: {
                id: 'workspace-administrator',
                name: 'Administrator',
                role: 'admin',
                slug: 'administrator',
              },
            },
            error: null,
            loading: false,
            reload: vi.fn(),
          }}
        >
          <WorkspaceContextSelector
            appId="docs"
            workspaceSlug="administrator"
          />
        </WorkspaceBootstrapProvider>
      </MemoryRouter>,
    );

    const trigger = screen.getByRole('button', {
      name: '이 앱의 워크스페이스',
    });
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    fireEvent.mouseDown(document.body);
    await waitFor(() => {
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
    });
  });
});
