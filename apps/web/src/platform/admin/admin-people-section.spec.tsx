import type { ReactNode } from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { updateAdminUser } from './admin-api';
import { PeopleSection } from './admin-people-section';
import { useAdminPeopleDirectoryController } from './useAdminPeopleDirectoryController';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en-US', resolvedLanguage: 'en-US' },
    t: (key: string) => key,
  }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    hasPermission: () => false,
    switchSession: vi.fn(),
    user: { id: 'platform-admin', time_zone: 'UTC' },
  }),
}));

vi.mock('@open-work-hub/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@open-work-hub/ui')>()),
  DropdownMenu: ({
    items,
  }: {
    items: Array<{
      id: string;
      label: ReactNode;
      disabled?: boolean;
      onSelect?: () => void;
    }>;
  }) => (
    <div>
      {items.map((item) => (
        <button
          disabled={item.disabled}
          key={item.id}
          onClick={item.onSelect}
          type="button"
        >
          {item.label}
        </button>
      ))}
    </div>
  ),
}));

vi.mock('./admin-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./admin-api')>()),
  updateAdminUser: vi.fn(),
}));

vi.mock('./useAdminPeopleDirectoryController', () => ({
  useAdminPeopleDirectoryController: vi.fn(),
}));

const member = {
  app_bar_layout: { pinned_app_ids: [] },
  date_format: 'korean',
  display_name: 'Member',
  email: 'member@example.com',
  full_name: 'Workspace Member',
  id: 'user-1',
  last_login_at: null,
  locale: 'ko-KR',
  login_id: 'member',
  must_change_password: false,
  status: 'active',
  system_roles: [],
  group_ids: [],
  managed_organization_unit_ids: [],
  theme_preference: 'system',
  time_zone: 'Asia/Seoul',
} as AuthUser;

beforeEach(() => {
  vi.mocked(updateAdminUser).mockReset();
  vi.mocked(updateAdminUser).mockResolvedValue(member);
  vi.mocked(useAdminPeopleDirectoryController).mockReturnValue({
    actions: {
      organizationUnitChanged: vi.fn(),
      reloadUsers: vi.fn().mockResolvedValue(undefined),
      searchChanged: vi.fn(),
      setIncludeDescendants: vi.fn(),
      setPage: vi.fn(),
      setPageSize: vi.fn(),
      setUnassignedOnly: vi.fn(),
    },
    state: {
      error: null,
      includeDescendants: true,
      isLoadingUsers: false,
      organizationUnitId: '',
      organizationUnits: [],
      page: 1,
      pageSize: 20,
      search: '',
      totalUsers: 1,
      unassignedOnly: false,
      users: [member],
    },
  });
});

describe('PeopleSection account editing', () => {
  it('saves profile and account status in one authorized update', async () => {
    render(
      <MemoryRouter>
        <PeopleSection token="test-token" />
      </MemoryRouter>,
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'admin.console.people.editUser' }),
    );
    const dialog = await screen.findByRole('dialog', {
      name: 'admin.console.people.editUser',
    });
    fireEvent.change(
      within(dialog).getByLabelText('admin.console.people.fullName'),
      { target: { value: 'Renamed Member' } },
    );
    fireEvent.change(
      within(dialog).getByLabelText('admin.console.people.columns.status'),
      { target: { value: 'suspended' } },
    );
    expect(updateAdminUser).not.toHaveBeenCalled();
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'common:actions.save' }),
    );
    await waitFor(() => expect(updateAdminUser).toHaveBeenCalledTimes(1));
    expect(updateAdminUser).toHaveBeenCalledWith(
      'test-token',
      'user-1',
      expect.objectContaining({
        full_name: 'Renamed Member',
        status: 'suspended',
      }),
    );
    expect(vi.mocked(updateAdminUser).mock.calls[0]?.[2]).not.toHaveProperty(
      'workspace_ids',
    );
  });
});
