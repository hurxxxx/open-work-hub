import type {
  ArtifactBuffer,
  ChatStreamStatus,
  PendingApproval,
  ToolCallBuffer,
} from '../api/agent-events';
import type {
  AiBackendMode,
  AiChatStreamRequest,
  ResolveAiApprovalRequest,
  ResumeAiChatRequest,
} from '../api/chatbot-api';
import type {
  ConversationDetail,
  ConversationLivePendingApproval,
} from '../api/conversations-api';
import {
  serializeTurnsForModel as serializeTurnsForModelForRequest,
  type AssistantTurnStreamState,
} from './chat-turn-model';
import type { ChatTurn } from './chat/chat-turn';
import type { ChatbotConversationScopeBinding } from './chatbot-experience';

export {
  buildAssistantTurnFromStream,
  collectArtifacts,
  normalizeConversationDetail,
  resolveAssistantTurnContent,
  serializeTurnForModel,
  serializeTurnsForModel,
} from './chat-turn-model';
export type {
  AssistantTurnContentMessages,
  AssistantTurnStreamState,
  ChatbotConversationScopeInfo,
  NormalizedConversationDetail,
  TerminalChatStreamStatus,
} from './chat-turn-model';

export interface AiDraftLocationState {
  aiDraft: string;
  aiDraftSourceKey: string;
  aiDraftOrigin: 'meeting_insight';
}

export interface PendingAiDraft {
  locationDraft: string | null;
  locationDraftSourceKey: string | null;
  pendingDraft: string | null;
  pendingDraftSourceKey: string | null;
}

export interface FreshChatDraftPatch {
  input: string;
  showInsightHint: true;
  pendingDraftSearchCleanup: boolean;
}

export interface AiDraftNavigationState {
  aiDraft: string;
  aiDraftSourceKey: string;
  aiDraftOrigin: 'meeting_insight';
}

export interface AiDraftCleanupNavigation {
  pathname: string;
  search: string;
  state: AiDraftNavigationState | unknown;
}

export interface AiChatSendRequestOptions {
  replaceFromSeq?: number;
  replaceFromTurnId?: string;
  replaceTailSeq?: number;
  replaceTailTurnId?: string;
  persistUserTurn?: boolean;
}

export type AiPendingSendKind = 'normal' | 'edit' | 'retry';

export interface AiPendingSendSnapshot {
  kind: AiPendingSendKind;
  originalTurns: ChatTurn[];
  optimisticTurns: ChatTurn[];
  pendingUserTurnId: string | null;
  pendingUserInput: string;
}

export interface AiSendTransition {
  nextTurns: ChatTurn[];
  pendingSend: AiPendingSendSnapshot;
  pendingUserInput: string;
  pendingUserTurnId: string | null;
  sendOptions?: AiChatSendRequestOptions;
}

export interface AiRewriteRollbackPatch {
  chatError: string;
  turns: ChatTurn[];
  editingTurnId?: string;
  editingText?: string;
  failedPromptRecovery?: string;
}

export interface AiFailedSendPatch {
  chatError: string;
  failedPromptRecovery: string;
  input: string;
  turns: ChatTurn[];
}

export type AiPromptEditTransition =
  | { status: 'invalid' }
  | { status: 'unchanged' }
  | ({ status: 'ready'; replaceFromSeq: number } & AiSendTransition);

export type AiRetryTransition =
  | { status: 'invalid' }
  | { status: 'missingTrailingUser'; replaceFromSeq: number }
  | ({ status: 'ready'; replaceFromSeq: number } & AiSendTransition);

export interface AiScopeBootstrapApp {
  app_id: string;
  enabled: boolean;
  title: string;
}

export interface AiScopeOption {
  id: string;
  title: string;
}

export type LivePendingApprovalInput =
  | ConversationLivePendingApproval
  | null
  | undefined;

export function readAiDraftLocationState(
  state: unknown,
): AiDraftLocationState | null {
  if (!state || typeof state !== 'object') {
    return null;
  }
  const candidate = state as {
    aiDraft?: unknown;
    aiDraftSourceKey?: unknown;
    aiDraftOrigin?: unknown;
  };
  if (
    typeof candidate.aiDraft !== 'string' ||
    typeof candidate.aiDraftSourceKey !== 'string' ||
    candidate.aiDraftOrigin !== 'meeting_insight'
  ) {
    return null;
  }
  return {
    aiDraft: candidate.aiDraft,
    aiDraftSourceKey: candidate.aiDraftSourceKey,
    aiDraftOrigin: 'meeting_insight',
  };
}

