import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { useConfirm } from '@ai-do/ui';

import type { NavItem } from '@/src/app/shell/navigation-types';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { resolveToolInvocationHref } from '@/src/platform/workspaces/workspace-utils';
import {
  CONVERSATIONS_UPDATED_EVENT,
  getConversation,
} from '../api/conversations-api';
import {
  isAiGraphRunActive,
  useAiGraphRunRecovery,
} from '../api/useAiGraphRunRecovery';
import { useChatStream } from '../api/useChatStream';
import type { ChatTurn } from './chat/MessageBubble';
import {
  buildAiChatStreamRequest,
  buildConversationSearchParams,
  buildPendingDraftCleanupNavigation,
  buildPromptEditTransition,
  buildRetryTurnTransition,
  buildSubmitTransition,
  mergeToolCalls,
  normalizeConversationDetail,
  resolvePendingAiDraft,
  shouldConfirmRewrite,
  serializeTurnForModel,
  type AiChatSendRequestOptions,
  type AiPendingSendSnapshot,
  type AiSendTransition,
} from './chatbot-view-model';
import { useChatbotViewState } from './useChatbotViewState';
import { useChatbotHealth } from './useChatbotHealth';
import { useChatbotChatStreamCommit } from './useChatbotChatStreamCommit';
import { useChatbotArtifactRouting } from './useChatbotArtifactRouting';
import { useChatbotApprovals } from './useChatbotApprovals';
import { useChatbotConversationHydration } from './useChatbotConversationHydration';
import type {
  ChatbotExperienceConfig,
  ResolvedChatbotExperienceConfig,
} from './chatbot-experience';

