import {
  useEffect,
  useEffectEvent,
  useRef,
  type MutableRefObject,
} from 'react';
import { useTranslation } from 'react-i18next';

import { CONVERSATIONS_UPDATED_EVENT } from '../api/conversations-api';
import type { ChatStreamState, UseChatStreamApi } from '../api/useChatStream';
import {
  buildAssistantTurnFromStream,
  buildFailedSendPatch,
  buildRewriteRollbackPatch,
  nextTurnSeq,
  resolveAssistantTurnContent,
  shouldFinalizeTerminalStream,
  shouldKeepPendingApprovalsAfterFailedSend,
  shouldKeepPendingApprovalsAfterTerminal,
  shouldRollbackRewriteBeforeAcceptance,
  type AiPendingSendSnapshot,
} from './chatbot-view-model';
import type { ChatbotViewStatePatchUpdater } from './useChatbotViewState';

function resetPendingSendRefs({
  pendingSendRef,
  pendingUserInputRef,
  pendingUserTurnIdRef,
}: {
  pendingSendRef: MutableRefObject<AiPendingSendSnapshot | null>;
  pendingUserInputRef: MutableRefObject<string>;
  pendingUserTurnIdRef: MutableRefObject<string | null>;
}) {
  pendingUserTurnIdRef.current = null;
  pendingUserInputRef.current = '';
  pendingSendRef.current = null;
}

function scheduleConversationDetailRefresh({
  clearRefreshConversationTimeout,
  conversationId,
  refreshConversationDetail,
  refreshConversationTimeoutRef,
}: {
  clearRefreshConversationTimeout: () => void;
  conversationId: string;
  refreshConversationDetail: (conversationId: string) => Promise<void>;
  refreshConversationTimeoutRef: MutableRefObject<number | null>;
}) {
  window.dispatchEvent(
    new CustomEvent(CONVERSATIONS_UPDATED_EVENT, {
      detail: { conversationId },
    }),
  );
  clearRefreshConversationTimeout();
  refreshConversationTimeoutRef.current = window.setTimeout(() => {
    void refreshConversationDetail(conversationId);
    refreshConversationTimeoutRef.current = null;
  }, 150);
}

