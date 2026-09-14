import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { listConversations } from '../api/conversations-api';
import { ChatbotConversationListPanel } from './ChatbotConversationListPanel';

vi.mock('react-i18next', () => {
  const translation = {
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
  };
  return { useTranslation: () => translation };
});

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token-1' }),
}));

vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useConfirm: () => ({
    confirm: vi.fn(),
    confirmDialog: null,
  }),
  usePrompt: () => ({
    prompt: vi.fn(),
    promptDialog: null,
  }),
  useFeedback: () => ({
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
          scopeRef: 'docs',
          scopeResourceId: 'doc-1',
          title: '진행 중인 분석',
          updatedAt: '2026-07-25T10:00:00Z',
        },
        {
          createdAt: '2026-07-25T09:00:00Z',
          id: 'conversation-2',
          scopeRef: 'docs',
          scopeResourceId: 'doc-1',
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
          navigationDisabled
          routeId="chatbot.root"
          scopeRef="docs"
          scopeResourceId="doc-1"
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
    for (const button of screen.getAllByRole('button', {
      name: 'apps:ai.sidebar.conversationActions',
    })) {
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
          navigationDisabled
          pendingConversationTitle="권역별 발생 건수를 비교해줘"
          routeId="chatbot.root"
          scopeRef="docs"
          scopeResourceId="doc-1"
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText('권역별 발생 건수를 비교해줘')).toBeTruthy();
    expect(screen.queryByText('apps:ai.sidebar.noConversations')).toBeNull();
  });

  it('distinguishes the initial request from an empty conversation list', async () => {
    let finish!: () => void;
    vi.mocked(listConversations).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = () => resolve({ items: [], nextCursor: null });
        }),
    );
    render(
      <MemoryRouter>
        <ChatbotConversationListPanel activeConversationId={null} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('status')).toBeTruthy();
    expect(screen.queryByText('apps:ai.sidebar.noConversations')).toBeNull();
    finish();
    expect(
      await screen.findByText('apps:ai.sidebar.noConversations'),
    ).toBeTruthy();
    expect(screen.queryByRole('status')).toBeNull();
  });
});
