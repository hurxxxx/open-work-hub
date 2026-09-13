import { i18n } from '@/src/platform/i18n';
import { useCallback, useMemo, useRef, useSyncExternalStore } from 'react';
import type { PendingApproval, RawAgentEvent } from './agent-events';
import {
  applyChatStreamEvent,
  cancelChatStreamState,
  CHAT_STREAM_INITIAL_STATE,
  createChatStreamStartState,
  failChatStreamState,
  markChatStreamOpened,
  replaceChatStreamPendingApprovals,
  resetChatStreamState,
  syncResponseToChatStreamState,
  upsertChatStreamPendingApproval,
  type ChatStreamState,
} from './chat-stream-state';
import {
  AiApiError,
  sendAiChat,
  streamAiChat,
  streamAiExistingRun,
  streamAiChatResume,
  type AiChatStreamRequest,
  type ResumeAiChatRequest,
} from './chatbot-api';
import { iterSseEvents } from './sse-parser';

export type { ChatStreamState, ChatTransport } from './chat-stream-state';

export interface UseChatStreamApi {
  state: ChatStreamState;
  isRunOwner: boolean;
  send: (payload: AiChatStreamRequest) => Promise<void>;
  resume: (
    payload: ResumeAiChatRequest,
    options?: { seedApproval?: PendingApproval | null },
  ) => Promise<void>;
  recover: (conversationId: string, runId: string) => Promise<void>;
  abort: () => void;
  reset: (options?: {
    keepPendingApprovals?: boolean;
    preserveActiveRun?: boolean;
  }) => void;
  replacePendingApprovals: (approvals: PendingApproval[]) => void;
  upsertPendingApproval: (approval: PendingApproval) => void;
}

const AI_STREAM_ENABLED_STORAGE_KEY = 'open-work-hub.ai.streamEnabled';

interface ChatStreamRuntime {
  abortController: AbortController | null;
  cleanupTimer: ReturnType<typeof setTimeout> | null;
  key: string;
  scopeKey: string;
  listeners: Set<() => void>;
  ownerId: string | null;
  runId: number;
  state: ChatStreamState;
}

const chatStreamRuntimes = new Map<string, ChatStreamRuntime>();
let chatStreamConsumerSequence = 0;
const CHAT_STREAM_RUNTIME_RETENTION_MS = 30 * 60 * 1000;

function createChatStreamRuntime(
  key: string,
  scopeKey: string,
): ChatStreamRuntime {
  return {
    abortController: null,
    cleanupTimer: null,
    key,
    scopeKey,
    listeners: new Set(),
    ownerId: null,
    runId: 0,
    state: CHAT_STREAM_INITIAL_STATE,
  };
}

function getChatStreamRuntime(
  scopeKey: string,
  conversationId?: string | null,
): ChatStreamRuntime {
  const runtimeKey = `${scopeKey}#${conversationId ?? 'new'}`;
  const existing = chatStreamRuntimes.get(runtimeKey);
  if (existing) {
    return existing;
  }
  const created = createChatStreamRuntime(runtimeKey, scopeKey);
  chatStreamRuntimes.set(runtimeKey, created);
  return created;
}

function clearRuntimeCleanup(runtime: ChatStreamRuntime) {
  if (runtime.cleanupTimer !== null) {
    clearTimeout(runtime.cleanupTimer);
    runtime.cleanupTimer = null;
  }
}

function scheduleRuntimeCleanup(runtime: ChatStreamRuntime) {
  clearRuntimeCleanup(runtime);
  if (runtime.listeners.size > 0 || runtime.state.status === 'streaming') {
    return;
  }
  runtime.cleanupTimer = setTimeout(() => {
    runtime.cleanupTimer = null;
    if (
      runtime.listeners.size === 0 &&
      runtime.state.status !== 'streaming' &&
      chatStreamRuntimes.get(runtime.key) === runtime
    ) {
      chatStreamRuntimes.delete(runtime.key);
    }
  }, CHAT_STREAM_RUNTIME_RETENTION_MS);
}

