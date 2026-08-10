import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  listPmsUsers,
  listSpaceMembers,
  removeSpaceMember,
} from '../api/pms-api';
import { SpaceMembersModal } from './SpaceMembersModal';

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'token',
    user: { id: 'owner' },
  }),
}));

vi.mock('@ai-do/ui', async () => {
  const React = await import('react');
  type ConfirmRequest = {
    cancelLabel: string;
    confirmLabel: string;
    description: string;
    resolve: (value: boolean) => void;
    title: string;
  };

  return {
    Button: ({
      children,
      ...props
    }: ButtonHTMLAttributes<HTMLButtonElement>) => (
      <button {...props}>{children}</button>
    ),
    Dialog: ({
      actions,
      children,
      title,
    }: {
      actions?: ReactNode;
      children: ReactNode;
      title: ReactNode;
    }) => (
      <section role="dialog">
        <h2>{title}</h2>
        {children}
        {actions ? <footer>{actions}</footer> : null}
      </section>
    ),
    useConfirm: () => {
      const [request, setRequest] = React.useState<ConfirmRequest | null>(null);
      const confirm = (options: Omit<ConfirmRequest, 'resolve'>) =>
        new Promise<boolean>((resolve) => {
          setRequest({ ...options, resolve });
        });
      const close = (value: boolean) => {
        const current = request;
        setRequest(null);
        current?.resolve(value);
      };
      const confirmDialog = request ? (
        <section role="dialog">
          <h2>{request.title}</h2>
          <p>{request.description}</p>
          <button onClick={() => close(false)} type="button">
            {request.cancelLabel}
          </button>
          <button onClick={() => close(true)} type="button">
            {request.confirmLabel}
          </button>
        </section>
      ) : null;

      return { confirm, confirmDialog };
    },
  };
});

vi.mock('../api/pms-api', () => ({
  addSpaceMember: vi.fn(),
  listPmsUsers: vi.fn(),
  listSpaceMembers: vi.fn(),
  removeSpaceMember: vi.fn(),
  updateSpaceMemberRole: vi.fn(),
}));

const { translate } = vi.hoisted(() => {
  const translations: Record<string, string> = {
    'common:actions.cancel': '취소',
    'common:actions.close': '닫기',
    'pms.noMatchingUsers': '일치하는 사용자가 없습니다',
    'pms.noUsersToAdd': '추가할 사용자가 없습니다',
    'pms.searchUser': '사용자 검색',
    'pms.settings.role.admin': '관리자',
    'pms.settings.role.member': '멤버',
    'pms.settings.role.owner': '소유자',
    'pms.settings.role.viewer': '뷰어',
    'pms.spaceMembers.changeRole': '역할 변경',
    'pms.spaceMembers.inviteHint': '초대 안내',
    'pms.spaceMembers.inviteTitle': '멤버 초대',
    'pms.spaceMembers.memberActions': '멤버 작업',
    'pms.spaceMembers.memberCount': '멤버 · {{count}}',
    'pms.spaceMembers.noMembers': '아직 멤버가 없습니다.',
    'pms.spaceMembers.removeConfirmAction': '내보내기',
    'pms.spaceMembers.removeConfirmDescription':
      '{{name}}님을 이 스페이스에서 내보냅니다.',
    'pms.spaceMembers.removeConfirmTitle': '멤버를 내보낼까요?',
    'pms.spaceMembers.removeFromSpace': '스페이스에서 내보내기',
    'pms.spaceMembers.roleDescription.admin': '관리 가능',
    'pms.spaceMembers.roleDescription.member': '편집 가능',
    'pms.spaceMembers.roleDescription.owner': '소유 가능',
    'pms.spaceMembers.roleDescription.viewer': '읽기 전용',
    'pms.spaceMembers.titleSuffix': '멤버 관리',
    'pms.taskDetail.me': '나',
  };
  return {
    translate: (key: string, values?: Record<string, string | number>) => {
      let value = translations[key] ?? key;
      for (const [name, replacement] of Object.entries(values ?? {})) {
        value = value.replace(`{{${name}}}`, String(replacement));
      }
      return value;
    },
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'ko-KR', resolvedLanguage: 'ko-KR' },
    t: translate,
  }),
}));

describe('SpaceMembersModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listSpaceMembers).mockResolvedValue({
      items: [
        {
          email: 'owner@example.test',
          full_name: 'Owner User',
          role: 'owner',
          user_id: 'owner',
        },
        {
          email: 'target@example.test',
          full_name: 'Target Member',
          role: 'member',
          user_id: 'target',
        },
      ],
    });
    vi.mocked(listPmsUsers).mockResolvedValue([]);
    vi.mocked(removeSpaceMember).mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uses the app confirm dialog before removing a member from a space', async () => {
    const browserConfirm = vi
      .spyOn(window, 'confirm')
      .mockImplementation(() => {
        throw new Error('window.confirm should not be called');
      });

    render(
      <SpaceMembersModal
        canManage
        currentUserRole="owner"
        isOpen
        onClose={() => undefined}
        spaceId="space-1"
        spaceName="스페이스"
        workspaceSlug="workspace"
      />,
    );

    await screen.findByText('Target Member');

    fireEvent.click(screen.getByRole('button', { name: '멤버 작업' }));
    const removeAction = await screen.findByRole('button', {
      name: '스페이스에서 내보내기',
    });
    expect(
      removeAction
        .closest('[data-ui-floating-layer]')
        ?.classList.contains('pointer-events-auto'),
    ).toBe(true);
    fireEvent.click(removeAction);

    expect(browserConfirm).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getAllByRole('dialog')).toHaveLength(2);
    });

    fireEvent.click(screen.getByRole('button', { name: '내보내기' }));

    await waitFor(() => {
      expect(removeSpaceMember).toHaveBeenCalledWith(
        'token',
        'space-1',
        'target',
        'workspace',
      );
    });
  });
});