export function resolvePendingAiDraft({
  insightId,
  locationState,
  routeDraft,
}: {
  insightId: string | null;
  locationState: unknown;
  routeDraft: string | null;
}): PendingAiDraft {
  const locationDraftState = readAiDraftLocationState(locationState);
  const routeDraftSourceKey = insightId
    ? `meeting-insight:${insightId}`
    : routeDraft
      ? `draft:${routeDraft}`
      : null;
  return {
    locationDraft: locationDraftState?.aiDraft ?? null,
    locationDraftSourceKey: locationDraftState?.aiDraftSourceKey ?? null,
    pendingDraft: locationDraftState?.aiDraft ?? routeDraft,
    pendingDraftSourceKey:
      locationDraftState?.aiDraftSourceKey ?? routeDraftSourceKey,
  };
}

export function shouldConsumePendingDraft({
  consumedDraftSourceKey,
  pendingDraft,
  pendingDraftSourceKey,
}: {
  consumedDraftSourceKey: string | null;
  pendingDraft: string | null;
  pendingDraftSourceKey: string | null;
}): boolean {
  return Boolean(
    pendingDraft &&
      pendingDraftSourceKey &&
      consumedDraftSourceKey !== pendingDraftSourceKey,
  );
}

export function buildFreshChatDraftPatch({
  consumedDraftSourceKey,
  hasRouteDraft,
  pendingDraft,
  pendingDraftSourceKey,
}: {
  consumedDraftSourceKey: string | null;
  hasRouteDraft: boolean;
  pendingDraft: string | null;
  pendingDraftSourceKey: string | null;
}): FreshChatDraftPatch | null {
  if (
    !shouldConsumePendingDraft({
      consumedDraftSourceKey,
      pendingDraft,
      pendingDraftSourceKey,
    })
  ) {
    return null;
  }
  return {
    input: pendingDraft as string,
    showInsightHint: true,
    pendingDraftSearchCleanup: hasRouteDraft,
  };
}

export function buildPendingDraftCleanupNavigation({
  locationPathname,
  locationState,
  pendingDraft,
  pendingDraftSourceKey,
  searchParams,
}: {
  locationPathname: string;
  locationState: unknown;
  pendingDraft: string | null;
  pendingDraftSourceKey: string | null;
  searchParams: URLSearchParams;
}): AiDraftCleanupNavigation {
  const next = new URLSearchParams(searchParams);
  next.delete('draft');
  next.delete('context');
  next.delete('context_id');
  next.delete('insight_id');
  next.delete('insight_kind');
  return {
    pathname: locationPathname,
    search: next.toString() ? `?${next.toString()}` : '',
    state:
      pendingDraft && pendingDraftSourceKey
        ? {
            aiDraft: pendingDraft,
            aiDraftSourceKey: pendingDraftSourceKey,
            aiDraftOrigin: 'meeting_insight',
          }
        : locationState,
  };
}

export function buildConversationSearchParams(
  searchParams: URLSearchParams,
  conversationId: string,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.set('c', conversationId);
  return next;
}

export function buildAiChatStreamRequest({
  activeConversationId,
  allowedAppIds,
  backendMode,
  conversationScope,
  options = {},
  turns,
}: {
  activeConversationId: string | null;
  allowedAppIds: string[] | null;
  backendMode: AiBackendMode;
  conversationScope?: ChatbotConversationScopeBinding;
  options?: AiChatSendRequestOptions;
  turns: ChatTurn[];
}): AiChatStreamRequest {
  return {
    messages: serializeTurnsForModelForRequest(turns),
    backend_mode: backendMode,
    temperature: 0.2,
    stream_reasoning: true,
    persist: true,
    conversation_id: activeConversationId ?? undefined,
    ...(!activeConversationId && conversationScope
      ? {
          scope_ref: conversationScope.ref,
          scope_resource_id: conversationScope.resourceId,
        }
      : {}),
    ...(options.replaceFromSeq !== undefined
      ? { replace_from_seq: options.replaceFromSeq }
      : {}),
    ...(options.replaceFromTurnId !== undefined
      ? { replace_from_turn_id: options.replaceFromTurnId }
      : {}),
    ...(options.replaceTailSeq !== undefined
      ? { replace_tail_seq: options.replaceTailSeq }
      : {}),
    ...(options.replaceTailTurnId !== undefined
      ? { replace_tail_turn_id: options.replaceTailTurnId }
      : {}),
    ...(options.persistUserTurn !== undefined
      ? { persist_user_turn: options.persistUserTurn }
      : {}),
    ...(allowedAppIds !== null ? { allowed_app_ids: allowedAppIds } : {}),
  };
}

