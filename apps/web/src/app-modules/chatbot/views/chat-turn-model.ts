import type { AiChatMessage } from '../api/chatbot-api';
import type {
  ConversationDetail,
  ConversationTurn as ApiConversationTurn,
} from '../api/conversations-api';
import type {
  ArtifactBuffer,
  ChatStreamStatus,
  DoneMeta,
  PendingApproval,
  ToolCallBuffer,
} from '../api/agent-events';
import type { ChatTurn } from './chat/chat-turn';

export type TerminalChatStreamStatus = Extract<
  ChatStreamStatus,
  'done' | 'cancelled' | 'error'
>;

export interface AssistantTurnContentMessages {
  cancelled: string;
  lengthLimit: string;
  responseFailed: string;
  fallbackResponseFailed: string;
}

export interface AssistantTurnStreamState {
  contentBuffer: string;
  reasoningBuffer: string;
  errorMessage: string | null;
  finishReason:
    | 'stop'
    | 'length'
    | 'cancelled'
    | 'error'
    | 'awaiting_approval'
    | null;
  doneMeta: DoneMeta | null;
  toolCalls: ToolCallBuffer[];
  pendingApprovals: PendingApproval[];
  artifacts: ArtifactBuffer[];
}

export interface ChatbotConversationScopeInfo {
  ref: string;
  resourceId: string;
  title: string | null;
}

export interface NormalizedConversationDetail {
  activeConversationId: string;
  scopeInfo: ChatbotConversationScopeInfo | null;
  turns: ChatTurn[];
}

export function detailToTurns(detail: ConversationDetail): ChatTurn[] {
  return detail.turns.map(apiTurnToChatTurn);
}

export function normalizeConversationDetail(
  detail: ConversationDetail,
): NormalizedConversationDetail {
  return {
    activeConversationId: detail.id,
    scopeInfo:
      detail.scopeRef && detail.scopeResourceId
        ? {
            ref: detail.scopeRef,
            resourceId: detail.scopeResourceId,
            title: null,
          }
        : null,
    turns: detailToTurns(detail),
  };
}

export function collectArtifacts(
  turns: ChatTurn[],
  liveArtifacts: ArtifactBuffer[],
): ArtifactBuffer[] {
  const entries = new Map<string, ArtifactBuffer>();
  for (const turn of turns) {
    if (!turn.artifacts) continue;
    for (const artifact of turn.artifacts) {
      mergeArtifactEntry(entries, artifact);
    }
  }
  for (const artifact of liveArtifacts) {
    mergeArtifactEntry(entries, artifact);
  }
  return Array.from(entries.values());
}

function mergeArtifactEntry(
  entries: Map<string, ArtifactBuffer>,
  artifact: ArtifactBuffer,
): void {
  const existing = entries.get(artifact.id);
  if (!existing) {
    entries.set(artifact.id, artifact);
    return;
  }
  entries.set(artifact.id, {
    ...existing,
    ...artifact,
    title: artifact.title?.trim() ? artifact.title : existing.title,
    language: artifact.language ?? existing.language,
    content: artifact.content.trim() ? artifact.content : existing.content,
    kind: artifact.kind ?? existing.kind,
    graphRunId: artifact.graphRunId ?? existing.graphRunId,
    conversationId: artifact.conversationId ?? existing.conversationId,
    conversationTurnId:
      artifact.conversationTurnId ?? existing.conversationTurnId,
    createdAt: artifact.createdAt ?? existing.createdAt,
    completedAt: artifact.completedAt ?? existing.completedAt,
  });
}

export function resolveAssistantTurnContent(
  contentBuffer: string,
  options: {
    status: TerminalChatStreamStatus;
    errorMessage: string | null;
    finishReason: AssistantTurnStreamState['finishReason'];
    hasArtifacts: boolean;
  },
  messages: AssistantTurnContentMessages,
): string {
  const { status, errorMessage, finishReason, hasArtifacts } = options;
  if (contentBuffer) {
    return contentBuffer;
  }
  if (status === 'cancelled') {
    return messages.cancelled;
  }
  if (status === 'error') {
    return errorMessage ?? messages.responseFailed;
  }
  if (finishReason === 'length') {
    return messages.lengthLimit;
  }
  // A successful response that streamed only artifacts has no chat-bubble
  // text; keep the message empty so the artifact card stands alone.
  if (hasArtifacts) {
    return '';
  }
  return messages.fallbackResponseFailed;
}

