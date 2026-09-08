import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import type { PendingApproval } from '../api/agent-events';
import {
  AiApiError,
  abandonAiApproval,
  resolveAiApproval,
} from '../api/chatbot-api';
import type { UseChatStreamApi } from '../api/useChatStream';
import {
  applyPendingApprovalDecision,
  buildAiApprovalResolveRequest,
  buildAiApprovalResumeRequest,
  cancelPendingApproval,
  livePendingApprovalToChatApprovals,
  type LivePendingApprovalInput,
} from './chatbot-view-model';
import type {
  ChatbotViewState,
  ChatbotViewStateUpdater,
} from './useChatbotViewState';

export function useChatbotApprovals({
  allowedAppIds,
  currentConversationId,
  isConversationReady,
  isSending,
  pendingApprovals,
  replacePendingApprovals,
  resumeChat,
  routeConversationId,
  setApprovalAction,
  setApprovalError,
  token,
  upsertPendingApproval,
}: {
  allowedAppIds: string[] | null;
  currentConversationId: string | null;
  isConversationReady: boolean;
  isSending: boolean;
  pendingApprovals: PendingApproval[];
  replacePendingApprovals: UseChatStreamApi['replacePendingApprovals'];
  resumeChat: UseChatStreamApi['resume'];
  routeConversationId: string | null;
  setApprovalAction: (
    value: ChatbotViewStateUpdater<ChatbotViewState['approvalAction']>,
  ) => void;
  setApprovalError: (
    value: ChatbotViewStateUpdater<ChatbotViewState['approvalError']>,
  ) => void;
  token: string | null;
  upsertPendingApproval: UseChatStreamApi['upsertPendingApproval'];
}) {
  const { t } = useTranslation(['apps', 'auth']);
  const autoResumeAttemptedApprovalsRef = useRef<Set<string>>(new Set());

  const pendingApproval = useMemo(
    () =>
      pendingApprovals.find((approval) => approval.decision === null) ?? null,
    [pendingApprovals],
  );
  const resumableApproval = useMemo(
    () =>
      pendingApprovals.find(
        (approval) =>
          approval.decision === 'approved' || approval.decision === 'rejected',
      ) ?? null,
    [pendingApprovals],
  );
  const blockingApproval = pendingApproval ?? resumableApproval;

  const clearApprovalAction = useCallback(
    (approvalId: string) => {
      setApprovalAction((current) =>
        current?.approvalId === approvalId ? null : current,
      );
    },
    [setApprovalAction],
  );

  const handleApprovalActionError = useCallback(
    (error: unknown, fallbackMessage: string) => {
      if (
        error instanceof AiApiError &&
        (error.status === 404 || error.status === 410)
      ) {
        replacePendingApprovals([]);
      }
      setApprovalError(
        error instanceof Error ? error.message : fallbackMessage,
      );
    },
    [replacePendingApprovals, setApprovalError],
  );

  const syncLivePendingApproval = useCallback(
    (livePendingApproval: LivePendingApprovalInput) => {
      const approvals = livePendingApprovalToChatApprovals(livePendingApproval);
      if (approvals.length === 0) {
        setApprovalError(null);
      }
      replacePendingApprovals(approvals);
    },
    [replacePendingApprovals, setApprovalError],
  );

  const resumePendingApproval = useCallback(
    async (approval: PendingApproval) => {
      if (!token || !currentConversationId) {
        setApprovalError(t('apps:ai.view.conversationContextMissing'));
        return;
      }
      setApprovalAction({ approvalId: approval.approval_id, kind: 'resume' });
      setApprovalError(null);
      try {
        await resumeChat(
          buildAiApprovalResumeRequest({
            allowedAppIds,
            approvalId: approval.approval_id,
            conversationId: currentConversationId,
          }),
          {
            seedApproval: approval,
          },
        );
      } catch (error) {
        handleApprovalActionError(error, t('apps:ai.view.resumeFailed'));
      } finally {
        clearApprovalAction(approval.approval_id);
      }
    },
    [
      allowedAppIds,
      clearApprovalAction,
      currentConversationId,
      handleApprovalActionError,
      resumeChat,
      setApprovalAction,
      setApprovalError,
      t,
      token,
    ],
  );

  const handleResolveApproval = useCallback(
    async (
      approval: PendingApproval,
      decision: 'approved' | 'rejected',
      reason?: string,
    ) => {
      if (!token) {
        setApprovalError(t('auth:errors.noActiveSession'));
        return;
      }
      setApprovalAction({
        approvalId: approval.approval_id,
        kind: decision === 'approved' ? 'approve' : 'reject',
      });
      setApprovalError(null);
      try {
        await resolveAiApproval(
          token,
          approval.approval_id,
          buildAiApprovalResolveRequest({
            decision,
            reason,
          }),
          {},
        );
        const resolvedApproval = applyPendingApprovalDecision({
          approval,
          decision,
          reason,
        });
        upsertPendingApproval(resolvedApproval);
        autoResumeAttemptedApprovalsRef.current.add(
          resolvedApproval.approval_id,
        );
        await resumePendingApproval(resolvedApproval);
      } catch (error) {
        handleApprovalActionError(error, t('apps:ai.view.applyApprovalFailed'));
      } finally {
        clearApprovalAction(approval.approval_id);
      }
    },
    [
      clearApprovalAction,
      handleApprovalActionError,
      resumePendingApproval,
      setApprovalAction,
      setApprovalError,
      t,
      token,
      upsertPendingApproval,
    ],
  );

  const handleAbandonApproval = useCallback(
    async (approval: PendingApproval) => {
      if (!token) {
        setApprovalError(t('auth:errors.noActiveSession'));
        return;
      }
      setApprovalAction({ approvalId: approval.approval_id, kind: 'abandon' });
      setApprovalError(null);
      try {
        await abandonAiApproval(token, approval.approval_id, {}, {});
        upsertPendingApproval(cancelPendingApproval(approval));
      } catch (error) {
        handleApprovalActionError(error, t('apps:ai.view.cancelRequestFailed'));
      } finally {
        clearApprovalAction(approval.approval_id);
      }
    },
    [
      clearApprovalAction,
      handleApprovalActionError,
      setApprovalAction,
      setApprovalError,
      t,
      token,
      upsertPendingApproval,
    ],
  );

  useEffect(() => {
    autoResumeAttemptedApprovalsRef.current.clear();
  }, [routeConversationId]);

  useEffect(() => {
    if (!resumableApproval || isSending || !isConversationReady) {
      return;
    }
    if (
      autoResumeAttemptedApprovalsRef.current.has(resumableApproval.approval_id)
    ) {
      return;
    }
    autoResumeAttemptedApprovalsRef.current.add(resumableApproval.approval_id);
    void resumePendingApproval(resumableApproval);
  }, [
    isConversationReady,
    isSending,
    resumePendingApproval,
    resumableApproval,
    routeConversationId,
  ]);

  return {
    blockingApproval,
    handleAbandonApproval,
    handleResolveApproval,
    pendingApproval,
    resumableApproval,
    resumePendingApproval,
    syncLivePendingApproval,
  };
}
