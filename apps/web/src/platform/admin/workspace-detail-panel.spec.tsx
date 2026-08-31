import type { ReactNode } from 'react';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  bulkWorkspaceMembers,
  listWorkspaceBindings,
  listWorkspaceMembers,
  removeWorkspaceMember,
  type WorkspaceBindingItem,
} from './admin-api';
import { WorkspaceDetailPanel } from './workspace-detail-panel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en-US', resolvedLanguage: 'en-US' },
    t: (key: string) => key,
  }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ user: { time_zone: 'UTC' } }),
}));

vi.mock('@open-work-hub/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@open-work-hub/ui')>()),
  DropdownMenu: ({
    trigger,
    items,
  }: {
    trigger: ReactNode;
    items: Array<{ id: string; label: ReactNode; onSelect?: () => void }>;
  }) => (
    <div>
      {trigger}
      {items.map((item) => (
        <button key={item.id} onClick={item.onSelect} type="button">
          {item.label}
        </button>
      ))}
    </div>
  ),
}));

vi.mock('./admin-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./admin-api')>()),
  bulkWorkspaceMembers: vi.fn(),
  listWorkspaceBindings: vi.fn(),
  listWorkspaceMembers: vi.fn(),
  removeWorkspaceMember: vi.fn(),
}));

const currentBinding: WorkspaceBindingItem = {
  role: 'admin',
  subject_id: 'user-1',
  subject_label: 'Current Admin',
  subject_secondary: 'admin@example.com',
  subject_type: 'user',
};
const memberBinding: WorkspaceBindingItem = {
  role: 'member',
  subject_id: 'user-2',
  subject_label: 'Member Two',
  subject_secondary: 'member@example.com',
  subject_type: 'user',
};