export function buildAssistantTurnFromStream({
  chatState,
  content,
  id,
  seq,
  status,
}: {
  chatState: AssistantTurnStreamState;
  content: string;
  id: string;
  seq: number;
  status: TerminalChatStreamStatus;
}): ChatTurn {
  return {
    id,
    seq,
    role: 'assistant',
    content,
    reasoning: chatState.reasoningBuffer || undefined,
    reasoningStatus: status,
    finishReason: chatState.finishReason,
    responseStatus: status === 'done' ? undefined : status,
    provider: chatState.doneMeta?.provider ?? undefined,
    policy: chatState.doneMeta?.policy ?? null,
    chosenPool: chatState.doneMeta?.chosen_pool ?? null,
    decisionReason: chatState.doneMeta?.decision_reason ?? null,
    forcedLocal: chatState.doneMeta?.forced_local ?? false,
    piiHits: chatState.doneMeta?.pii_hits ?? [],
    toolCalls: chatState.toolCalls,
    pendingApprovals: chatState.pendingApprovals,
    artifacts: chatState.artifacts,
  };
}

export function serializeTurnsForModel(turns: ChatTurn[]): AiChatMessage[] {
  return turns.flatMap((turn) => {
    const content = serializeTurnForModel(turn);
    if (!content.trim()) {
      return [];
    }
    return [{ role: turn.role, content }];
  });
}

export function serializeTurnForModel(turn: ChatTurn): string {
  const artifacts = turn.artifacts ?? [];
  if (artifacts.length === 0) {
    return turn.content;
  }
  const blocks = artifacts.map((artifact) => {
    const titleAttr = artifact.title
      ? ` title="${artifact.title.replace(/"/g, '\u201d')}"`
      : '';
    const languageAttr = artifact.language
      ? ` language="${artifact.language.replace(/"/g, '\u201d')}"`
      : '';
    return `<artifact type="${artifact.type}"${languageAttr}${titleAttr}>\n${artifact.content}\n</artifact>`;
  });
  if (!turn.content.trim()) {
    return blocks.join('\n\n');
  }
  return `${turn.content}\n\n${blocks.join('\n\n')}`;
}

export function apiTurnToChatTurn(turn: ApiConversationTurn): ChatTurn {
  return {
    id: turn.id,
    seq: turn.seq,
    role: turn.role,
    content: turn.content,
    reasoning: turn.reasoning ?? undefined,
    reasoningStatus: (turn.reasoningStatus ??
      undefined) as ChatTurn['reasoningStatus'],
    finishReason: (turn.finishReason ?? null) as ChatTurn['finishReason'],
    responseStatus: (turn.responseStatus ??
      undefined) as ChatTurn['responseStatus'],
    provider: turn.provider ?? undefined,
    policy: turn.policy ?? null,
    chosenPool: turn.chosenPool ?? null,
    decisionReason: turn.decisionReason ?? null,
    forcedLocal: Boolean(turn.forcedLocal),
    piiHits: turn.piiHits ?? [],
    toolCalls: (turn.toolCalls ?? []) as unknown as ChatTurn['toolCalls'],
    pendingApprovals: (turn.pendingApprovals ??
      []) as unknown as ChatTurn['pendingApprovals'],
    artifacts: (turn.artifacts ?? []).map((artifact) => ({
      id: artifact.id,
      type: artifact.type,
      title: artifact.title ?? null,
      language: artifact.language ?? null,
      content: artifact.content,
      status: artifact.status === 'open' ? 'open' : 'closed',
      conversationTurnId: turn.id,
    })),
  };
}