function updateRuntimeState(
  runtime: ChatStreamRuntime,
  next: ChatStreamState | ((prev: ChatStreamState) => ChatStreamState),
) {
  runtime.state = typeof next === 'function' ? next(runtime.state) : next;
  if (runtime.state.conversationId) {
    const key = `${runtime.scopeKey}#${runtime.state.conversationId}`;
    if (key !== runtime.key) {
      chatStreamRuntimes.delete(runtime.key);
      runtime.key = key;
      chatStreamRuntimes.set(key, runtime);
    }
  }
  for (const listener of runtime.listeners) {
    listener();
  }
  if (runtime.listeners.size === 0) {
    scheduleRuntimeCleanup(runtime);
  }
}

export function useChatStream(
  token: string | null,
  runtimeKey?: string | null,
  options: {
    disableSyncFallback?: boolean;
    conversationId?: string | null;
  } = {},
): UseChatStreamApi {
  const disableSyncFallback = options.disableSyncFallback ?? false;
  const consumerIdRef = useRef<string | null>(null);
  if (consumerIdRef.current === null) {
    chatStreamConsumerSequence += 1;
    consumerIdRef.current = `chat-stream-consumer-${chatStreamConsumerSequence}`;
  }
  const localRuntimeKeyRef = useRef<string | null>(null);
  if (localRuntimeKeyRef.current === null) {
    localRuntimeKeyRef.current = `chat-stream-local-${consumerIdRef.current}`;
  }
  const resolvedRuntimeKey = runtimeKey || localRuntimeKeyRef.current;
  const runtime = useMemo(
    () => getChatStreamRuntime(resolvedRuntimeKey, options.conversationId),
    [resolvedRuntimeKey, options.conversationId],
  );
  const state = useSyncExternalStore(
    useCallback(
      (listener) => {
        clearRuntimeCleanup(runtime);
        runtime.listeners.add(listener);
        return () => {
          runtime.listeners.delete(listener);
          scheduleRuntimeCleanup(runtime);
        };
      },
      [runtime],
    ),
    useCallback(() => runtime.state, [runtime]),
    useCallback(() => runtime.state, [runtime]),
  );

  const abort = useCallback(() => {
    const controller = runtime.abortController;
    if (!controller) {
      return;
    }
    controller.abort('stop');
    if (runtime.state.status === 'streaming') {
      updateRuntimeState(runtime, cancelChatStreamState);
    }
  }, [runtime]);

  const setStateForRun = useCallback(
    (
      runId: number,
      next: ChatStreamState | ((prev: ChatStreamState) => ChatStreamState),
    ) => {
      if (runtime.runId !== runId) {
        return;
      }
      updateRuntimeState(runtime, next);
    },
    [runtime],
  );

  const reset = useCallback(
    (options?: {
      keepPendingApprovals?: boolean;
      preserveActiveRun?: boolean;
    }) => {
      if (options?.preserveActiveRun && runtime.state.status !== 'idle') {
        return;
      }
      runtime.runId += 1;
      runtime.abortController?.abort();
      runtime.abortController = null;
      runtime.ownerId = null;
      updateRuntimeState(runtime, (prev) =>
        resetChatStreamState(prev, {
          keepPendingApprovals: options?.keepPendingApprovals,
        }),
      );
    },
    [runtime],
  );

  const replacePendingApprovals = useCallback(
    (approvals: PendingApproval[]) => {
      updateRuntimeState(runtime, (prev) =>
        replaceChatStreamPendingApprovals(prev, approvals),
      );
    },
    [runtime],
  );

  const upsertPendingApproval = useCallback(
    (approval: PendingApproval) => {
      updateRuntimeState(runtime, (prev) =>
        upsertChatStreamPendingApproval(prev, approval),
      );
    },
    [runtime],
  );

  const send = useCallback(
    async (
      payload: AiChatStreamRequest,
      existing?: { conversationId: string; runId: string },
    ) => {
      if (!token) {
        throw new AiApiError(401, i18n.t('auth:errors.noActiveSession'));
      }

      runtime.abortController?.abort();
      const runId = runtime.runId + 1;
      runtime.runId = runId;
      runtime.ownerId = consumerIdRef.current;
      const controller = new AbortController();
      runtime.abortController = controller;

      if (!existing && !disableSyncFallback && !shouldUseStreamingTransport()) {
        await sendViaSyncFallback({
          payload,
          token,
          runId,
          setStateForRun,
        });
        return;
      }

      setStateForRun(
        runId,
        createChatStreamStartState({
          transport: 'stream',
          pendingUserContent: latestUserContent(payload),
        }),
      );

      let streamOpened = false;
      const terminalState = { received: false };
      try {
        const response = existing
          ? await streamAiExistingRun(
              token,
              existing.runId,
              existing.conversationId,
              controller.signal,
            )
          : await streamAiChat({ payload, token, signal: controller.signal });
        if (!response.body) {
          throw new AiApiError(0, i18n.t('apps:ai.errors.emptySseBody'));
        }

        streamOpened = true;
        setStateForRun(runId, markChatStreamOpened);

        for await (const message of iterSseEvents(
          response.body,
          controller.signal,
        )) {
          const parsed = parseMessage(message.data);
          if (!parsed) {
            continue;
          }
          const terminal = isTerminalAgentEvent(parsed);
          if (terminal) {
            terminalState.received = true;
          }
          setStateForRun(runId, (prev) => {
            const { next } = applyChatStreamEvent(prev, parsed);
            return next;
          });
          if (terminal) {
            break;
          }
        }
        if (!terminalState.received) {
          setStateForRun(
            runId,
            controller.signal.aborted
              ? cancelChatStreamState
              : (prev) =>
                  failChatStreamState(
                    prev,
                    i18n.t('apps:ai.errors.streamFailed'),
                  ),
          );
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          if (!terminalState.received) {
            setStateForRun(runId, cancelChatStreamState);
          }
          return;
        }

        if (!streamOpened) {
          if (disableSyncFallback || existing) {
            setStateForRun(runId, (prev) =>
              failChatStreamState(
                prev,
                error instanceof Error
                  ? error.message
                  : i18n.t('apps:ai.errors.streamFailed'),
              ),
            );
            return;
          }
          // Auto-fallback to the sync endpoint when SSE never opened (proxy
          // buffering, transient gateway, etc.) so the user still gets a
          // reply. `/api/v1/chatbot/chat` now accepts the same persistence
          // fields as `/chat/stream`, so conversation history continues to
          // append even when the transport downgrades.
          await sendViaSyncFallback({
            payload,
            token,
            runId,
            setStateForRun,
            fallbackReason: error,
          });
          return;
        }

        setStateForRun(runId, (prev) =>
          failChatStreamState(
            prev,
            error instanceof Error
              ? error.message
              : (prev.errorMessage ?? i18n.t('apps:ai.errors.streamFailed')),
          ),
        );
      } finally {
        if (runtime.abortController === controller) {
          runtime.abortController = null;
        }
      }
    },
    [disableSyncFallback, runtime, setStateForRun, token],
  );

  const recover = useCallback(
    async (conversationId: string, runId: string) => {
      if (runtime.state.status === 'streaming') return;
      await send(
        { messages: [], backend_mode: 'local' },
        { conversationId, runId },
      );
    },
    [runtime, send],
  );

  const resume = useCallback(
    async (
      payload: ResumeAiChatRequest,
      options?: { seedApproval?: PendingApproval | null },
    ) => {
      if (!token) {
        throw new AiApiError(401, i18n.t('auth:errors.noActiveSession'));
      }

      runtime.abortController?.abort();
      const runId = runtime.runId + 1;
      runtime.runId = runId;
      runtime.ownerId = consumerIdRef.current;
      const controller = new AbortController();
      runtime.abortController = controller;
      const seededApproval = options?.seedApproval ?? null;

      setStateForRun(
        runId,
        createChatStreamStartState({
          transport: 'stream',
          pendingApprovals: seededApproval ? [seededApproval] : [],
        }),
      );

      const terminalState = { received: false };
      try {
        const response = await streamAiChatResume({
          payload,
          token,
          signal: controller.signal,
        });
        if (!response.body) {
          throw new AiApiError(0, i18n.t('apps:ai.errors.emptySseBody'));
        }

        setStateForRun(runId, markChatStreamOpened);

        for await (const message of iterSseEvents(
          response.body,
          controller.signal,
        )) {
          const parsed = parseMessage(message.data);
          if (!parsed) {
            continue;
          }
          const terminal = isTerminalAgentEvent(parsed);
          if (terminal) {
            terminalState.received = true;
          }
          setStateForRun(runId, (prev) => {
            const { next } = applyChatStreamEvent(prev, parsed);
            return next;
          });
          if (terminal) {
            break;
          }
        }
        if (!terminalState.received) {
          setStateForRun(
            runId,
            controller.signal.aborted
              ? cancelChatStreamState
              : (prev) =>
                  failChatStreamState(
                    prev,
                    i18n.t('apps:ai.errors.resumeStreamFailed'),
                  ),
          );
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          if (!terminalState.received) {
            setStateForRun(runId, cancelChatStreamState);
          }
          return;
        }

        setStateForRun(runId, (prev) =>
          failChatStreamState(
            prev,
            error instanceof Error
              ? error.message
              : (prev.errorMessage ??
                  i18n.t('apps:ai.errors.resumeStreamFailed')),
          ),
        );
      } finally {
        if (runtime.abortController === controller) {
          runtime.abortController = null;
        }
      }
    },
    [runtime, setStateForRun, token],
  );

  return {
    state,
    isRunOwner: runtime.ownerId === consumerIdRef.current,
    send,
    resume,
    abort,
    recover,
    reset,
    replacePendingApprovals,
    upsertPendingApproval,
  };
}