export function useChatbotChatStreamCommit({
  chatState,
  clearRefreshConversationTimeout,
  failedPromptRecoveryRef,
  patchViewState,
  pendingSendRef,
  pendingUserInputRef,
  pendingUserTurnIdRef,
  isRunOwner,
  refreshConversationDetail,
  refreshConversationTimeoutRef,
  resetChat,
}: {
  chatState: ChatStreamState;
  clearRefreshConversationTimeout: () => void;
  failedPromptRecoveryRef: MutableRefObject<string>;
  patchViewState: (value: ChatbotViewStatePatchUpdater) => void;
  pendingSendRef: MutableRefObject<AiPendingSendSnapshot | null>;
  pendingUserInputRef: MutableRefObject<string>;
  pendingUserTurnIdRef: MutableRefObject<string | null>;
  isRunOwner: boolean;
  refreshConversationDetail: (conversationId: string) => Promise<void>;
  refreshConversationTimeoutRef: MutableRefObject<number | null>;
  resetChat: UseChatStreamApi['reset'];
}) {
  const { t } = useTranslation('apps');
  const chatStateRef = useRef(chatState);
  chatStateRef.current = chatState;

  const commitLatestChatState = useEffectEvent(() => {
    const currentChatState = chatStateRef.current;
    const status = currentChatState.status;
    if (status === 'idle' || status === 'streaming') {
      return;
    }
    const currentPendingUserInput = pendingUserInputRef.current;
    const currentPendingUserTurnId = pendingUserTurnIdRef.current;
    const pendingSend = pendingSendRef.current;
    if (!isRunOwner && currentChatState.conversationId) {
      resetPendingSendRefs({
        pendingSendRef,
        pendingUserInputRef,
        pendingUserTurnIdRef,
      });
      scheduleConversationDetailRefresh({
        clearRefreshConversationTimeout,
        conversationId: currentChatState.conversationId,
        refreshConversationDetail,
        refreshConversationTimeoutRef,
      });
      resetChat({
        keepPendingApprovals: shouldKeepPendingApprovalsAfterTerminal({
          finishReason: currentChatState.finishReason,
          pendingApprovals: currentChatState.pendingApprovals,
          status,
        }),
      });
      return;
    }
    if (
      shouldRollbackRewriteBeforeAcceptance({
        conversationId: currentChatState.conversationId,
        pendingSend,
        status,
      }) &&
      pendingSend
    ) {
      patchViewState(
        buildRewriteRollbackPatch({
          errorMessage: currentChatState.errorMessage,
          fallbackErrorMessage: t('ai.errors.responseFailed'),
          pendingSend,
        }),
      );
      resetPendingSendRefs({
        pendingSendRef,
        pendingUserInputRef,
        pendingUserTurnIdRef,
      });
      resetChat({
        keepPendingApprovals: currentChatState.pendingApprovals.length > 0,
      });
      return;
    }

    if (
      shouldFinalizeTerminalStream({
        status,
        streamOpened: currentChatState.streamOpened,
      })
    ) {
      const shouldClearFailedPrompt =
        Boolean(failedPromptRecoveryRef.current) &&
        pendingSend?.pendingUserInput.trim() ===
          failedPromptRecoveryRef.current.trim();
      patchViewState((current) => {
        const content = resolveAssistantTurnContent(
          currentChatState.contentBuffer,
          {
            status,
            errorMessage: currentChatState.errorMessage,
            finishReason: currentChatState.finishReason,
            hasArtifacts: currentChatState.artifacts.length > 0,
          },
          {
            cancelled: t('ai.message.cancelled'),
            fallbackResponseFailed: t('ai.errors.responseFailed'),
            lengthLimit: t('ai.message.lengthLimit'),
            responseFailed: t('ai.message.responseFailed'),
          },
        );
        const assistantTurn = buildAssistantTurnFromStream({
          chatState: currentChatState,
          content,
          id: `assistant-${Date.now()}`,
          seq: nextTurnSeq(current.turns),
          status,
        });
        return {
          chatError: null,
          failedPromptRecovery: shouldClearFailedPrompt
            ? ''
            : current.failedPromptRecovery,
          turns: [...current.turns, assistantTurn],
        };
      });
      resetPendingSendRefs({
        pendingSendRef,
        pendingUserInputRef,
        pendingUserTurnIdRef,
      });
      if (typeof window !== 'undefined' && currentChatState.conversationId) {
        scheduleConversationDetailRefresh({
          clearRefreshConversationTimeout,
          conversationId: currentChatState.conversationId,
          refreshConversationDetail,
          refreshConversationTimeoutRef,
        });
      }
      resetChat({
        keepPendingApprovals: shouldKeepPendingApprovalsAfterTerminal({
          finishReason: currentChatState.finishReason,
          pendingApprovals: currentChatState.pendingApprovals,
          status,
        }),
      });
    } else {
      patchViewState((current) => {
        const failedPatch = buildFailedSendPatch({
          currentInput: current.input,
          currentTurns: current.turns,
          errorMessage: currentChatState.errorMessage,
          fallbackErrorMessage: t('ai.errors.responseFailed'),
          pendingSend,
          pendingUserInput: currentPendingUserInput,
          pendingUserTurnId: currentPendingUserTurnId,
        });
        return {
          ...failedPatch,
          failedPromptRecovery:
            failedPatch.failedPromptRecovery || current.failedPromptRecovery,
        };
      });
      resetPendingSendRefs({
        pendingSendRef,
        pendingUserInputRef,
        pendingUserTurnIdRef,
      });
      resetChat({
        keepPendingApprovals: shouldKeepPendingApprovalsAfterFailedSend({
          pendingApprovals: currentChatState.pendingApprovals,
          pendingUserTurnId: currentPendingUserTurnId,
        }),
      });
    }
  });

  useEffect(() => {
    if (chatState.status === 'idle' || chatState.status === 'streaming') {
      return;
    }
    commitLatestChatState();
    // Effect Events are intentionally non-reactive; the status fields below
    // decide when the terminal stream commit runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatState.pendingApprovals.length, chatState.status]);
}
