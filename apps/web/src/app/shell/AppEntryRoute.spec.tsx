import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AppEntryRoute } from './AppEntryRoute';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'token',
    user: { workspaces: [] },
  }),
}));

vi.mock('@/src/platform/workspaces/useEligibleWorkspaceSearch', () => ({
  useEligibleWorkspaceSearch: () => ({
    error: null,
    hasMore: false,
    items: [],
    loading: false,
    query: '',
    retry: vi.fn(),
    setQuery: vi.fn(),
  }),
}));

describe('AppEntryRoute workspace access', () => {
  it('fails closed before loading a known workspace app for a zero-workspace user', () => {
    render(
      <MemoryRouter initialEntries={['/launch/docs']}>
        <Routes>
          <Route
            path="/launch/:appId"
            element={
              <AppEntryRoute
                bootstrap={null}
                error={null}
                loading
                reload={vi.fn()}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'launcher.workspaceMembershipRequiredTitle',
      }),
    ).toBeTruthy();
    expect(
      screen.getByText('launcher.workspaceMembershipRequiredDescription'),
    ).toBeTruthy();
  });
});
