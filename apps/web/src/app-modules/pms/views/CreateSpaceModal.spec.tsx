import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { CreateSpaceModal } from './CreateSpaceModal';

const mockUseAuth = vi.fn();
const mockCreateSpace = vi.fn();
const mockListPmsUsers = vi.fn();
const mockAddSpaceMember = vi.fn();

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

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../api/pms-api', () => ({
  addSpaceMember: (...args: unknown[]) => mockAddSpaceMember(...args),
  createSpace: (...args: unknown[]) => mockCreateSpace(...args),
  listPmsUsers: (...args: unknown[]) => mockListPmsUsers(...args),
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
    workspaces: [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'HQ',
        role: 'member',
      },
    ],
    workspace_roles: [
      {
        workspace_id: 'workspace-pms',
        key: 'pms',
        name: 'PMS Workspace',
        role: 'member',
      },
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
    mockListPmsUsers.mockResolvedValue([]);
    mockAddSpaceMember.mockResolvedValue(undefined);
  });

  it('disables creation for users without workspace access', () => {
    mockUseAuth.mockReturnValue({
      token: 'member-token',
      user: buildUser({
        workspaces: [],
      }),
    });

    render(
      <CreateSpaceModal
        isOpen
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('워크스페이스 접근 권한이 없어 스페이스를 생성할 수 없습니다.')).toBeTruthy();
    expect((screen.getByRole('button', { name: '스페이스 만들기' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('creates a space for users with workspace access', async () => {
    mockUseAuth.mockReturnValue({
      token: 'workspace-member-token',
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

    fireEvent.change(screen.getByPlaceholderText('예: Engineering'), {
      target: { value: 'Engineering' },
    });
    fireEvent.change(screen.getByPlaceholderText('스페이스에 대한 간단한 설명'), {
      target: { value: 'Delivery team' },
    });
    fireEvent.click(screen.getByRole('button', { name: '스페이스 만들기' }));

    await waitFor(() => {
      expect(mockCreateSpace).toHaveBeenCalledWith('workspace-member-token', {
        name: 'Engineering',
        description: 'Delivery team',
      });
    });
    expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 'space-1' }));
    expect(onClose).toHaveBeenCalled();
  });
});
