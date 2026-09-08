import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getConversation,
  type ConversationDetail,
} from '../api/conversations-api';
import { useChatbotConversationHydration } from './useChatbotConversationHydration';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../api/conversations-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/conversations-api')>()),
  getConversation: vi.fn(),
}));

describe('useChatbotConversationHydration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the pending question when remount hydration races an empty persisted conversation', async () => {
    vi.mocked(getConversation).mockResolvedValue({
      id: 'conversation-1',
      livePendingApproval: null,
      scopeRef: 'docs',
      scopeResourceId: 'workspace',
      turns: [],
    } as ConversationDetail);
    const patchViewState = vi.fn();

    renderHook(() =>
      useChatbotConversationHydration({
        abortHydrateRef: { current: null },
        authStatus: 'authenticated',
        consumedDraftRef: { current: null },
        locationDraft: null,
        locationDraftSourceKey: null,
        patchViewState,
        pendingDraft: null,
        pendingDraftSourceKey: null,
        pendingSendRef: { current: null },
        pendingUserContentRef: {
          current: '권역별 발생 건수를 비교해줘',
        },
        pendingUserInputRef: { current: '' },
        pendingUserTurnIdRef: { current: null },
        replacePendingApprovals: vi.fn(),
        resetChat: vi.fn(),
        routeConversationId: 'conversation-1',
        routeDraft: null,
        skipHydrationConversationIdRef: { current: null },
        skipNextHydrationResetRef: { current: false },
        syncLivePendingApproval: vi.fn(),
        token: 'token-1',
      }),
    );

    await waitFor(() => {
      expect(patchViewState).toHaveBeenCalledWith(
        expect.objectContaining({
          activeConversationId: 'conversation-1',
          turns: [
            expect.objectContaining({
              content: '권역별 발생 건수를 비교해줘',
              role: 'user',
            }),
          ],
        }),
      );
    });
  });
});