beforeEach(() => {
  vi.mocked(listWorkspaceBindings).mockResolvedValue([
    currentBinding,
    memberBinding,
  ]);
  vi.mocked(listWorkspaceMembers).mockResolvedValue({
    items: [
      { ...currentBinding, last_login_at: null, user_status: 'active' },
      { ...memberBinding, last_login_at: null, user_status: 'active' },
    ],
    page: 1,
    page_size: 25,
    pending_count: 0,
    role_counts: { admin: 1, member: 1 },
    total: 2,
    user_count: 2,
  });
  vi.mocked(removeWorkspaceMember).mockResolvedValue(undefined);
  vi.mocked(bulkWorkspaceMembers).mockResolvedValue({
    failed: [],
    succeeded: 1,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('WorkspaceDetailPanel lifecycle actions', () => {
  it('offers archive recovery without a hard-delete action', async () => {
    render(
      <WorkspaceDetailPanel
        workspace={{
          active: false,
          created_at: null,
          description: '',
          doc_count: 0,
          id: 'workspace-1',
          key: 'workspace-one',
          meeting_count: 0,
          member_count: 1,
          name: 'Workspace One',
          team_count: 0,
          updated_at: null,
        }}
        token="test-token"
        currentUserId="user-1"
        capabilities={{
          canEditProfile: true,
          canManageMembers: true,
          canArchive: true,
          canBrowseDirectory: true,
        }}
        onWorkspaceChanged={vi.fn()}
        flashSuccess={vi.fn()}
        flashError={vi.fn()}
      />,
    );
    await waitFor(() => expect(listWorkspaceBindings).toHaveBeenCalled());

    expect(screen.getByText('admin.workspace.reactivateAction')).toBeTruthy();
    expect(screen.queryByText('common:actions.deletePermanently')).toBeNull();
  });

  it('requires explicit confirmation before removing a preview member', async () => {
    vi.mocked(listWorkspaceBindings).mockResolvedValue([memberBinding]);
    renderPanel();
    await screen.findByText('Member Two');

    const actionsButton = screen.getByRole('button', {
      name: 'admin.workspace.members.actions',
    });
    actionsButton.focus();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'admin.workspace.members.removeFromWorkspace',
      }),
    );
    const confirmation = await screen.findByRole('dialog', {
      name: 'admin.workspace.members.removeConfirmTitle',
    });
    fireEvent.click(
      within(confirmation).getByRole('button', {
        name: 'common:actions.cancel',
      }),
    );
    expect(removeWorkspaceMember).not.toHaveBeenCalled();
    await waitFor(() => expect(document.activeElement).toBe(actionsButton));

    fireEvent.click(
      screen.getByRole('button', {
        name: 'admin.workspace.members.removeFromWorkspace',
      }),
    );
    fireEvent.click(
      within(
        await screen.findByRole('dialog', {
          name: 'admin.workspace.members.removeConfirmTitle',
        }),
      ).getByRole('button', {
        name: 'admin.workspace.members.removeConfirmAction',
      }),
    );

    await waitFor(() =>
      expect(removeWorkspaceMember).toHaveBeenCalledWith(
        'test-token',
        'workspace-1',
        'user',
        'user-2',
      ),
    );
  });

  it('requires confirmation for single and bulk removals in the members drawer', async () => {
    renderPanel();
    await waitFor(() => expect(listWorkspaceBindings).toHaveBeenCalled());
    fireEvent.click(
      screen.getByRole('button', { name: 'admin.workspace.members.manage' }),
    );
    const drawer = await screen.findByRole('dialog', {
      name: 'admin.workspace.members.manageTitle',
    });
    await within(drawer).findByText('Member Two');

    fireEvent.click(
      within(drawer).getByRole('button', {
        name: 'admin.workspace.members.removeFromWorkspace',
      }),
    );
    const singleConfirmation = await screen.findByRole('dialog', {
      name: 'admin.workspace.members.removeConfirmTitle',
    });
    fireEvent.click(
      within(singleConfirmation).getByRole('button', {
        name: 'common:actions.cancel',
      }),
    );
    expect(removeWorkspaceMember).not.toHaveBeenCalled();

    fireEvent.click(
      within(drawer).getByRole('button', {
        name: 'admin.workspace.members.removeFromWorkspace',
      }),
    );
    fireEvent.click(
      within(
        await screen.findByRole('dialog', {
          name: 'admin.workspace.members.removeConfirmTitle',
        }),
      ).getByRole('button', {
        name: 'admin.workspace.members.removeConfirmAction',
      }),
    );
    await waitFor(() => expect(removeWorkspaceMember).toHaveBeenCalledTimes(1));

    vi.mocked(removeWorkspaceMember).mockClear();
    const reloadedDrawer = screen.getByRole('dialog', {
      name: 'admin.workspace.members.manageTitle',
    });
    fireEvent.click(
      within(reloadedDrawer).getByRole('checkbox', {
        name: 'admin.workspace.members.selectMember',
      }),
    );
    const bulkDeleteButton = within(reloadedDrawer).getByRole('button', {
      name: 'common:actions.delete',
    });
    expect(bulkDeleteButton.className).toContain('text-app-danger-text');
    fireEvent.click(bulkDeleteButton);
    const bulkConfirmation = await screen.findByRole('dialog', {
      name: 'admin.workspace.members.bulkRemoveConfirmTitle',
    });
    fireEvent.click(
      within(bulkConfirmation).getByRole('button', {
        name: 'common:actions.cancel',
      }),
    );
    expect(bulkWorkspaceMembers).not.toHaveBeenCalled();

    fireEvent.click(bulkDeleteButton);
    fireEvent.click(
      within(
        await screen.findByRole('dialog', {
          name: 'admin.workspace.members.bulkRemoveConfirmTitle',
        }),
      ).getByRole('button', {
        name: 'admin.workspace.members.removeConfirmAction',
      }),
    );
    await waitFor(() =>
      expect(bulkWorkspaceMembers).toHaveBeenCalledWith(
        'test-token',
        'workspace-1',
        {
          action: 'remove',
          subjects: [{ subject_id: 'user-2', subject_type: 'user' }],
        },
      ),
    );
  });

  it('returns focus to the member actions button after cancelling removal', async () => {
    renderPanel();
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'admin.workspace.members.manage',
      }),
    );
    const drawer = await screen.findByRole('dialog', {
      name: 'admin.workspace.members.manageTitle',
    });
    await within(drawer).findByText('Member Two');
    const actionsButton = within(drawer).getByRole('button', {
      name: 'admin.workspace.members.actions',
    });
    actionsButton.focus();

    fireEvent.click(
      within(drawer).getByRole('button', {
        name: 'admin.workspace.members.removeFromWorkspace',
      }),
    );
    fireEvent.click(
      within(
        await screen.findByRole('dialog', {
          name: 'admin.workspace.members.removeConfirmTitle',
        }),
      ).getByRole('button', { name: 'common:actions.cancel' }),
    );

    await waitFor(() => expect(document.activeElement).toBe(actionsButton));
  });
});

function renderPanel() {
  return render(
    <WorkspaceDetailPanel
      workspace={{
        active: true,
        created_at: null,
        description: '',
        doc_count: 0,
        id: 'workspace-1',
        key: 'workspace-one',
        meeting_count: 0,
        member_count: 2,
        name: 'Workspace One',
        team_count: 0,
        updated_at: null,
      }}
      token="test-token"
      currentUserId="user-1"
      capabilities={{
        canEditProfile: true,
        canManageMembers: true,
        canArchive: true,
        canBrowseDirectory: true,
      }}
      onWorkspaceChanged={vi.fn()}
      flashSuccess={vi.fn()}
      flashError={vi.fn()}
    />,
  );
}
