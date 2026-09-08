import { useEffect, type MutableRefObject } from 'react';
import { useTranslation } from 'react-i18next';

import type { AuthSessionStatus } from '@/src/platform/auth/auth-context';
import {
  getConversation,
  type ConversationDetail,
} from '../api/conversations-api';
import type { UseChatStreamApi } from '../api/useChatStream';
import {
  buildFreshChatDraftPatch,
  buildHydratedConversationDraftPatch,
  mergePendingUserTurn,
  normalizeConversationDetail,
  type AiPendingSendSnapshot,
  type LivePendingApprovalInput,
} from './chatbot-view-model';
import type {
  ChatbotViewStatePatch,
  ChatbotViewStatePatchUpdater,
} from './useChatbotViewState';

function buildConversationResetPatch(
  patch: ChatbotViewStatePatch = {},
): ChatbotViewStatePatch {
  return {
    activeConversationId: null,
    approvalAction: null,
    approvalError: null,
    chatError: null,
    editingText: '',
    editingTurnId: null,
    failedPromptRecovery: '',
    input: '',
    isLoadingConversation: false,
    scopeInfo: null,
    turns: [],
    ...patch,
  };
}

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

export function useChatbotConversationHydration({
  abortHydrateRef,
  authStatus,
  consumedDraftRef,
  locationDraft,
  locationDraftSourceKey,
  pendingUserContentRef,
  patchViewState,
  pendingDraft,
  pendingDraftSourceKey,
  pendingSendRef,
  pendingUserInputRef,
  pendingUserTurnIdRef,
  replacePendingApprovals,
  resetChat,
  routeConversationId,
  routeDraft,
  skipHydrationConversationIdRef,
  skipNextHydrationResetRef,
  syncLivePendingApproval,
  token,
}: {
  abortHydrateRef: MutableRefObject<AbortController | null>;
  authStatus: AuthSessionStatus;
  consumedDraftRef: MutableRefObject<string | null>;
  locationDraft: string | null;
  locationDraftSourceKey: string | null;
  pendingUserContentRef: MutableRefObject<string | null>;
  patchViewState: (value: ChatbotViewStatePatchUpdater) => void;
  pendingDraft: string | null;
  pendingDraftSourceKey: string | null;
  pendingSendRef: MutableRefObject<AiPendingSendSnapshot | null>;
  pendingUserInputRef: MutableRefObject<string>;
  pendingUserTurnIdRef: MutableRefObject<string | null>;
  replacePendingApprovals: UseChatStreamApi['replacePendingApprovals'];
  resetChat: UseChatStreamApi['reset'];
  routeConversationId: string | null;
  routeDraft: string | null;
  skipHydrationConversationIdRef: MutableRefObject<string | null>;
  skipNextHydrationResetRef: MutableRefObject<boolean>;
  syncLivePendingApproval: (
    livePendingApproval: LivePendingApprovalInput,
  ) => void;
  token: string | null;
}) {
  const { t } = useTranslation('apps');

  useEffect(() => {
    if (authStatus === 'bootstrapping') {
      return;
    }

    if (skipNextHydrationResetRef.current) {
      skipNextHydrationResetRef.current = false;
      return;
    }
    abortHydrateRef.current?.abort();

    if (
      routeConversationId &&
      routeConversationId === skipHydrationConversationIdRef.current
    ) {
      skipHydrationConversationIdRef.current = null;
      patchViewState({
        activeConversationId: routeConversationId,
        chatError: null,
        isLoadingConversation: false,
      });
      return;
    }

    resetPendingSendRefs({
      pendingSendRef,
      pendingUserInputRef,
      pendingUserTurnIdRef,
    });
    // Conversation hydration is a view concern. A scoped chat stream may be
    // continuing in the shared runtime while this route remounts, so loading
    // the route must not cancel that run.
    resetChat({ preserveActiveRun: true });
    const pendingUserContent = pendingUserContentRef.current;

    if (!routeConversationId) {
      const nextViewState = buildConversationResetPatch({
        turns: mergePendingUserTurn({
          conversationId: null,
          pendingUserContent,
          turns: [],
        }),
      });

      const draftPatch = buildFreshChatDraftPatch({
        consumedDraftSourceKey: consumedDraftRef.current,
        hasRouteDraft: Boolean(routeDraft),
        pendingDraft,
        pendingDraftSourceKey,
      });
      if (draftPatch) {
        Object.assign(nextViewState, draftPatch);
      }
      patchViewState(nextViewState);
      return;
    }

    if (!token) {
      patchViewState(buildConversationResetPatch());
      return;
    }

    const controller = new AbortController();
    abortHydrateRef.current = controller;
    patchViewState(
      buildConversationResetPatch({ isLoadingConversation: true }),
    );
    getConversation(token, routeConversationId, {})
      .then((detail: ConversationDetail) => {
        if (controller.signal.aborted) {
          return;
        }
        const normalizedDetail = normalizeConversationDetail(detail);
        const nextViewState: ChatbotViewStatePatch = {
          activeConversationId: normalizedDetail.activeConversationId,
          chatError: null,
          scopeInfo: normalizedDetail.scopeInfo,
          turns: mergePendingUserTurn({
            conversationId: normalizedDetail.activeConversationId,
            pendingUserContent,
            turns: normalizedDetail.turns,
          }),
        };
        syncLivePendingApproval(detail.livePendingApproval);
        const draftPatch = buildHydratedConversationDraftPatch({
          consumedDraftSourceKey: consumedDraftRef.current,
          detail,
          locationDraft,
          locationDraftSourceKey,
        });
        if (draftPatch) {
          Object.assign(nextViewState, draftPatch);
        }
        patchViewState(nextViewState);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        replacePendingApprovals([]);
        patchViewState({
          activeConversationId: null,
          chatError:
            error instanceof Error
              ? error.message
              : t('ai.view.conversationLoadFailed'),
          turns: mergePendingUserTurn({
            conversationId: routeConversationId,
            pendingUserContent,
            turns: [],
          }),
        });
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          patchViewState({ isLoadingConversation: false });
        }
      });

    return () => {
      controller.abort();
    };
  }, [
    abortHydrateRef,
    authStatus,
    consumedDraftRef,
    locationDraft,
    locationDraftSourceKey,
    patchViewState,
    pendingDraft,
    pendingDraftSourceKey,
    pendingUserContentRef,
    pendingSendRef,
    pendingUserInputRef,
    pendingUserTurnIdRef,
    replacePendingApprovals,
    resetChat,
    routeConversationId,
    routeDraft,
    skipHydrationConversationIdRef,
    skipNextHydrationResetRef,
    syncLivePendingApproval,
    t,
    token,
  ]);
}