async function sendViaSyncFallback({
  payload,
  token,
  runId,
  setStateForRun,
  fallbackReason,
}: {
  payload: AiChatStreamRequest;
  token: string;
  runId: number;
  setStateForRun: (
    runId: number,
    next: ChatStreamState | ((prev: ChatStreamState) => ChatStreamState),
  ) => void;
  fallbackReason?: unknown;
}) {
  setStateForRun(
    runId,
    createChatStreamStartState({
      transport: 'sync',
      pendingUserContent: latestUserContent(payload),
    }),
  );

  const { stream_reasoning: _streamReasoning, ...syncPayload } = payload;
  void _streamReasoning;

  try {
    const response = await sendAiChat(syncPayload, token, {});
    setStateForRun(runId, syncResponseToChatStreamState(response));
  } catch (error) {
    const resolved = error instanceof Error ? error : fallbackReason;
    setStateForRun(runId, (prev) => ({
      ...prev,
      status: 'error',
      errorMessage:
        resolved instanceof Error
          ? resolved.message
          : i18n.t('apps:ai.errors.responseFailed'),
    }));
  }
}

function latestUserContent(payload: AiChatStreamRequest): string | null {
  for (let index = payload.messages.length - 1; index >= 0; index -= 1) {
    const message = payload.messages[index];
    if (message?.role === 'user' && message.content.trim()) {
      return message.content.trim();
    }
  }
  return null;
}

function shouldUseStreamingTransport(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }
  try {
    const stored = window.localStorage.getItem(AI_STREAM_ENABLED_STORAGE_KEY);
    if (stored === '0' || stored === 'false' || stored === 'off') {
      return false;
    }
  } catch {
    return true;
  }
  return supportsStreamingTransport();
}

function supportsStreamingTransport(): boolean {
  return (
    typeof fetch === 'function' &&
    typeof AbortController !== 'undefined' &&
    typeof ReadableStream !== 'undefined' &&
    typeof TextDecoder !== 'undefined'
  );
}

function parseMessage(data: string): RawAgentEvent | null {
  try {
    return JSON.parse(data) as RawAgentEvent;
  } catch (error) {
    console.debug('[useChatStream] failed to parse SSE data', error);
    return null;
  }
}

function isTerminalAgentEvent(event: RawAgentEvent): boolean {
  return event.type === 'done';
}
