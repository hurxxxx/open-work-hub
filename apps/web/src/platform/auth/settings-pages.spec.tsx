import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { vi } from 'vitest';

import { ProfilePage } from './settings-pages';
import { i18n, syncLocale } from '@/src/platform/i18n';
import type { AuthUser } from './auth-api';

const mockListSessions = vi.fn();
const mockLogout = vi.fn();
const mockUpdatePreferences = vi.fn();
const mockChangePassword = vi.fn();
const mockRevokeSession = vi.fn();

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@aidoo.local',
    full_name: 'AIDOO Member',
    display_name: 'AIDOO Member',
    job_title: 'Platform Owner',
    status: 'active',
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    primary_org_unit: null,
    workspaces: [],
    workspace_roles: [],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
    must_change_password: false,
    last_login_at: null,
    created_at: '2026-04-08T00:00:00Z',
    ...overrides,
  };
}

vi.mock('./auth-provider', () => ({
  useAuth: () => ({
    user: buildUser(),
    logout: mockLogout,
    listSessions: mockListSessions,
    updatePreferences: mockUpdatePreferences,
    changePassword: mockChangePassword,
    revokeSession: mockRevokeSession,
  }),
}));

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

describe('ProfilePage', () => {
  beforeEach(() => {
    syncLocale('ko-KR');
    mockListSessions.mockResolvedValue([]);
    mockLogout.mockResolvedValue(undefined);
    mockUpdatePreferences.mockResolvedValue(undefined);
    mockChangePassword.mockResolvedValue(undefined);
    mockRevokeSession.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('switches sections without changing the current route', async () => {
    render(
      <MemoryRouter initialEntries={['/profile']}>
        <ProfilePage initialTab="profile" />
        <LocationDisplay />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '보안' }));

    await screen.findByText('현재 비밀번호');
    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toBe('/profile');
    });
    expect(mockListSessions).toHaveBeenCalledTimes(1);
  });

  it('saves the selected time zone from appearance settings', async () => {
    render(
      <MemoryRouter initialEntries={['/profile']}>
        <ProfilePage initialTab="appearance" />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getAllByRole('combobox')[1], {
      target: { value: 'America/New_York' },
    });

    await waitFor(() => {
      expect(mockUpdatePreferences).toHaveBeenCalledWith({ time_zone: 'America/New_York' });
    });
  });

  it('saves the selected locale from appearance settings', async () => {
    render(
      <MemoryRouter initialEntries={['/profile']}>
        <ProfilePage initialTab="appearance" />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getAllByRole('combobox')[0], {
      target: { value: 'en-US' },
    });

    await waitFor(() => {
      expect(mockUpdatePreferences).toHaveBeenCalledWith({ locale: 'en-US' });
    });
  });

  it('rolls back locale changes when saving fails', async () => {
    mockUpdatePreferences.mockRejectedValueOnce(new Error('locale save failed'));

    render(
      <MemoryRouter initialEntries={['/profile']}>
        <ProfilePage initialTab="appearance" />
      </MemoryRouter>,
    );

    const languageSelect = screen.getAllByRole('combobox')[0] as HTMLSelectElement;
    fireEvent.change(languageSelect, {
      target: { value: 'en-US' },
    });

    await screen.findByText('locale save failed');
    await waitFor(() => {
      expect(languageSelect.value).toBe('ko-KR');
      expect(i18n.language).toBe('ko-KR');
    });
  });

  it('rolls back time zone changes when saving fails', async () => {
    mockUpdatePreferences.mockRejectedValueOnce(new Error('time zone save failed'));

    render(
      <MemoryRouter initialEntries={['/profile']}>
        <ProfilePage initialTab="appearance" />
      </MemoryRouter>,
    );

    const timeZoneSelect = screen.getAllByRole('combobox')[1] as HTMLSelectElement;
    fireEvent.change(timeZoneSelect, {
      target: { value: 'America/New_York' },
    });

    await screen.findByText('time zone save failed');
    await waitFor(() => {
      expect(timeZoneSelect.value).toBe('Asia/Seoul');
    });
  });
});
