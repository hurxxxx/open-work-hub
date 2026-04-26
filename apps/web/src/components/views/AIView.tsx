import { motion } from 'motion/react';
import { Sparkles } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  AiApiError,
  abandonAiApproval,
  getLlmHealth,
  resolveAiApproval,
  type AiBackendMode,
  type AiChatMessage,
  type LlmHealthResponse,
} from '@/src/domains/ai/ai-api';
import {
  CONVERSATIONS_UPDATED_EVENT,
  getConversation,
  type ConversationDetail,
  type ConversationLivePendingApproval,
  type ConversationTurn as ApiConversationTurn,
} from '@/src/domains/ai/conversations-api';
import { useChatStream } from '@/src/domains/ai/useChatStream';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { getMeeting } from '@/src/domains/meeting/meeting-api';
import {
  buildWorkspaceAppPath,
  resolveToolInvocationHref,
} from '@/src/domains/workspaces/workspace-utils';
import { useWorkspaceBootstrapContext } from '@/src/domains/workspaces/workspace-bootstrap-context';
import { NAV_ITEMS } from '@/src/constants';
import { ChatThread } from '@/src/components/views/chat/ChatThread';
import { ApprovalModal } from '@/src/components/views/chat/ApprovalModal';
import { ArtifactPanel } from '@/src/components/views/chat/ArtifactPanel';
import { ToolCallCard } from '@/src/components/views/chat/ToolCallCard';
import { ChatTopBar } from '@/src/components/views/chat/ChatTopBar';
import { ChatComposer } from '@/src/components/views/chat/ChatComposer';
import { EmptyState } from '@/src/components/views/chat/EmptyState';
import type { ChatTurn } from '@/src/components/views/chat/MessageBubble';
import type {
  ArtifactBuffer,
  PendingApproval,
  ToolCallBuffer,
} from '@/src/domains/ai/agent-events';
import type { NavItem } from '@/src/constants';

const AI_BACKEND_MODE_STORAGE_KEY = 'aidoo.ai.backendMode';
const AI_SCOPE_STORAGE_PREFIX = 'aidoo.ai.scope.';

function chatScopeStorageKey(workspaceSlug: string | undefined): string | null {
  if (!workspaceSlug) return null;
  return `${AI_SCOPE_STORAGE_PREFIX}${workspaceSlug}`;
}

function readPersistedScope(workspaceSlug: string | undefined): string[] | null {
  const key = chatScopeStorageKey(workspaceSlug);
  if (!key || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return parsed.filter((item): item is string => typeof item === 'string');
  } catch {
    return null;
  }
}

function writePersistedScope(
  workspaceSlug: string | undefined,
  selection: string[] | null,
): void {
  const key = chatScopeStorageKey(workspaceSlug);
  if (!key || typeof window === 'undefined') return;
  try {
    if (selection === null) {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, JSON.stringify(selection));
    }
  } catch {
    // Quota or disabled storage — picker still works in-memory for the session.
  }
}

interface AiDraftLocationState {
  aiDraft: string;
  aiDraftSourceKey: string;
  aiDraftOrigin: 'meeting_insight';
}