export function useChatbotViewController(
  experience: ChatbotExperienceConfig = {},
) {
  const { t } = useTranslation(['apps', 'auth', 'shell']);
  const { confirm, confirmDialog } = useConfirm();
  const { status: authStatus, token, user } = useAuth();
  const { pathname: locationPathname, state: locationState } = useLocation();
  const navigate = useNavigate();
  const { workspaceSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  // `c` query param is the durable source of truth for which persisted
  // conversation this tab is showing. The conversation list navigates to
  // `/w/:slug/chatbot?c=<id>` to switch threads; the bare
  // `/w/:slug/chatbot` path
  // opens a fresh chat. Stream-created conversations write themselves back
  // into this param so a page refresh resumes the same thread.
  const routeConversationId = searchParams.get('c');
  // Meeting-insight deep-link `draft` param (Step E.4). Populated when
  // the user clicks continue in chat on a meeting AI suggestion card and
  // becomes the composer's starting value on the next fresh-chat mount.
  // The companion params (`context`, `context_id`, `insight_id`,
  // `insight_kind`) are cleared alongside `draft` in the same replace
  // call; they carry no runtime behavior in this slice and are reserved
  // for the Step F scope-bound conversation flow.
  const routeDraft = searchParams.get('draft');
  const {
    locationDraft,
    locationDraftSourceKey,
    pendingDraft,
    pendingDraftSourceKey,
  } = resolvePendingAiDraft({
    insightId: searchParams.get('insight_id'),
    locationState,
    routeDraft,
  });
  const { health, healthError } = useChatbotHealth(token, workspaceSlug);
  const backendMode = 'local' as const;
  const resolvedExperience = useMemo<ResolvedChatbotExperienceConfig>(() => {
    return {
      routeAppId: experience.routeAppId ?? 'chatbot',
      routePathSuffix: experience.routePathSuffix ?? '',
      sidebarEyebrow: experience.sidebarEyebrow ?? 'AI',
      sidebarTitle:
        experience.sidebarTitle ?? t('apps:ai.sidebar.recentConversations'),
      title: experience.title ?? t('apps:ai.view.title'),
      conversationScope: experience.conversationScope,
      emptyGreeting: experience.emptyGreeting,
      emptySubline: experience.emptySubline,
      artifactRenderers: experience.artifactRenderers,
      autoOpenArtifacts: experience.autoOpenArtifacts ?? true,
      executionMode: experience.executionMode ?? 'inline',
      sourceArtifactTypes: experience.sourceArtifactTypes ?? [],
    };
  }, [
    experience.artifactRenderers,
    experience.autoOpenArtifacts,
    experience.conversationScope,
    experience.executionMode,
    experience.emptyGreeting,
    experience.emptySubline,
    experience.routeAppId,
    experience.routePathSuffix,
    experience.sidebarEyebrow,
    experience.sidebarTitle,
    experience.sourceArtifactTypes,
    experience.title,
    t,
  ]);
  const scopeOptions: [] = [];
  const sanitizedAllowedAppIds: [] = [];
  const setAllowedAppIds = useCallback(
    (_nextAllowedAppIds: string[] | null) => {
      // Business context selection is hidden until the RAG/SQL/fulltext context
      // architecture is redesigned. Keep the action shape stable for callers.
    },
    [],
  );
  const {
    state: viewState,
    setTurns,
    patchViewState,
    setInput,
    setEditingTurnId,
    setEditingText,
    setChatError,
    setApprovalError,
    setFailedPromptRecovery,
    setForceFollowKey,
    setActiveConversationId,
    setScopeInfo,
    setApprovalAction,
    setShowInsightHint,
    setPendingDraftSearchCleanup,
  } = useChatbotViewState();
  const {
    turns,
    input,
    editingTurnId,
    editingText,
    chatError,
    approvalError,
    failedPromptRecovery,
    forceFollowKey,
    activeConversationId,
    isLoadingConversation,
    scopeInfo,
    approvalAction,
    showInsightHint,
    pendingDraftSearchCleanup,
  } = viewState;
  const pendingUserTurnIdRef = useRef<string | null>(null);
  const pendingUserInputRef = useRef('');
  const pendingSendRef = useRef<AiPendingSendSnapshot | null>(null);
  // Only tracks a conversation id once the view can safely append to it:
  // either hydration succeeded for `?c=` or the current stream emitted
  // `conversation_attached`. This avoids writing into an existing thread
  // before its history has been loaded.
  // Tracks the resolved scope binding for the current conversation. `null`
  // means free chat (no scope). When a meeting-scoped conversation is
  // loaded, scope title is filled asynchronously for known scope adapters so
  // the chip can display a concrete resource name instead of a generic label.
  const chatRuntimeKey = useMemo(
    () =>
      [
        user?.id ?? 'anonymous',
        workspaceSlug ?? 'no-workspace',
        resolvedExperience.routeAppId,
        resolvedExperience.routePathSuffix,
        resolvedExperience.conversationScope?.ref ?? 'unscoped',
        resolvedExperience.conversationScope?.resourceId ?? 'unscoped',
      ].join(':'),
    [
      resolvedExperience.conversationScope?.ref,
      resolvedExperience.conversationScope?.resourceId,
      resolvedExperience.routeAppId,
      resolvedExperience.routePathSuffix,
      user?.id,
      workspaceSlug,
    ],
  );
  const chat = useChatStream(token, workspaceSlug, chatRuntimeKey, {
    disableSyncFallback:
      resolvedExperience.executionMode === 'durable_background',
  });
  const pendingUserContentRef = useRef<string | null>(null);
  pendingUserContentRef.current =
    chat.state.status === 'streaming' ? chat.state.pendingUserContent : null;
  const {
    abort: abortChat,
    replacePendingApprovals,
    reset: resetChat,
    resume: resumeChat,
    upsertPendingApproval,
  } = chat;
  const isSending = chat.state.status === 'streaming';
  const isConversationReady =
    routeConversationId === null ||
    activeConversationId === routeConversationId;
  const finalizedToolCalls = useMemo(
    () => turns.flatMap((turn) => turn.toolCalls ?? []),
    [turns],
  );
  const visibleToolCalls = useMemo(
    () => mergeToolCalls(finalizedToolCalls, chat.state.toolCalls),
    [chat.state.toolCalls, finalizedToolCalls],
  );
  const slashCommandItems: NavItem[] = [];

  const currentConversationId = activeConversationId ?? routeConversationId;
  const durableRunRecovery = useAiGraphRunRecovery({
    appId: resolvedExperience.routeAppId,
    conversationId: currentConversationId,
    enabled: resolvedExperience.executionMode === 'durable_background',
    refreshKey: chat.state.status,
    token,
    workspaceSlug,
  });
  const recoveredRunIsActive = isAiGraphRunActive(durableRunRecovery.run);
  const isRunInProgress = isSending || recoveredRunIsActive;
  const abortHydrateRef = useRef<AbortController | null>(null);
  const skipHydrationConversationIdRef = useRef<string | null>(null);
  // Tracks the draft source key only after the draft text has actually
  // landed in component state. Deferring the write avoids a StrictMode
  // double-effect bug where the first mount run mutates the ref, the
  // second mount run skips consumption, and the queued `setInput(...)`
  // never makes it to the committed render.
  const consumedDraftRef = useRef<string | null>(null);
  const refreshConversationTimeoutRef = useRef<number | null>(null);
  const durableRunRefreshKeyRef = useRef<string | null>(null);
  const failedPromptRecoveryRef = useRef('');
  // The consume path clears the `draft` URL param via setSearchParams,
  // which changes `routeDraft` and triggers another run of the
  // hydration effect. Without this guard, that run would execute the
  // unconditional `setInput('')` reset and wipe the draft we just
  // injected. Setting the flag immediately before `setSearchParams`
  // means the very next run skips its reset, then clears the flag.
  const skipNextHydrationResetRef = useRef(false);

  const clearRefreshConversationTimeout = useCallback(() => {
    const refreshConversationTimeout = refreshConversationTimeoutRef.current;
    if (refreshConversationTimeout !== null) {
      window.clearTimeout(refreshConversationTimeout);
      refreshConversationTimeoutRef.current = null;
    }
  }, []);

  const {
    blockingApproval,
    handleAbandonApproval,
    handleResolveApproval,
    pendingApproval,
    resumableApproval,
    resumePendingApproval,
    syncLivePendingApproval,
  } = useChatbotApprovals({
    allowedAppIds: sanitizedAllowedAppIds,
    currentConversationId,
    isConversationReady,
    isSending,
    pendingApprovals: chat.state.pendingApprovals,
    replacePendingApprovals,
    resumeChat,
    routeConversationId,
    setApprovalAction,
    setApprovalError,
    token,
    upsertPendingApproval,
    workspaceSlug,
  });

  const isComposerDisabled =
    isLoadingConversation ||
    !isConversationReady ||
    blockingApproval !== null ||
    recoveredRunIsActive;

  const refreshConversationDetail = useCallback(
    async (conversationId: string) => {
      if (!token) {
        return;
      }
      try {
        const detail = await getConversation(token, conversationId, {
          workspaceSlug,
        });
        const normalizedDetail = normalizeConversationDetail(detail);
        setTurns(normalizedDetail.turns);
        setActiveConversationId(normalizedDetail.activeConversationId);
        setChatError(null);
        syncLivePendingApproval(detail.livePendingApproval);
        setScopeInfo(normalizedDetail.scopeInfo);
      } catch {
        // The live answer is already rendered. A stale post-stream refresh can
        // wait for the next explicit hydration or sidebar selection.
      }
    },
    [
      setActiveConversationId,
      setChatError,
      setScopeInfo,
      setTurns,
      syncLivePendingApproval,
      token,
      workspaceSlug,
    ],
  );

  useEffect(() => {
    const run = durableRunRecovery.run;
    if (
      !currentConversationId ||
      !run ||
      (run.status !== 'completed' &&
        run.status !== 'failed' &&
        run.status !== 'cancelled')
    ) {
      return;
    }
    const refreshKey = `${run.id}:${run.status}:${run.updatedAt ?? ''}`;
    if (durableRunRefreshKeyRef.current === refreshKey) {
      return;
    }
    durableRunRefreshKeyRef.current = refreshKey;
    void refreshConversationDetail(currentConversationId);
  }, [
    currentConversationId,
    durableRunRecovery.run,
    refreshConversationDetail,
  ]);

  useEffect(() => {
    failedPromptRecoveryRef.current = failedPromptRecovery;
  }, [failedPromptRecovery]);

  useEffect(() => {
    if (!input && showInsightHint) {
      setShowInsightHint(false);
    }
  }, [input, setShowInsightHint, showInsightHint]);

  useEffect(() => {
    if (
      pendingDraft &&
      pendingDraftSourceKey &&
      showInsightHint &&
      input === pendingDraft
    ) {
      consumedDraftRef.current = pendingDraftSourceKey;
    }
  }, [input, pendingDraft, pendingDraftSourceKey, showInsightHint]);

  useEffect(() => {
    return clearRefreshConversationTimeout;
  }, [clearRefreshConversationTimeout]);

  useChatbotConversationHydration({
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
    workspaceSlug,
  });

  useEffect(() => {
    if (!blockingApproval) {
      setApprovalError(null);
    }
  }, [blockingApproval, setApprovalError]);

  useEffect(() => {
    if (!pendingDraftSearchCleanup || !routeDraft) {
      return;
    }
    skipNextHydrationResetRef.current = true;
    setPendingDraftSearchCleanup(false);
    const navigation = buildPendingDraftCleanupNavigation({
      locationPathname,
      locationState,
      pendingDraft,
      pendingDraftSourceKey,
      searchParams,
    });
    navigate(
      { pathname: navigation.pathname, search: navigation.search },
      {
        replace: true,
        state: navigation.state,
      },
    );
  }, [
    locationPathname,
    locationState,
    navigate,
    pendingDraft,
    pendingDraftSearchCleanup,
    pendingDraftSourceKey,
    routeDraft,
    searchParams,
    setPendingDraftSearchCleanup,
  ]);

  // When a stream lands a brand-new conversation id (first persisted turn
  // on an empty URL), push it back into `?c=` so a refresh or a bookmark
  // resumes the same thread. Uses replace so the history doesn't grow an
  // extra entry per new chat.
  useEffect(() => {
    const streamedId = chat.state.conversationId;
    if (!streamedId || streamedId === routeConversationId) {
      return;
    }
    setActiveConversationId(streamedId);
    window.dispatchEvent(
      new CustomEvent(CONVERSATIONS_UPDATED_EVENT, {
        detail: { conversationId: streamedId },
      }),
    );
    if (chat.isRunOwner) {
      skipHydrationConversationIdRef.current = streamedId;
    }
    // Read the live URL rather than the hook's snapshot so a sibling
    // effect that just wrote `?a=<artifact>` in the same render tick
    // doesn't get clobbered when this one writes `?c=<conversation>`.
    setSearchParams(
      buildConversationSearchParams(
        new URLSearchParams(
          typeof window === 'undefined' ? '' : window.location.search,
        ),
        streamedId,
      ),
      { replace: true },
    );
  }, [
    chat.isRunOwner,
    chat.state.conversationId,
    routeConversationId,
    searchParams,
    setActiveConversationId,
    setSearchParams,
  ]);

  useChatbotChatStreamCommit({
    chatState: chat.state,
    clearRefreshConversationTimeout,
    failedPromptRecoveryRef,
    patchViewState,
    pendingSendRef,
    pendingUserInputRef,
    pendingUserTurnIdRef,
    isRunOwner: chat.isRunOwner,
    refreshConversationDetail,
    refreshConversationTimeoutRef,
    resetChat,
  });

  const {
    activeArtifact,
    allArtifacts,
    handleCloseArtifact,
    handleOpenArtifact,
    routeArtifactId,
  } = useChatbotArtifactRouting({
    autoOpenArtifacts: resolvedExperience.autoOpenArtifacts,
    isConversationReady,
    isLoadingConversation: isLoadingConversation || durableRunRecovery.loading,
    isSending,
    liveArtifacts: chat.state.artifacts,
    recoveredArtifacts: durableRunRecovery.artifacts,
    sourceArtifactTypes: resolvedExperience.sourceArtifactTypes,
    turns,
  });

  const sendTurnsToChat = (
    nextTurns: ChatTurn[],
    options: AiChatSendRequestOptions = {},
  ) => {
    if (!token) {
      return;
    }
    void chat.send(
      buildAiChatStreamRequest({
        activeConversationId,
        allowedAppIds: sanitizedAllowedAppIds,
        backendMode,
        conversationScope: resolvedExperience.conversationScope,
        options,
        turns: nextTurns,
      }),
    );
  };

  const commitSendTransition = (
    transition: AiSendTransition,
    options: { closeRouteArtifact?: boolean } = {},
  ) => {
    setTurns(transition.nextTurns);
    setEditingTurnId(null);
    setEditingText('');
    setInput('');
    setChatError(null);
    setApprovalError(null);
    pendingUserTurnIdRef.current = transition.pendingUserTurnId;
    pendingUserInputRef.current = transition.pendingUserInput;
    pendingSendRef.current = transition.pendingSend;
    setForceFollowKey((current) => current + 1);
    resetChat();
    if (options.closeRouteArtifact && routeArtifactId) {
      handleCloseArtifact();
    }
    sendTurnsToChat(transition.nextTurns, transition.sendOptions);
  };

  const confirmRewriteIfNeeded = async (
    replaceFromSeq: number,
  ): Promise<boolean> => {
    if (!shouldConfirmRewrite({ turns, replaceFromSeq })) {
      return true;
    }
    return confirm({
      title: t('apps:ai.message.rewriteConfirmTitle'),
      description: t('apps:ai.message.rewriteConfirmDescription'),
      confirmLabel: t('apps:ai.message.rewriteConfirmAction'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
  };

  const handleCopyTurn = async (turn: ChatTurn) => {
    try {
      await navigator.clipboard.writeText(serializeTurnForModel(turn));
      setChatError(null);
    } catch (error) {
      setChatError(t('apps:ai.message.copyFailed'));
      throw error;
    }
  };

  const handleStartEditTurn = (turn: ChatTurn) => {
    if (isRunInProgress || turn.role !== 'user') {
      return;
    }
    setEditingTurnId(turn.id);
    setEditingText(turn.content);
  };

  const submitEditedTurn = async () => {
    if (
      !editingTurnId ||
      !token ||
      isRunInProgress ||
      !isConversationReady ||
      blockingApproval !== null
    ) {
      return;
    }
    const transition = buildPromptEditTransition({
      editingText,
      editingTurnId,
      turns,
    });
    if (transition.status === 'invalid') {
      return;
    }
    if (transition.status === 'unchanged') {
      setEditingTurnId(null);
      setEditingText('');
      return;
    }
    const confirmed = await confirmRewriteIfNeeded(transition.replaceFromSeq);
    if (!confirmed) {
      return;
    }
    commitSendTransition(transition, { closeRouteArtifact: true });
  };

  const handleRetryTurn = async (turn: ChatTurn) => {
    if (
      !token ||
      isRunInProgress ||
      turn.role !== 'assistant' ||
      turn.seq === undefined ||
      !isConversationReady ||
      blockingApproval !== null
    ) {
      return;
    }
    const transition = buildRetryTurnTransition({ turn, turns });
    if (transition.status === 'invalid') {
      return;
    }
    const confirmed = await confirmRewriteIfNeeded(transition.replaceFromSeq);
    if (!confirmed) {
      return;
    }
    if (transition.status === 'missingTrailingUser') {
      setChatError(t('apps:ai.message.retryUnavailable'));
      return;
    }
    commitSendTransition(transition, { closeRouteArtifact: true });
  };

  function handleSelectTool(item: NavItem) {
    // Tool invocation semantics: plain AI items land on their /tool/:id page,
    // deep-links (linkAppId, absolutePath) honor their NavItem metadata.
    navigate(resolveToolInvocationHref(item, workspaceSlug, user));
  }

  function handleSubmit() {
    const transition = buildSubmitTransition({
      input,
      nowMs: Date.now(),
      turns,
    });
    if (
      !transition ||
      !token ||
      isRunInProgress ||
      !isConversationReady ||
      blockingApproval !== null
    ) {
      return;
    }

    commitSendTransition(transition);
  }

  return {
    state: {
      approvalAction,
      approvalError,
      blockingApproval,
      chatError,
      chatState: chat.state,
      currentConversationId,
      editingText,
      editingTurnId,
      failedPromptRecovery,
      forceFollowKey,
      health,
      healthError,
      input,
      isComposerDisabled,
      isConversationReady,
      isLoadingConversation,
      isRunInProgress,
      isSending,
      pendingApproval,
      recoveredRunIsActive,
      resumableApproval,
      routeArtifactId,
      sanitizedAllowedAppIds,
      scopeInfo,
      showInsightHint,
      turns,
    },
    actions: {
      abortChat,
      handleAbandonApproval,
      handleCloseArtifact,
      handleCopyTurn,
      handleOpenArtifact,
      handleResolveApproval,
      handleRetryTurn,
      handleSelectTool,
      handleStartEditTurn,
      handleSubmit,
      resumePendingApproval,
      setAllowedAppIds,
      setEditingText,
      setEditingTurnId,
      setFailedPromptRecovery,
      setInput,
      submitEditedTurn,
    },
    derived: {
      activeArtifact,
      allArtifacts,
      backendMode,
      confirmDialog,
      durableRun: durableRunRecovery.run,
      experience: resolvedExperience,
      scopeOptions,
      slashCommandItems,
      t,
      visibleToolCalls,
      workspaceSlug,
    },
  };
}

export type ChatbotViewController = ReturnType<typeof useChatbotViewController>;