export function buildAiApprovalResumeRequest({
  allowedAppIds,
  approvalId,
  conversationId,
}: {
  allowedAppIds: string[] | null;
  approvalId: string;
  conversationId: string;
}): ResumeAiChatRequest {
  return {
    conversation_id: conversationId,
    approval_id: approvalId,
    ...(allowedAppIds !== null ? { allowed_app_ids: allowedAppIds } : {}),
  };
}

function normalizeOptionalReason(reason: string | null | undefined): {
  requestReason: string | undefined;
  approvalReason: string | null;
} {
  const trimmed = reason?.trim();
  if (!trimmed) {
    return { requestReason: undefined, approvalReason: null };
  }
  return { requestReason: trimmed, approvalReason: trimmed };
}

export function buildAiApprovalResolveRequest({
  decision,
  reason,
}: {
  decision: 'approved' | 'rejected';
  reason?: string;
}): ResolveAiApprovalRequest {
  return {
    decision,
    reason: normalizeOptionalReason(reason).requestReason,
  };
}

export function applyPendingApprovalDecision({
  approval,
  decision,
  reason,
}: {
  approval: PendingApproval;
  decision: 'approved' | 'rejected';
  reason?: string;
}): PendingApproval {
  return {
    ...approval,
    decision,
    reason: normalizeOptionalReason(reason).approvalReason,
  };
}

export function cancelPendingApproval(
  approval: PendingApproval,
): PendingApproval {
  return {
    ...approval,
    decision: 'cancelled',
    reason: null,
  };
}

export function shouldRollbackRewriteBeforeAcceptance({
  conversationId,
  pendingSend,
  status,
}: {
  conversationId: string | null;
  pendingSend: AiPendingSendSnapshot | null;
  status: ChatStreamStatus;
}): boolean {
  return Boolean(
    pendingSend !== null &&
      pendingSend.kind !== 'normal' &&
      (status === 'error' || status === 'cancelled') &&
      !conversationId,
  );
}

export function buildRewriteRollbackPatch({
  errorMessage,
  fallbackErrorMessage,
  pendingSend,
}: {
  errorMessage: string | null;
  fallbackErrorMessage: string;
  pendingSend: AiPendingSendSnapshot;
}): AiRewriteRollbackPatch {
  const patch: AiRewriteRollbackPatch = {
    chatError: errorMessage ?? fallbackErrorMessage,
    turns: pendingSend.originalTurns,
  };
  if (pendingSend.kind === 'edit' && pendingSend.pendingUserTurnId) {
    patch.editingTurnId = pendingSend.pendingUserTurnId;
    patch.editingText = pendingSend.pendingUserInput;
  } else if (pendingSend.pendingUserInput) {
    patch.failedPromptRecovery = pendingSend.pendingUserInput;
  }
  return patch;
}

export function shouldFinalizeTerminalStream({
  status,
  streamOpened,
}: {
  status: ChatStreamStatus;
  streamOpened: boolean;
}): boolean {
  return status === 'done' || status === 'cancelled' || streamOpened;
}

export function shouldKeepPendingApprovalsAfterTerminal({
  finishReason,
  pendingApprovals,
  status,
}: {
  finishReason: AssistantTurnStreamState['finishReason'];
  pendingApprovals: PendingApproval[];
  status: ChatStreamStatus;
}): boolean {
  return (
    finishReason === 'awaiting_approval' ||
    ((status === 'error' || status === 'cancelled') &&
      pendingApprovals.length > 0)
  );
}