function readAiDraftLocationState(state: unknown): AiDraftLocationState | null {
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

function readInitialBackendMode(): AiBackendMode {
  if (typeof window === 'undefined') {
    return 'auto';
  }

  const savedMode = window.localStorage.getItem(AI_BACKEND_MODE_STORAGE_KEY);
  if (savedMode === 'auto' || savedMode === 'local') {
    return savedMode;
  }

  return 'auto';
}

function resolveAssistantTurnContent(
  contentBuffer: string,
  options: {
    status: 'done' | 'cancelled' | 'error';
    errorMessage: string | null;
    finishReason: 'stop' | 'length' | 'cancelled' | 'error' | 'awaiting_approval' | null;
    hasArtifacts: boolean;
  },
): string {
  const { status, errorMessage, finishReason, hasArtifacts } = options;
  if (contentBuffer) {
    return contentBuffer;
  }
  if (status === 'cancelled') {
    return '응답이 중단되었습니다.';
  }
  if (status === 'error') {
    return errorMessage ?? '응답 중 오류가 발생했습니다.';
  }
  if (finishReason === 'length') {
    return '응답이 토큰 한도에 도달해 중간에서 잘렸습니다. 질문 범위를 줄이거나 이어서 요청하세요.';
  }
  // A successful response that streamed only artifacts has no chat-bubble
  // text — render an empty string so the message area shows the artifact
  // card alone instead of a bogus "failed" placeholder.
  if (hasArtifacts) {
    return '';
  }
  return '응답을 생성하지 못했습니다.';
}

interface ScopeInfo {
  ref: 'meeting';
  resourceId: string;
  meetingTitle: string | null;
}

type ApprovalActionKind = 'approve' | 'reject' | 'abandon' | 'resume';

function ScopeChip({
  scope,
  workspaceSlug,
}: {
  scope: ScopeInfo;
  workspaceSlug: string | undefined;
}) {
  const label = scope.meetingTitle
    ? `회의 "${scope.meetingTitle}" 컨텍스트`
    : '회의 컨텍스트';
  const commonClass =
    'app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink transition-colors hover:border-app-accent';
  if (!workspaceSlug) {
    return (
      <span role="status" className={commonClass} data-testid="ai-scope-chip">
        <Sparkles size={12} className="text-app-accent" aria-hidden="true" />
        {label}
      </span>
    );
  }
  return (
    <Link
      to={buildWorkspaceAppPath(workspaceSlug, 'meeting', `/${scope.resourceId}`)}
      role="status"
      aria-label={`${label} — 회의로 돌아가기`}
      className={`${commonClass} no-underline`}
      data-testid="ai-scope-chip"
    >
      <Sparkles size={12} className="text-app-accent" aria-hidden="true" />
      {label}
    </Link>
  );
}

export const AIView = () => {
  const { status: authStatus, token, user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { workspaceSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  // `c` query param is the durable source of truth for which persisted
  // conversation this tab is showing. The sidebar navigates to
  // `/w/:slug/ai?c=<id>` to switch threads; the bare `/w/:slug/ai` path
  // opens a fresh chat. Stream-created conversations write themselves back
  // into this param so a page refresh resumes the same thread.
  const routeConversationId = searchParams.get('c');
  // `a` query param tracks which artifact's side panel is open. Bookmarks
  // and page refreshes resume with the same panel visible; closing the
  // panel clears the param via `handleCloseArtifact`.
  const routeArtifactId = searchParams.get('a');
  // Meeting-insight deep-link `draft` param (Step E.4). Populated when
  // the user clicks "챗에서 진행" on a meeting AI suggestion card and
  // becomes the composer's starting value on the next fresh-chat mount.
  // The companion params (`context`, `context_id`, `insight_id`,
  // `insight_kind`) are cleared alongside `draft` in the same replace
  // call; they carry no runtime behavior in this slice and are reserved
  // for the Step F scope-bound conversation flow.
  const routeDraft = searchParams.get('draft');
  const locationDraftState = readAiDraftLocationState(location.state);
  const locationDraft = locationDraftState?.aiDraft ?? null;
  const locationDraftSourceKey = locationDraftState?.aiDraftSourceKey ?? null;
  const pendingDraft = locationDraftState?.aiDraft ?? routeDraft;
  const pendingDraftSourceKey =
    locationDraftState?.aiDraftSourceKey ??
    (() => {
      const insightId = searchParams.get('insight_id');
      if (insightId) {
        return `meeting-insight:${insightId}`;
      }
      return routeDraft ? `draft:${routeDraft}` : null;
    })();
  // Read bootstrap state from the shell context (AppContent already fetched
  // it). Previously AIView issued its own GET /api/v1/workspaces/:slug/bootstrap
  // on every mount, which also briefly fell back to the full static NAV_ITEMS
  // slice in the slash menu while the duplicate request was in flight.
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const [health, setHealth] = useState<LlmHealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [backendMode, setBackendMode] = useState<AiBackendMode>(
    readInitialBackendMode,
  );
  // ``null`` = let the server expose every entitled tool (legacy default).
  // Persisted per-workspace in localStorage; reset to ``null`` automatically
  // when the workspace's chatbot_app_ids drop the previously selected ids.
  const [allowedAppIds, setAllowedAppIds] = useState<string[] | null>(
    () => readPersistedScope(workspaceSlug),
  );
  const chatbotCapableAppIds = useMemo(
    () => workspaceBootstrap.data?.chatbot_app_ids ?? [],
    [workspaceBootstrap.data?.chatbot_app_ids],
  );
  const scopeOptions = useMemo(() => {
    const apps = workspaceBootstrap.data?.apps ?? [];
    const titlesById = new Map(apps.map((app) => [app.app_id, app.title]));
    return chatbotCapableAppIds.map((id) => ({
      id,
      title: titlesById.get(id) ?? id.toUpperCase(),
    }));
  }, [chatbotCapableAppIds, workspaceBootstrap.data?.apps]);
  // Strip ids that are no longer chatbot-capable so a stale selection
  // doesn't keep narrowing the surface to apps that no longer expose tools.
  const sanitizedAllowedAppIds = useMemo(() => {
    if (allowedAppIds === null) return null;
    if (chatbotCapableAppIds.length === 0) return allowedAppIds;
    const known = new Set(chatbotCapableAppIds);
    return allowedAppIds.filter((id) => known.has(id));
  }, [allowedAppIds, chatbotCapableAppIds]);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState('');
  const [chatError, setChatError] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [pendingUserTurnId, setPendingUserTurnId] = useState<string | null>(
    null,
  );
  const [pendingUserInput, setPendingUserInput] = useState('');
  // Only tracks a conversation id once the view can safely append to it:
  // either hydration succeeded for `?c=` or the current stream emitted
  // `conversation_attached`. This avoids writing into an existing thread
  // before its history has been loaded.
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  // Tracks the resolved scope binding for the current conversation. `null`
  // means free chat (no scope). When a meeting-scoped conversation is
  // loaded, meetingTitle is filled asynchronously via a separate fetch so
  // the chip can display the meeting name instead of a generic label.
  const [scopeInfo, setScopeInfo] = useState<ScopeInfo | null>(null);
  const [approvalAction, setApprovalAction] = useState<{
    approvalId: string;
    kind: ApprovalActionKind;
  } | null>(null);
  const chat = useChatStream(token);
  const {
    abort: abortChat,
    replacePendingApprovals,
    reset: resetChat,
    resume: resumeChat,
    upsertPendingApproval,
  } = chat;
  const isSending = chat.state.status === 'streaming';
  const isConversationReady =
    routeConversationId === null || activeConversationId === routeConversationId;
  const finalizedToolCalls = useMemo(
    () => turns.flatMap((turn) => turn.toolCalls ?? []),
    [turns],
  );
  const visibleToolCalls = useMemo(
    () => mergeToolCalls(finalizedToolCalls, chat.state.toolCalls),
    [chat.state.toolCalls, finalizedToolCalls],
  );
  const pendingApproval = useMemo(
    () =>
      chat.state.pendingApprovals.find((approval) => approval.decision === null) ??
      null,
    [chat.state.pendingApprovals],
  );
  const resumableApproval = useMemo(
    () =>
      chat.state.pendingApprovals.find(
        (approval) =>
          approval.decision === 'approved' || approval.decision === 'rejected',
      ) ?? null,
    [chat.state.pendingApprovals],
  );
  const blockingApproval = pendingApproval ?? resumableApproval;
  const isComposerDisabled =
    isSending || isLoadingConversation || !isConversationReady || blockingApproval !== null;

  // Slash-command candidates: merge workspace bootstrap nav (filters out
  // disabled/unauthorized tools) with the local NAV_ITEMS registry (supplies
  // icons + full metadata). Falls back to the local AI-only list while
  // bootstrap is still loading so the menu stays usable.
  const slashCommandItems = useMemo(() => {
    const registry = new Map(NAV_ITEMS.map((item) => [item.id, item]));
    const bootstrapNav = workspaceBootstrap.data?.nav ?? null;
    if (!bootstrapNav) {
      return NAV_ITEMS.filter((item) => item.appId === 'ai');
    }
    return bootstrapNav
      .filter((entry) => entry.app_id === 'ai')
      .map((entry) => {
        const localItem = registry.get(entry.id);
        if (!localItem) {
          return null;
        }
        return {
          ...localItem,
          title: entry.title,
          category: entry.category,
        };
      })
      .filter((item): item is NavItem => item !== null);
  }, [workspaceBootstrap.data]);

  const currentConversationId = activeConversationId ?? routeConversationId;
  const abortHydrateRef = useRef<AbortController | null>(null);
  const skipHydrationConversationIdRef = useRef<string | null>(null);
  const autoResumeAttemptedApprovalsRef = useRef<Set<string>>(new Set());
  // Tracks the draft source key only after the draft text has actually
  // landed in component state. Deferring the write avoids a StrictMode
  // double-effect bug where the first mount run mutates the ref, the
  // second mount run skips consumption, and the queued `setInput(...)`
  // never makes it to the committed render.
  const consumedDraftRef = useRef<string | null>(null);
  // The consume path clears the `draft` URL param via setSearchParams,
  // which changes `routeDraft` and triggers another run of the
  // hydration effect. Without this guard, that run would execute the
  // unconditional `setInput('')` reset and wipe the draft we just
  // injected. Setting the flag immediately before `setSearchParams`
  // means the very next run skips its reset, then clears the flag.
  const skipNextHydrationResetRef = useRef(false);

  const syncLivePendingApproval = useCallback((
    livePendingApproval: ConversationLivePendingApproval | null | undefined,
  ) => {
    if (!livePendingApproval) {
      setApprovalError(null);
      replacePendingApprovals([]);
      return;
    }
    replacePendingApprovals([
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
    ]);
  }, [replacePendingApprovals]);

  const resumePendingApproval = useCallback(async (approval: PendingApproval) => {
    if (!token || !currentConversationId) {
      setApprovalError('대화 컨텍스트를 확인하지 못했습니다.');
      return;
    }
    setApprovalAction({ approvalId: approval.approval_id, kind: 'resume' });
    setApprovalError(null);
    try {
      await resumeChat(
        {
          conversation_id: currentConversationId,
          approval_id: approval.approval_id,
          ...(sanitizedAllowedAppIds !== null
            ? { allowed_app_ids: sanitizedAllowedAppIds }
            : {}),
        },
        {
          seedApproval: approval,
        },
      );
    } catch (error) {
      if (
        error instanceof AiApiError &&
        (error.status === 404 || error.status === 410)
      ) {
        replacePendingApprovals([]);
      }
      setApprovalError(
        error instanceof Error
          ? error.message
          : '승인된 작업 재개에 실패했습니다.',
      );
    } finally {
      setApprovalAction((current) =>
        current?.approvalId === approval.approval_id ? null : current,
      );
    }
  }, [currentConversationId, replacePendingApprovals, resumeChat, sanitizedAllowedAppIds, token]);

  const handleResolveApproval = useCallback(async (
    approval: PendingApproval,
    decision: 'approved' | 'rejected',
    reason?: string,
  ) => {
    if (!token) {
      setApprovalError('로그인이 필요합니다.');
      return;
    }
    setApprovalAction({
      approvalId: approval.approval_id,
      kind: decision === 'approved' ? 'approve' : 'reject',
    });
    setApprovalError(null);
    try {
      await resolveAiApproval(token, approval.approval_id, {
        decision,
        reason: reason?.trim() ? reason.trim() : undefined,
      });
      const resolvedApproval: PendingApproval = {
        ...approval,
        decision,
        reason: reason?.trim() ? reason.trim() : null,
      };
      upsertPendingApproval(resolvedApproval);
      autoResumeAttemptedApprovalsRef.current.add(resolvedApproval.approval_id);
      await resumePendingApproval(resolvedApproval);
    } catch (error) {
      if (
        error instanceof AiApiError &&
        (error.status === 404 || error.status === 410)
      ) {
        replacePendingApprovals([]);
      }
      setApprovalError(
        error instanceof Error
          ? error.message
          : '승인 상태를 반영하지 못했습니다.',
      );
    } finally {
      setApprovalAction((current) =>
        current?.approvalId === approval.approval_id ? null : current,
      );
    }
  }, [replacePendingApprovals, resumePendingApproval, token, upsertPendingApproval]);

  const handleAbandonApproval = useCallback(async (approval: PendingApproval) => {
    if (!token) {
      setApprovalError('로그인이 필요합니다.');
      return;
    }
    setApprovalAction({ approvalId: approval.approval_id, kind: 'abandon' });
    setApprovalError(null);
    try {
      await abandonAiApproval(token, approval.approval_id, {});
      upsertPendingApproval({
        ...approval,
        decision: 'cancelled',
        reason: null,
      });
    } catch (error) {
      if (
        error instanceof AiApiError &&
        (error.status === 404 || error.status === 410)
      ) {
        replacePendingApprovals([]);
      }
      setApprovalError(
        error instanceof Error
          ? error.message
          : '요청 취소에 실패했습니다.',
      );
    } finally {
      setApprovalAction((current) =>
        current?.approvalId === approval.approval_id ? null : current,
      );
    }
  }, [replacePendingApprovals, token, upsertPendingApproval]);

  async function refreshHealth() {
    if (!token) {
      return;
    }

    setIsCheckingHealth(true);
    try {
      const nextHealth = await getLlmHealth(token);
      setHealth(nextHealth);
      setHealthError(null);
    } catch (error) {
      setHealth(null);
      setHealthError(
        error instanceof Error
          ? error.message
          : '모델 상태를 확인하지 못했습니다.',
      );
    } finally {
      setIsCheckingHealth(false);
    }
  }

  useEffect(() => {
    autoResumeAttemptedApprovalsRef.current.clear();
  }, [routeConversationId]);

  useEffect(() => {
    if (!token) {
      return;
    }

    let cancelled = false;
    getLlmHealth(token)
      .then((nextHealth) => {
        if (!cancelled) {
          setHealth(nextHealth);
          setHealthError(null);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setHealth(null);
          setHealthError(
            error instanceof Error
              ? error.message
              : '모델 상태를 확인하지 못했습니다.',
          );
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(AI_BACKEND_MODE_STORAGE_KEY, backendMode);
    }
  }, [backendMode]);

  useEffect(() => {
    writePersistedScope(workspaceSlug, allowedAppIds);
  }, [allowedAppIds, workspaceSlug]);

  // Re-read persisted scope when the user switches workspaces — each
  // workspace tracks its own scope choice.
  useEffect(() => {
    setAllowedAppIds(readPersistedScope(workspaceSlug));
  }, [workspaceSlug]);

  // Hydrate turns whenever the URL conversation changes. Clearing `c` (from
  // the sidebar "+ 새 대화" action, say) resets the thread to an empty state;
  // setting it to a new id fetches the persisted turns so the thread renders
  // identically to what the user saw live. Guarded by token so we don't fire
  // a fetch before auth bootstrap completes.
  const [showInsightHint, setShowInsightHint] = useState(false);
  const [pendingDraftSearchCleanup, setPendingDraftSearchCleanup] = useState(false);
  // Clear the "회의 AI 제안에서 시작됨" hint once the composer is empty —
  // this covers both the submit path (handleSubmit clears input) and
  // the user manually clearing the draft. The hint is pinned to the
  // first turn that originated from the deep-link; once that turn is
  // dispatched, the hint is no longer useful.
  useEffect(() => {
    if (!input && showInsightHint) {
      setShowInsightHint(false);
    }
  }, [input, showInsightHint]);
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
    if (authStatus === 'bootstrapping') {
      return;
    }

    // Tail-end of a just-consumed draft: the `routeDraft → null`
    // transition triggered by our own setSearchParams. Skip the reset
    // dance so the draft text we just pushed into the composer is
    // preserved.
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
      setActiveConversationId(routeConversationId);
      setChatError(null);
      setIsLoadingConversation(false);
      return;
    }

    setPendingUserTurnId(null);
    setPendingUserInput('');
    setApprovalAction(null);
    setApprovalError(null);
    setInput('');
    resetChat();

    if (!routeConversationId) {
      setActiveConversationId(null);
      setTurns([]);
      setChatError(null);
      setIsLoadingConversation(false);
      setScopeInfo(null);

      // Consume the meeting-insight deep-link draft exactly once per
      // distinct value. Scheduled AFTER the setInput('') above in the
      // same synchronous block so React batches the two state updates
      // and the composer ends up holding the draft, not an empty
      // string. URL params are cleared in the same tick via replace to
      // avoid history bloat and to prevent a reload from re-consuming.
      if (
        pendingDraft &&
        pendingDraftSourceKey &&
        consumedDraftRef.current !== pendingDraftSourceKey
      ) {
        setInput(pendingDraft);
        setShowInsightHint(true);
        setPendingDraftSearchCleanup(Boolean(routeDraft));
      }
      return;
    }

    setTurns([]);
    setActiveConversationId(null);
    setChatError(null);
    setScopeInfo(null);

    if (!token) {
      setIsLoadingConversation(false);
      return;
    }

    const controller = new AbortController();
    abortHydrateRef.current = controller;
    setIsLoadingConversation(true);
    getConversation(token, routeConversationId)
      .then((detail) => {
        if (controller.signal.aborted) {
          return;
        }
        setTurns(detailToTurns(detail));
        setActiveConversationId(detail.id);
        setChatError(null);
        syncLivePendingApproval(detail.livePendingApproval);
        if (detail.scopeRef === 'meeting' && detail.scopeResourceId) {
          setScopeInfo({
            ref: 'meeting',
            resourceId: detail.scopeResourceId,
            meetingTitle: null,
          });
        } else {
          setScopeInfo(null);
        }
        if (
          locationDraft &&
          locationDraftSourceKey &&
          detail.scopeRef === 'meeting' &&
          detail.turns.length === 0 &&
          consumedDraftRef.current !== locationDraftSourceKey
        ) {
          setInput(locationDraft);
          setShowInsightHint(true);
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setTurns([]);
        setActiveConversationId(null);
        replacePendingApprovals([]);
        setChatError(
          error instanceof Error
            ? error.message
            : '대화 기록을 불러오지 못했습니다.',
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingConversation(false);
        }
      });

    return () => {
      controller.abort();
    };
    // `workspaceSlug` is part of the deps because a same-mounted AIView
    // can see the workspace change via client-side routing (e.g. switching
    // `/w/<old>/ai?c=<id>` → `/w/<new>/ai?c=<id>`). Without it, the old
    // workspace's turns would linger under the new slug.
    // `pendingDraftSourceKey` / `pendingDraft` are part of the deps so a
    // second "챗에서 진행" click (fresh chat still open) re-runs the
    // consume branch with the new draft source. Using a source key rather
    // than the raw draft text keeps the router-state handoff stable even if
    // the cleanup effect removes the query params immediately after mount.
  }, [
    authStatus,
    locationDraft,
    locationDraftSourceKey,
    pendingDraft,
    pendingDraftSourceKey,
    replacePendingApprovals,
    resetChat,
    routeConversationId,
    routeDraft,
    syncLivePendingApproval,
    token,
    workspaceSlug,
  ]);

  // Resolve the meeting title for the scope chip. Runs after hydration
  // sets scopeInfo; degrades silently so a transient fetch failure still
  // leaves the chip visible (just without the specific meeting name).
  useEffect(() => {
    if (!token || !workspaceSlug) return;
    if (
      !scopeInfo ||
      scopeInfo.ref !== 'meeting' ||
      scopeInfo.meetingTitle !== null
    ) {
      return;
    }
    let cancelled = false;
    const resourceId = scopeInfo.resourceId;
    getMeeting(token, workspaceSlug, resourceId)
      .then((meeting) => {
        if (cancelled) return;
        setScopeInfo((prev) =>
          prev &&
          prev.ref === 'meeting' &&
          prev.resourceId === resourceId &&
          prev.meetingTitle === null
            ? { ...prev, meetingTitle: meeting.title }
            : prev,
        );
      })
      .catch(() => {
        // Silent fallback: the chip still renders with the generic label.
      });
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, scopeInfo]);

  useEffect(() => {
    if (!resumableApproval || isSending || !isConversationReady) {
      return;
    }
    if (autoResumeAttemptedApprovalsRef.current.has(resumableApproval.approval_id)) {
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

  useEffect(() => {
    if (!blockingApproval) {
      setApprovalError(null);
    }
  }, [blockingApproval]);

  useEffect(() => {
    if (!pendingDraftSearchCleanup || !routeDraft) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete('draft');
    next.delete('context');
    next.delete('context_id');
    next.delete('insight_id');
    next.delete('insight_kind');
    skipNextHydrationResetRef.current = true;
    setPendingDraftSearchCleanup(false);
    navigate(
      {
        pathname: location.pathname,
        search: next.toString() ? `?${next.toString()}` : '',
      },
      {
        replace: true,
        state:
          pendingDraft && pendingDraftSourceKey
            ? {
                aiDraft: pendingDraft,
                aiDraftSourceKey: pendingDraftSourceKey,
                aiDraftOrigin: 'meeting_insight' as const,
              }
            : location.state,
      },
    );
  }, [
    location.pathname,
    location.state,
    navigate,
    pendingDraft,
    pendingDraftSearchCleanup,
    pendingDraftSourceKey,
    routeDraft,
    searchParams,
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
    skipHydrationConversationIdRef.current = streamedId;
    // Read the live URL rather than the hook's snapshot so a sibling
    // effect that just wrote `?a=<artifact>` in the same render tick
    // doesn't get clobbered when this one writes `?c=<conversation>`.
    const next = new URLSearchParams(
      typeof window === 'undefined' ? '' : window.location.search,
    );
    next.set('c', streamedId);
    setSearchParams(next, { replace: true });
  }, [
    chat.state.conversationId,
    routeConversationId,
    searchParams,
    setSearchParams,
  ]);

  useEffect(() => {
    const status = chat.state.status;
    if (status === 'idle' || status === 'streaming') {
      return;
    }

    if (status === 'done' || status === 'cancelled' || chat.state.streamOpened) {
      setTurns((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: resolveAssistantTurnContent(chat.state.contentBuffer, {
            status,
            errorMessage: chat.state.errorMessage,
            finishReason: chat.state.finishReason,
            hasArtifacts: chat.state.artifacts.length > 0,
          }),
          reasoning: chat.state.reasoningBuffer || undefined,
          reasoningStatus: status,
          finishReason: chat.state.finishReason,
          responseStatus: status === 'done' ? undefined : status,
          provider: chat.state.doneMeta?.provider ?? undefined,
          policy: chat.state.doneMeta?.policy ?? null,
          chosenPool: chat.state.doneMeta?.chosen_pool ?? null,
          decisionReason: chat.state.doneMeta?.decision_reason ?? null,
          forcedLocal: chat.state.doneMeta?.forced_local ?? false,
          piiHits: chat.state.doneMeta?.pii_hits ?? [],
          toolCalls: chat.state.toolCalls,
          pendingApprovals: chat.state.pendingApprovals,
          artifacts: chat.state.artifacts,
        },
      ]);
      setChatError(null);
      setPendingUserTurnId(null);
      setPendingUserInput('');
      // Notify the sidebar that this conversation's `updated_at` just
      // bumped on the server. Follow-up replies keep the same `?c=` so
      // the sidebar's URL-based effect wouldn't refetch otherwise.
      if (typeof window !== 'undefined' && chat.state.conversationId) {
        window.dispatchEvent(
          new CustomEvent(CONVERSATIONS_UPDATED_EVENT, {
            detail: { conversationId: chat.state.conversationId },
          }),
        );
      }
      const shouldKeepPendingApprovals =
        chat.state.finishReason === 'awaiting_approval' ||
        ((status === 'error' || status === 'cancelled') &&
          chat.state.pendingApprovals.length > 0);
      resetChat({
        keepPendingApprovals: shouldKeepPendingApprovals,
      });
    } else {
      setChatError(chat.state.errorMessage ?? 'AI 응답에 실패했습니다.');
      if (pendingUserTurnId) {
        setTurns((current) =>
          current.filter((turn) => turn.id !== pendingUserTurnId),
        );
      }
      if (pendingUserInput && !input) {
        setInput(pendingUserInput);
      }
      setPendingUserTurnId(null);
      setPendingUserInput('');
      resetChat({
        keepPendingApprovals:
          pendingUserTurnId === null && chat.state.pendingApprovals.length > 0,
      });
    }
    // intentionally excluding chat/pendingUserTurnId/pendingUserInput from deps:
    // the hook's state transitions drive the effect; adding unstable refs to
    // deps would retrigger the commit block.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.state.pendingApprovals.length, chat.state.status, resetChat]);

  // Gather every artifact the thread knows about — both persisted (on
  // finalized turns) and live (from the in-flight stream) — so the side
  // panel can resolve its active id regardless of where the artifact lives.
  const allArtifacts = useMemo(() => {
    const entries: ArtifactBuffer[] = [];
    for (const turn of turns) {
      if (!turn.artifacts) continue;
      for (const artifact of turn.artifacts) {
        entries.push({
          id: artifact.id,
          type: artifact.type,
          title: artifact.title ?? null,
          language: artifact.language ?? null,
          content: artifact.content,
          status: artifact.status,
        });
      }
    }
    for (const artifact of chat.state.artifacts) {
      entries.push(artifact);
    }
    return entries;
  }, [chat.state.artifacts, turns]);

  const activeArtifact = useMemo(() => {
    if (!routeArtifactId) {
      return null;
    }
    return allArtifacts.find((entry) => entry.id === routeArtifactId) ?? null;
  }, [allArtifacts, routeArtifactId]);

  // Auto-open the first artifact the current stream produces so the user
  // doesn't have to hunt for the side panel. Fires at most once per new
  // artifact; if the user closes the panel, a subsequent artifact is
  // tracked as the new "latest" and reopens — matching Claude's pattern.
  const lastAutoOpenedArtifactRef = useRef<string | null>(null);
  useEffect(() => {
    const live = chat.state.artifacts;
    if (live.length === 0) {
      return;
    }
    const latest = live[live.length - 1];
    if (
      lastAutoOpenedArtifactRef.current === latest.id ||
      routeArtifactId === latest.id
    ) {
      return;
    }
    lastAutoOpenedArtifactRef.current = latest.id;
    // Read the live URL rather than the hook's `searchParams` snapshot:
    // the `conversation_attached` effect can fire in the same render tick
    // and write `?c=<id>`. Cloning the pre-update snapshot here would
    // drop that value and strand new threads without a persisted id.
    const next = new URLSearchParams(
      typeof window === 'undefined' ? '' : window.location.search,
    );
    next.set('a', latest.id);
    setSearchParams(next, { replace: true });
  }, [chat.state.artifacts, routeArtifactId, searchParams, setSearchParams]);

  const handleOpenArtifact = (artifactId: string) => {
    if (artifactId === routeArtifactId) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set('a', artifactId);
    setSearchParams(next, { replace: false });
  };

  const handleCloseArtifact = () => {
    if (!routeArtifactId) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete('a');
    setSearchParams(next, { replace: false });
  };

  function handleSelectTool(item: NavItem) {
    // Tool invocation semantics: plain AI items land on their /tool/:id page,
    // deep-links (linkAppId, absolutePath) honor their NavItem metadata.
    navigate(resolveToolInvocationHref(item, workspaceSlug, user));
  }

  function handleSubmit() {
    const trimmed = input.trim();
    if (
      !trimmed ||
      !token ||
      isSending ||
      !isConversationReady ||
      blockingApproval !== null
    ) {
      return;
    }

    const userTurn: ChatTurn = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
    };
    const nextTurns = [...turns, userTurn];
    setTurns(nextTurns);
    setInput('');
    setChatError(null);
    setApprovalError(null);
    setPendingUserTurnId(userTurn.id);
    setPendingUserInput(trimmed);
    resetChat();

    // No client-side system message: the API prepends its own AGENT_SYSTEM_PROMPT
    // (apps/api/src/aidoo_api/domains/ai/agent.py) on every turn. Sending one
    // here produced two consecutive system messages, which providers like
    // mlx-lm reject with "System message must be at the beginning" (HTTP 404).
    const messages: AiChatMessage[] = nextTurns.map((turn) => ({
      role: turn.role,
      content: serializeTurnForModel(turn),
    }));

    void chat.send({
      messages,
      backend_mode: backendMode,
      temperature: 0.2,
      stream_reasoning: true,
      // Turn on server-side persistence once the user submits anything. The
      // backend returns a conversation_id via the `conversation_attached`
      // envelope which we capture in chat.state and thread back on follow-ups
      // so the whole thread lands on one Conversation row.
      persist: true,
      conversation_id: activeConversationId ?? undefined,
      // ``undefined`` lets the server fall through to its "all entitled
      // tools" default; a non-null value narrows tool exposure for this turn
      // (the server still intersects with workspace entitlements, so this
      // can never widen access).
      ...(sanitizedAllowedAppIds !== null
        ? { allowed_app_ids: sanitizedAllowedAppIds }
        : {}),
    });
  }

  const composerPlaceholder =
    isLoadingConversation
      ? '대화를 불러오는 중입니다.'
      : !isConversationReady
        ? '이 대화를 열 수 없습니다. 새 대화를 시작하거나 다른 대화를 선택하세요.'
        : blockingApproval
          ? '현재 승인을 해결해야 다음 요청이 가능합니다.'
          : undefined;

  const blockingApprovalAction =
    blockingApproval && approvalAction?.approvalId === blockingApproval.approval_id
      ? approvalAction.kind
      : null;

  const approvalNotice = blockingApproval ? (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
      <div>
        <p className="app-text-body-sm text-app-ink">
          {pendingApproval
            ? '현재 승인을 해결해야 다음 요청이 가능합니다.'
            : '승인 결과를 적용하는 중입니다. 문제가 생기면 이어가기를 다시 시도하세요.'}
        </p>
        <p className="app-text-caption text-app-ink/60">
          {blockingApproval.tool}
          {blockingApproval.resource_preview
            ? ` · ${blockingApproval.resource_preview}`
            : ''}
        </p>
        {approvalError && !pendingApproval ? (
          <p
            role="alert"
            className="app-text-caption mt-1 text-[var(--ui-color-danger)]"
          >
            {approvalError}
          </p>
        ) : null}
      </div>
      {pendingApproval ? (
        <button
          type="button"
          onClick={() => {
            void handleAbandonApproval(pendingApproval);
          }}
          disabled={Boolean(blockingApprovalAction)}
          className="app-text-control rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:border-app-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          {blockingApprovalAction === 'abandon' ? '취소 중...' : '요청 취소'}
        </button>
      ) : resumableApproval ? (
        <button
          type="button"
          onClick={() => {
            void resumePendingApproval(resumableApproval);
          }}
          disabled={Boolean(blockingApprovalAction)}
          className="app-text-control rounded-md bg-app-accent px-3 py-2 text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
        >
          {blockingApprovalAction === 'resume' ? '이어가는 중...' : '이어가기'}
        </button>
      ) : null}
    </div>
  ) : null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mx-auto flex w-full max-w-7xl flex-col gap-8 p-6 lg:p-8"
    >
      <section className="flex min-h-[640px] flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface">
        <ChatTopBar
          title="업무 챗봇"
          backendMode={backendMode}
          onBackendModeChange={setBackendMode}
          health={health}
          healthError={healthError}
          isCheckingHealth={isCheckingHealth}
          onRefreshHealth={refreshHealth}
          canRefresh={Boolean(token)}
          scopeOptions={scopeOptions}
          scopeSelected={sanitizedAllowedAppIds}
          onScopeChange={setAllowedAppIds}
          scopeDisabled={isSending}
        />

        {turns.length === 0 && !isSending ? (
          <EmptyState
            composer={
              <div className="space-y-2">
                {scopeInfo ? (
                  <div className="flex justify-center">
                    <ScopeChip scope={scopeInfo} workspaceSlug={workspaceSlug} />
                  </div>
                ) : showInsightHint ? (
                  <p
                    role="status"
                    className="app-text-caption text-center text-app-ink/60"
                  >
                    회의 AI 제안에서 시작됨
                  </p>
                ) : null}
                {approvalNotice}
                <ChatComposer
                  input={input}
                  onInputChange={setInput}
                  onSubmit={handleSubmit}
                  onAbort={abortChat}
                  isSending={isSending}
                  isStreaming={chat.state.transport === 'stream'}
                  chatError={chatError}
                  isDisabled={isComposerDisabled}
                  onSelectTool={handleSelectTool}
                  toolItems={slashCommandItems}
                  placeholder={composerPlaceholder}
                  autoFocus
                />
              </div>
            }
            greeting={
              isLoadingConversation
                ? '대화를 불러오는 중입니다.'
                : undefined
            }
            subline={
              isLoadingConversation
                ? '잠시만 기다려 주세요.'
                : undefined
            }
          />
        ) : (
          <>
            <ChatThread
              turns={turns}
              activeArtifactId={routeArtifactId}
              onOpenArtifact={handleOpenArtifact}
              liveAssistant={
                isSending
                  ? {
                      content: chat.state.contentBuffer,
                      reasoning: chat.state.reasoningBuffer,
                      status: chat.state.status,
                      artifacts: chat.state.artifacts,
                    }
                  : null
              }
            />
            {visibleToolCalls.map((call) => (
              <ToolCallCard key={call.call_id} call={call} />
            ))}
            <div className="border-t border-app-border bg-app-surface p-4 space-y-2">
              {scopeInfo ? (
                <div className="flex">
                  <ScopeChip scope={scopeInfo} workspaceSlug={workspaceSlug} />
                </div>
              ) : null}
              {approvalNotice}
              <ChatComposer
                input={input}
                onInputChange={setInput}
                onSubmit={handleSubmit}
                onAbort={abortChat}
                isSending={isSending}
                isStreaming={chat.state.transport === 'stream'}
                chatError={chatError}
                isDisabled={isComposerDisabled}
                onSelectTool={handleSelectTool}
                toolItems={slashCommandItems}
                placeholder={composerPlaceholder}
              />
            </div>
          </>
        )}
      </section>
      {pendingApproval ? (
        <ApprovalModal
          key={pendingApproval.approval_id}
          approval={pendingApproval}
          isSubmitting={approvalAction?.approvalId === pendingApproval.approval_id}
          errorMessage={approvalError}
          onResolve={(decision, reason) =>
            handleResolveApproval(pendingApproval, decision, reason)
          }
          onClose={() => handleAbandonApproval(pendingApproval)}
        />
      ) : null}
      <ArtifactPanel artifact={activeArtifact} onClose={handleCloseArtifact} />
    </motion.div>
  );
};

function mergeToolCalls(
  finalized: ToolCallBuffer[],
  live: ToolCallBuffer[],
): ToolCallBuffer[] {
  const merged = new Map<string, ToolCallBuffer>();
  for (const call of [...finalized, ...live]) {
    merged.set(call.call_id, call);
  }
  return Array.from(merged.values());
}

/**
 * Translate a server-side ConversationDetail into the ChatTurn[] shape the
 * thread renderer consumes. Keeps the reload path visually identical to a
 * live stream — reasoning/tool-calls/status fields all round-trip.
 */
function detailToTurns(detail: ConversationDetail): ChatTurn[] {
  return detail.turns.map(apiTurnToChatTurn);
}

/**
 * Rebuild the on-the-wire form of a prior assistant turn for the next LLM
 * request. The bubble's visible text was the short summary; the full document
 * bodies live on ``turn.artifacts``. Serializing only ``turn.content`` would
 * hide the generated document from the model, so revision asks like
 * "두 번째 문단을 고쳐줘" would operate on ghost text. Re-emit each artifact
 * using the exact ``<artifact>`` grammar the server parses so the model sees
 * the same canonical form it produced.
 */
function serializeTurnForModel(turn: ChatTurn): string {
  const artifacts = turn.artifacts ?? [];
  if (artifacts.length === 0) {
    return turn.content;
  }
  const blocks = artifacts.map((artifact) => {
    // The server's artifact tag grammar only understands double-quoted
    // attribute values without entity decoding. Swap embedded `"` for a
    // Unicode right-double-quote so the model sees a readable title on
    // follow-up turns instead of a literal `&quot;` leak. Titles are
    // display metadata, so the glyph shift is invisible in practice.
    const titleAttr = artifact.title
      ? ` title="${artifact.title.replace(/"/g, '\u201d')}"`
      : '';
    // ``type="code"`` artifacts also carry a language attribute so the
    // model sees the full original tag when revisiting in a follow-up.
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

function apiTurnToChatTurn(turn: ApiConversationTurn): ChatTurn {
  return {
    id: turn.id,
    role: turn.role,
    content: turn.content,
    reasoning: turn.reasoning ?? undefined,
    reasoningStatus: (turn.reasoningStatus ?? undefined) as ChatTurn['reasoningStatus'],
    finishReason: (turn.finishReason ?? null) as ChatTurn['finishReason'],
    responseStatus: (turn.responseStatus ?? undefined) as ChatTurn['responseStatus'],
    provider: turn.provider ?? undefined,
    policy: turn.policy ?? null,
    chosenPool: turn.chosenPool ?? null,
    decisionReason: turn.decisionReason ?? null,
    forcedLocal: Boolean(turn.forcedLocal),
    piiHits: turn.piiHits ?? [],
    toolCalls: (turn.toolCalls ?? []) as unknown as ChatTurn['toolCalls'],
    pendingApprovals:
      (turn.pendingApprovals ?? []) as unknown as ChatTurn['pendingApprovals'],
    artifacts: (turn.artifacts ?? []).map((artifact) => ({
      id: artifact.id,
      type: artifact.type,
      title: artifact.title ?? null,
      language: artifact.language ?? null,
      content: artifact.content,
      status: artifact.status === 'open' ? 'open' : 'closed',
    })),
  };
}
