import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import type { AuthUser } from '@/src/domains/auth/auth-api';
import { CreateSpaceModal } from './CreateSpaceModal';

const mockUseAuth = vi.fn();
const mockCreateTeam = vi.fn();

vi.mock('@aidoo/ui', () => ({
  Dialog: ({
    open,
    title,
    children,
    actions,
  }: {
    open: boolean;
    title: string;
    children?: ReactNode;
    actions?: ReactNode;
  }) => (open ? (
    <div>
      <h2>{title}</h2>
      <div>{children}</div>
      <div>{actions}</div>
    </div>
  ) : null),
  Button: ({
    children,
    onClick,
    disabled,
  }: {
    children?: ReactNode;
    onClick?: () => void;
    disabled?: boolean;
  }) => (
    <button disabled={disabled} onClick={onClick} type="button">
      {children}
    </button>
  ),
}));

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/src/domains/admin/admin-api', () => ({
  createTeam: (...args: unknown[]) => mockCreateTeam(...args),
}));

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@aidoo.local',
    full_name: 'AIDOO Member',
    display_name: 'AIDOO Member',
    status: 'active',
    theme_preference: 'system',
    primary_org_unit: null,
    workspace_roles: [
      {
        workspace_id: 'workspace-pms',
        key: 'pms',
        name: 'PMS Workspace',
        role: 'member',
      },
    ],
    group_ids: [],
    group_slugs: [],
    permissions: [],
    visible_features: ['nav.pms'],
    must_change_password: false,
    is_admin: false,
    last_login_at: null,
    created_at: '2026-04-08T00:00:00Z',
    ...overrides,
  };
}

describe('CreateSpaceModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('disables creation for users without workspace admin scope', () => {
    mockUseAuth.mockReturnValue({
      token: 'member-token',
      user: buildUser(),
    });

    render(
      <CreateSpaceModal
        isOpen
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('이 워크스페이스에서 스페이스를 만들 권한이 없습니다.')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Create Space' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('creates a space for workspace admins', async () => {
    mockUseAuth.mockReturnValue({
      token: 'workspace-admin-token',
      user: buildUser({
        workspace_roles: [
          {
            workspace_id: 'workspace-pms',
            key: 'pms',
            name: 'PMS Workspace',
            role: 'workspace_admin',
          },
        ],
      }),
    });
    mockCreateTeam.mockResolvedValue({
      id: 'team-1',
      workspace_id: 'workspace-pms',
      workspace_key: 'pms',
      key: 'eng',
      name: 'Engineering',
      description: 'Delivery team',
      active: true,
      member_count: 1,
    });

    const onClose = vi.fn();
    const onCreated = vi.fn();

    render(
      <CreateSpaceModal
        isOpen
        onClose={onClose}
        onCreated={onCreated}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText('e.g. Engineering'), {
      target: { value: 'Engineering' },
    });
    fireEvent.change(screen.getByPlaceholderText('스페이스에 대한 간단한 설명'), {
      target: { value: 'Delivery team' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create Space' }));

    await waitFor(() => {
      expect(mockCreateTeam).toHaveBeenCalledWith('workspace-admin-token', 'workspace-pms', {
        name: 'Engineering',
        description: 'Delivery team',
      });
    });
    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 'team-1' }));
    expect(onClose).toHaveBeenCalled();
  });
});
