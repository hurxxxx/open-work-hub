import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkspaceBootstrapProvider } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { getEligibleWorkspaces } from '@/src/platform/workspaces/workspaces-api';
import { WorkspaceContextSelector } from './WorkspaceContextSelector';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        'workspaceContext.currentUnavailable': '현재 워크스페이스 사용 불가',
        'workspaceContext.label': '이 앱의 워크스페이스',
        'workspaceContext.loadFailed':
          '워크스페이스 목록을 불러오지 못했습니다.',
        'workspaceContext.retry': '다시 시도',
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
    const search = screen.getByRole('searchbox');
    fireEvent.change(search, { target: { value: 'General' } });
    search.focus();

    fireEvent.keyDown(search, { key: 'Escape' });

    await waitFor(() => {
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
      expect(document.activeElement).toBe(trigger);
    });
    fireEvent.click(trigger);
    expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('');
  });
});
