import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { listConversations } from '../api/conversations-api';
import { ChatbotConversationListPanel } from './ChatbotConversationListPanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        'apps:ai.message.typing': '답변 작성 중',
        'apps:ai.sidebar.deleteConversation': '대화 삭제',
        'apps:ai.sidebar.historyToday': '오늘',
        'apps:ai.sidebar.newConversation': '새 대화',
        'apps:ai.sidebar.recentConversations': '최근 대화',
        'apps:ai.sidebar.renameConversation': '대화 이름 변경',
        'apps:ai.sidebar.searchConversations': '대화 검색',
      })[key] ?? key,
  }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token-1' }),
}));

vi.mock('@ai-do/ui', () => ({
  useConfirm: () => ({
    confirm: vi.fn(),
    confirmDialog: null,
  }),
  usePrompt: () => ({
    prompt: vi.fn(),
    promptDialog: null,
  }),
  useToast: () => ({
    error: vi.fn(),
    success: vi.fn(),
  }),
}));

vi.mock('../api/conversations-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/conversations-api')>()),
  listConversations: vi.fn(),
}));

describe('ChatbotConversationListPanel', () => {
  beforeEach(() => {
    vi.mocked(listConversations).mockResolvedValue({
      items: [
        {
          createdAt: '2026-07-25T10:00:00Z',
          id: 'conversation-1',
          scopeRef: 'legacy_issues',
          scopeResourceId: 'workspace',
          title: '진행 중인 분석',
          updatedAt: '2026-07-25T10:00:00Z',
        },
        {
          createdAt: '2026-07-25T09:00:00Z',
          id: 'conversation-2',
          scopeRef: 'legacy_issues',
          scopeResourceId: 'workspace',
          title: '다른 분석',
          updatedAt: '2026-07-25T09:00:00Z',
        },
      ],
      nextCursor: null,
    });
  });

  it('prevents switching or deleting conversations while a response is running', async () => {
    render(
      <MemoryRouter>
        <ChatbotConversationListPanel
          activeConversationId="conversation-1"
          currentWorkspaceSlug="research"
          navigationDisabled
          routeAppId="legacy-issues"
          routePathSuffix="assistant"
          scopeRef="legacy_issues"
          scopeResourceId="workspace"
        />
      </MemoryRouter>,
    );

    const otherConversation = (await screen.findByText('다른 분석')).closest(
      'button',
    );
    expect(otherConversation?.hasAttribute('disabled')).toBe(true);
    expect(
      screen.getByRole('button', { name: '새 대화' }).hasAttribute('disabled'),
    ).toBe(true);
    for (const button of screen.getAllByRole('button', { name: '대화 삭제' })) {
      expect(button.hasAttribute('disabled')).toBe(true);
    }
  });

  it('shows the pending question before the server conversation appears', async () => {
    vi.mocked(listConversations).mockResolvedValue({
      items: [],
      nextCursor: null,
    });

    render(
      <MemoryRouter>
        <ChatbotConversationListPanel
          activeConversationId={null}
          currentWorkspaceSlug="research"
          navigationDisabled
          pendingConversationTitle="권역별 발생 건수를 비교해줘"
          routeAppId="legacy-issues"
          routePathSuffix="assistant"
          scopeRef="legacy_issues"
          scopeResourceId="workspace"
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText('권역별 발생 건수를 비교해줘')).toBeTruthy();
    expect(screen.queryByText('apps:ai.sidebar.noConversations')).toBeNull();
  });
});
