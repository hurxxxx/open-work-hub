import type { ReactNode } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { listWorkspaceBindings } from './admin-api';
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
    items,
  }: {
    items: Array<{ id: string; label: ReactNode }>;
  }) => (
    <div>
      {items.map((item) => (
        <div key={item.id}>{item.label}</div>
      ))}
    </div>
  ),
}));

vi.mock('./admin-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./admin-api')>()),
  listWorkspaceBindings: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(listWorkspaceBindings).mockResolvedValue([]);
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
    expect(
      screen.queryByText('common:actions.deletePermanently'),
    ).toBeNull();
  });
});
