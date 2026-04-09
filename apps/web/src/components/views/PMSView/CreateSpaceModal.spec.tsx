import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import type { AuthUser } from '@/src/domains/auth/auth-api';
import { CreateSpaceModal } from './CreateSpaceModal';

const mockUseAuth = vi.fn();
const mockCreateSpace = vi.fn();

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

vi.mock('@/src/domains/pms/pms-api', () => ({
  createSpace: (...args: unknown[]) => mockCreateSpace(...args),
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
    app_access: [
      { app: 'pms', workspace_id: 'workspace-pms', workspace_key: 'pms', workspace_name: 'PMS Workspace', role: 'member' },
    ],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
    must_change_password: false,
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
      user: buildUser({ app_access: [] }),
    });

    render(
      <CreateSpaceModal
        isOpen
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('PMS 앱 접근 권한이 없어 스페이스를 생성할 수 없습니다.')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Create Space' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('creates a space for users with PMS app access', async () => {
    mockUseAuth.mockReturnValue({
      token: 'pms-member-token',
      user: buildUser(),
    });
    mockCreateSpace.mockResolvedValue({
      id: 'space-1',
      workspace_id: 'workspace-pms',
      workspace_key: 'pms',
      key: 'eng',
      name: 'Engineering',
      description: 'Delivery team',
      member_count: 1,
      current_user_role: 'owner',
      created_at: '2026-04-08T00:00:00Z',
      updated_at: '2026-04-08T00:00:00Z',
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
      expect(mockCreateSpace).toHaveBeenCalledWith('pms-member-token', {
        name: 'Engineering',
        description: 'Delivery team',
      });
    });
    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 'space-1' }));
    expect(onClose).toHaveBeenCalled();
  });
});
