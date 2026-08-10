import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CHAT_STREAM_INITIAL_STATE } from '../api/chat-stream-state';
import { useChatbotChatStreamCommit } from './useChatbotChatStreamCommit';

describe('useChatbotChatStreamCommit', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('reloads the persisted result when a background run finishes after route remount', () => {
    vi.useFakeTimers();
    const patchViewState = vi.fn();
    const refreshConversationDetail = vi.fn().mockResolvedValue(undefined);
    const resetChat = vi.fn();
    const refreshConversationTimeoutRef = { current: null as number | null };

    renderHook(() =>
      useChatbotChatStreamCommit({
        chatState: {
          ...CHAT_STREAM_INITIAL_STATE,
          contentBuffer: '완료된 보고서',
          conversationId: 'conversation-1',
          finishReason: 'stop',
          status: 'done',
          streamOpened: true,
          transport: 'stream',
        },
        clearRefreshConversationTimeout: vi.fn(),
        failedPromptRecoveryRef: { current: '' },
        isRunOwner: false,
        patchViewState,
        pendingSendRef: { current: null },
        pendingUserInputRef: { current: '' },
        pendingUserTurnIdRef: { current: null },
        refreshConversationDetail,
        refreshConversationTimeoutRef,
        resetChat,
      }),
    );

    expect(patchViewState).not.toHaveBeenCalled();
    expect(resetChat).toHaveBeenCalledTimes(1);

    act(() => {
      vi.runAllTimers();
    });
    expect(refreshConversationDetail).toHaveBeenCalledWith('conversation-1');
  });
});