export function buildFailedSendPatch({
  currentInput,
  currentTurns,
  errorMessage,
  fallbackErrorMessage,
  pendingSend,
  pendingUserInput,
  pendingUserTurnId,
}: {
  currentInput: string;
  currentTurns: ChatTurn[];
  errorMessage: string | null;
  fallbackErrorMessage: string;
  pendingSend: AiPendingSendSnapshot | null;
  pendingUserInput: string;
  pendingUserTurnId: string | null;
}): AiFailedSendPatch {
  const failedTurnId = pendingSend?.pendingUserTurnId ?? pendingUserTurnId;
  const failedInput = pendingSend?.pendingUserInput ?? pendingUserInput;
  return {
    chatError: errorMessage ?? fallbackErrorMessage,
    failedPromptRecovery: failedInput && currentInput ? failedInput : '',
    input: failedInput && !currentInput ? failedInput : currentInput,
    turns: failedTurnId
      ? currentTurns.filter((turn) => turn.id !== failedTurnId)
      : currentTurns,
  };
}

export function shouldKeepPendingApprovalsAfterFailedSend({
  pendingApprovals,
  pendingUserTurnId,
}: {
  pendingApprovals: PendingApproval[];
  pendingUserTurnId: string | null;
}): boolean {
  return pendingUserTurnId === null && pendingApprovals.length > 0;
}

export function shouldConfirmRewrite({
  replaceFromSeq,
  turns,
}: {
  replaceFromSeq: number;
  turns: ChatTurn[];
}): boolean {
  return turns.some((turn) => (turn.seq ?? -1) > replaceFromSeq);
}

export function buildSubmitTransition({
  input,
  nowMs,
  turns,
}: {
  input: string;
  nowMs: number;
  turns: ChatTurn[];
}): AiSendTransition | null {
  const trimmed = input.trim();
  if (!trimmed) {
    return null;
  }
  const userTurn: ChatTurn = {
    id: `user-${nowMs}`,
    seq: nextTurnSeq(turns),
    role: 'user',
    content: trimmed,
  };
  const nextTurns = [...turns, userTurn];
  return {
    nextTurns,
    pendingSend: {
      kind: 'normal',
      originalTurns: turns,
      optimisticTurns: nextTurns,
      pendingUserTurnId: userTurn.id,
      pendingUserInput: trimmed,
    },
    pendingUserInput: trimmed,
    pendingUserTurnId: userTurn.id,
  };
}

export function buildPromptEditTransition({
  editingText,
  editingTurnId,
  turns,
}: {
  editingText: string;
  editingTurnId: string | null;
  turns: ChatTurn[];
}): AiPromptEditTransition {
  if (!editingTurnId) {
    return { status: 'invalid' };
  }
  const target = turns.find((turn) => turn.id === editingTurnId);
  const replaceFromSeq = target?.seq;
  const trimmed = editingText.trim();
  if (
    !target ||
    target.role !== 'user' ||
    replaceFromSeq === undefined ||
    !trimmed
  ) {
    return { status: 'invalid' };
  }
  if (trimmed === target.content) {
    return { status: 'unchanged' };
  }
  const rewriteTail = latestSequencedTurn(turns);
  if (!rewriteTail || rewriteTail.seq === undefined) {
    return { status: 'invalid' };
  }
  const editedTurn: ChatTurn = {
    ...target,
    content: trimmed,
    seq: replaceFromSeq,
  };
  const nextTurns = [
    ...turns.filter(
      (turn) => (turn.seq ?? Number.MAX_SAFE_INTEGER) < replaceFromSeq,
    ),
    editedTurn,
  ];
  return {
    status: 'ready',
    replaceFromSeq,
    nextTurns,
    pendingSend: {
      kind: 'edit',
      originalTurns: turns,
      optimisticTurns: nextTurns,
      pendingUserTurnId: editedTurn.id,
      pendingUserInput: trimmed,
    },
    pendingUserInput: trimmed,
    pendingUserTurnId: editedTurn.id,
    sendOptions: {
      replaceFromSeq,
      replaceFromTurnId: target.id,
      replaceTailSeq: rewriteTail.seq,
      replaceTailTurnId: rewriteTail.id,
      persistUserTurn: true,
    },
  };
}

