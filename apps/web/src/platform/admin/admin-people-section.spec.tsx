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
import {
  removeWorkspaceMember,
  updateAdminUser,
  type WorkspaceItem,
} from './admin-api';
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
  bulkWorkspaceMembers: vi.fn(),
  removeWorkspaceMember: vi.fn(),
  updateAdminUser: vi.fn(),
}));

vi.mock('./useAdminPeopleDirectoryController', () => ({
  useAdminPeopleDirectoryController: vi.fn(),
}));

const workspace = {
  active: true,
  description: '',
  id: 'workspace-1',
  key: 'workspace-one',
  member_count: 1,
  name: 'Workspace One',
} as WorkspaceItem;

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
  theme_preference: 'system',
  time_zone: 'Asia/Seoul',
  workspaces: [
    {
      id: workspace.id,
      name: workspace.name,
      role: 'member',
      slug: workspace.key,
    },
  ],
  workspace_roles: [],
} as AuthUser;

beforeEach(() => {
  vi.mocked(updateAdminUser).mockReset();
  vi.mocked(updateAdminUser).mockResolvedValue(member);
  vi.mocked(removeWorkspaceMember).mockReset();
  vi.mocked(removeWorkspaceMember).mockResolvedValue(undefined);
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
      workspaces: [workspace],
    },
  });
});

describe('PeopleSection workspace membership removal', () => {
  it('does not save profile or revoke access until the removal is confirmed', async () => {
    render(
      <MemoryRouter>
        <PeopleSection token="test-token" />
      </MemoryRouter>,
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'admin.console.people.editUser',
      }),
    );
    const editDialog = await screen.findByRole('dialog', {
      name: 'admin.console.people.editUser',
    });
    fireEvent.click(
      within(editDialog).getByRole('checkbox', { name: /Workspace One/ }),
    );
    fireEvent.click(
      within(editDialog).getByRole('button', { name: 'common:actions.save' }),
    );

    const confirmation = await screen.findByRole('dialog', {
      name: 'admin.console.people.workspaceRemovalConfirmTitle',
    });
    expect(updateAdminUser).not.toHaveBeenCalled();
    expect(removeWorkspaceMember).not.toHaveBeenCalled();
    fireEvent.click(
      within(confirmation).getByRole('button', {
        name: 'common:actions.cancel',
      }),
    );
    expect(updateAdminUser).not.toHaveBeenCalled();

    fireEvent.click(
      within(editDialog).getByRole('button', { name: 'common:actions.save' }),
    );
    fireEvent.click(
      within(
        await screen.findByRole('dialog', {
          name: 'admin.console.people.workspaceRemovalConfirmTitle',
        }),
      ).getByRole('button', {
        name: 'admin.console.people.workspaceRemovalConfirmAction',
      }),
    );

    await waitFor(() => expect(updateAdminUser).toHaveBeenCalledTimes(1));
    expect(removeWorkspaceMember).toHaveBeenCalledWith(
      'test-token',
      'workspace-1',
      'user',
      'user-1',
    );
  });
});