export function buildRetryTurnTransition({
  turn,
  turns,
}: {
  turn: ChatTurn;
  turns: ChatTurn[];
}): AiRetryTransition {
  if (turn.role !== 'assistant' || turn.seq === undefined) {
    return { status: 'invalid' };
  }
  const replaceFromSeq = turn.seq;
  const rewriteTail = latestSequencedTurn(turns);
  if (!rewriteTail || rewriteTail.seq === undefined) {
    return { status: 'invalid' };
  }
  const nextTurns = turns.filter(
    (candidate) => (candidate.seq ?? Number.MAX_SAFE_INTEGER) < replaceFromSeq,
  );
  const trailingUser = [...nextTurns]
    .reverse()
    .find((candidate) => candidate.role === 'user');
  if (!trailingUser) {
    return { status: 'missingTrailingUser', replaceFromSeq };
  }
  return {
    status: 'ready',
    replaceFromSeq,
    nextTurns,
    pendingSend: {
      kind: 'retry',
      originalTurns: turns,
      optimisticTurns: nextTurns,
      pendingUserTurnId: null,
      pendingUserInput: trailingUser.content,
    },
    pendingUserInput: trailingUser.content,
    pendingUserTurnId: null,
    sendOptions: {
      replaceFromSeq,
      replaceFromTurnId: turn.id,
      replaceTailSeq: rewriteTail.seq,
      replaceTailTurnId: rewriteTail.id,
      persistUserTurn: false,
    },
  };
}

export function shouldClearFailedPromptRecovery({
  failedPromptRecovery,
  pendingUserInput,
}: {
  failedPromptRecovery: string;
  pendingUserInput: string | null | undefined;
}): boolean {
  return Boolean(
    failedPromptRecovery &&
      pendingUserInput?.trim() === failedPromptRecovery.trim(),
  );
}

export function resolveFailedPromptRestoreInput(
  currentInput: string,
  failedPromptRecovery: string,
): string {
  return currentInput.trim()
    ? `${failedPromptRecovery}\n\n${currentInput}`
    : failedPromptRecovery;
}

export function shouldClearMissingArtifactQuery({
  activeArtifact,
  isConversationReady,
  isLoadingConversation,
  isSending,
  routeArtifactId,
}: {
  activeArtifact: ArtifactBuffer | null;
  isConversationReady: boolean;
  isLoadingConversation: boolean;
  isSending: boolean;
  routeArtifactId: string | null;
}): boolean {
  return Boolean(
    routeArtifactId &&
      !activeArtifact &&
      !isSending &&
      !isLoadingConversation &&
      isConversationReady,
  );
}

export function resolveActiveArtifact({
  artifacts,
  routeArtifactId,
}: {
  artifacts: ArtifactBuffer[];
  routeArtifactId: string | null;
}): ArtifactBuffer | null {
  if (!routeArtifactId) {
    return null;
  }
  return artifacts.find((entry) => entry.id === routeArtifactId) ?? null;
}

export function resolveAutoOpenArtifactId({
  lastAutoOpenedArtifactId,
  liveArtifacts,
  routeArtifactId,
}: {
  lastAutoOpenedArtifactId: string | null;
  liveArtifacts: ArtifactBuffer[];
  routeArtifactId: string | null;
}): string | null {
  if (liveArtifacts.length === 0) {
    return null;
  }
  if (
    routeArtifactId &&
    liveArtifacts.some((artifact) => artifact.id === routeArtifactId)
  ) {
    return null;
  }
  const primary = liveArtifacts[0];
  if (primary.status !== 'closed') {
    return null;
  }
  if (lastAutoOpenedArtifactId === primary.id) {
    return null;
  }
  return primary.id;
}

export function buildArtifactSearchParams(
  searchParams: URLSearchParams,
  artifactId: string | null,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  if (artifactId) {
    next.set('a', artifactId);
  } else {
    next.delete('a');
  }
  return next;
}

export function resolveChatbotCapableAppIds({
  apps,
  bootstrapChatbotAppIds,
  fallbackAppIds,
}: {
  apps: readonly AiScopeBootstrapApp[] | null | undefined;
  bootstrapChatbotAppIds: readonly string[] | null | undefined;
  fallbackAppIds: readonly string[];
}): string[] {
  if (bootstrapChatbotAppIds && bootstrapChatbotAppIds.length > 0) {
    return [...bootstrapChatbotAppIds];
  }
  const enabled = new Set<string>();
  for (const app of apps ?? []) {
    if (app.enabled) {
      enabled.add(app.app_id);
    }
  }
  return fallbackAppIds.filter((id) => enabled.has(id));
}

export function buildAiScopeOptions({
  apps,
  chatbotCapableAppIds,
}: {
  apps: readonly AiScopeBootstrapApp[] | null | undefined;
  chatbotCapableAppIds: readonly string[];
}): AiScopeOption[] {
  const titlesById = new Map(
    (apps ?? []).map((app) => [app.app_id, app.title]),
  );
  return chatbotCapableAppIds.map((id) => ({
    id,
    title: titlesById.get(id) ?? id.toUpperCase(),
  }));
}

export function sanitizeAllowedAppIds({
  allowedAppIds,
  chatbotCapableAppIds,
}: {
  allowedAppIds: string[] | null;
  chatbotCapableAppIds: readonly string[];
}): string[] | null {
  if (allowedAppIds === null) {
    return null;
  }
  if (chatbotCapableAppIds.length === 0) {
    return allowedAppIds;
  }
  const known = new Set(chatbotCapableAppIds);
  return allowedAppIds.filter((id) => known.has(id));
}

export function mergeToolCalls(
  finalized: ToolCallBuffer[],
  live: ToolCallBuffer[],
): ToolCallBuffer[] {
  const merged = new Map<string, ToolCallBuffer>();
  for (const call of [...finalized, ...live]) {
    merged.set(call.call_id, call);
  }
  return Array.from(merged.values());
}

export function livePendingApprovalToChatApprovals(
  livePendingApproval: LivePendingApprovalInput,
): PendingApproval[] {
  if (!livePendingApproval) {
    return [];
  }
  return [
    {
      approval_id: livePendingApproval.approvalId,
      call_id: livePendingApproval.callId,
      tool: livePendingApproval.tool,
      resource_preview: livePendingApproval.resourcePreview ?? null,
      expires_at_ms: livePendingApproval.expiresAtMs,
      decision:
        livePendingApproval.status === 'pending'
          ? null
          : livePendingApproval.status,
      reason: livePendingApproval.reason ?? null,
    },
  ];
}

export function buildHydratedConversationDraftPatch({
  consumedDraftSourceKey,
  detail,
  locationDraft,
  locationDraftSourceKey,
}: {
  consumedDraftSourceKey: string | null;
  detail: ConversationDetail;
  locationDraft: string | null;
  locationDraftSourceKey: string | null;
}): Pick<FreshChatDraftPatch, 'input' | 'showInsightHint'> | null {
  if (
    !locationDraft ||
    !locationDraftSourceKey ||
    detail.scopeRef !== 'meeting' ||
    detail.turns.length !== 0 ||
    consumedDraftSourceKey === locationDraftSourceKey
  ) {
    return null;
  }
  return {
    input: locationDraft,
    showInsightHint: true,
  };
}

export function nextTurnSeq(turns: ChatTurn[]): number {
  return turns.reduce((max, turn) => Math.max(max, turn.seq ?? -1), -1) + 1;
}

export function mergePendingUserTurn({
  conversationId,
  pendingUserContent,
  turns,
}: {
  conversationId: string | null;
  pendingUserContent: string | null;
  turns: ChatTurn[];
}): ChatTurn[] {
  const content = pendingUserContent?.trim();
  if (!content) {
    return turns;
  }
  const lastTurn = turns.at(-1);
  if (lastTurn?.role === 'user' && lastTurn.content.trim() === content) {
    return turns;
  }
  return [
    ...turns,
    {
      id: `pending-user-${conversationId ?? 'new'}`,
      seq: nextTurnSeq(turns),
      role: 'user',
      content,
    },
  ];
}

function latestSequencedTurn(turns: ChatTurn[]): ChatTurn | null {
  return turns.reduce<ChatTurn | null>((latest, turn) => {
    if (turn.seq === undefined) {
      return latest;
    }
    if (!latest || turn.seq > (latest.seq ?? -1)) {
      return turn;
    }
    return latest;
  }, null);
}
