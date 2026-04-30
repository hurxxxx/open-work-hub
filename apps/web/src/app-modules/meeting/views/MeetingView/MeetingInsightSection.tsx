import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';

import { AiApiError } from '@/src/domains/ai/ai-api';
import type { MeetingDetail } from '@/src/domains/meeting/meeting-api';
import {
  draftFollowupSchedule,
  extractActions,
  extractDecisions,
  type MeetingFollowupResult,
  type MeetingInsightItem,
  type MeetingInsightListResult,
} from '@/src/domains/meeting/meeting-insights-api';

import { EmptyRow, Section } from './MeetingSection';

const SUMMARY_NOT_READY_HINT =
  '회의 요약이 아직 없어 AI 제안을 다시 만들 수 없습니다.';
const EXTRACTING_STATUSES = new Set(['extracting_insights', 'generating_doc']);

interface GroupState<T> {
  items: T[];
  loading: boolean;
  error: string | null;
}

const emptyGroup = <T,>(): GroupState<T> => ({
  items: [],
  loading: false,
  error: null,
});

interface MeetingInsightSectionProps {
  meeting: MeetingDetail;
  workspaceSlug: string;
  token: string | null;
  onOpenInChat: (insight: MeetingInsightItem) => void | Promise<void>;
}

function errorMessage(error: unknown): string {
  if (error instanceof AiApiError) {
    if (error.status === 409) {
      return SUMMARY_NOT_READY_HINT;
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'AI 제안을 불러오지 못했습니다.';
}

function attendeeNameMap(meeting: MeetingDetail): Map<string, string> {
  const map = new Map<string, string>();
  for (const attendee of meeting.attendees) {
    map.set(attendee.user_id, attendee.full_name);
  }
  return map;
}

function formatDueDate(value: unknown): string | null {
  if (typeof value !== 'string' || !value) return null;
  return value;
}

function renderSlotList(slots: unknown): string[] {
  if (!Array.isArray(slots)) return [];
  const out: string[] = [];
  for (const raw of slots.slice(0, 3)) {
    if (!raw || typeof raw !== 'object') continue;
    const start = (raw as { start_at?: unknown }).start_at;
    if (typeof start !== 'string') continue;
    const parsed = new Date(start);
    if (Number.isNaN(parsed.valueOf())) continue;
    out.push(
      `${parsed.getMonth() + 1}/${parsed.getDate()} ${String(parsed.getHours()).padStart(2, '0')}:${String(parsed.getMinutes()).padStart(2, '0')}`,
    );
  }
  return out;
}

interface OpenInChatState {
  openingInsightId: string | null;
  onOpen: (insight: MeetingInsightItem) => void;
}

function OpenInChatButton({
  insight,
  state,
}: {
  insight: MeetingInsightItem;
  state: OpenInChatState;
}) {
  const isOpening = state.openingInsightId === insight.id;
  const isOtherOpening =
    state.openingInsightId !== null && state.openingInsightId !== insight.id;
  return (
    <button
      type="button"
      onClick={() => state.onOpen(insight)}
      disabled={isOpening || isOtherOpening}
      aria-busy={isOpening}
      className="app-text-caption inline-flex items-center gap-1 text-app-accent hover:underline disabled:text-app-ink/40 disabled:hover:no-underline"
    >
      {isOpening ? (
        <Loader2 size={12} className="animate-spin" aria-hidden="true" />
      ) : null}
      챗에서 진행
    </button>
  );
}

function ActionCard({
  insight,
  assigneeName,
  openState,
}: {
  insight: MeetingInsightItem;
  assigneeName: string | null;
  openState: OpenInChatState;
}) {
  const payload = insight.payload;
  const title = typeof payload.title === 'string' ? payload.title : '';
  const description =
    typeof payload.description === 'string' ? payload.description : null;
  const dueDate = formatDueDate(payload.proposed_due_date);
  return (
    <li className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3">
      <p className="app-text-body text-app-ink">{title || '(제목 없음)'}</p>
      {description ? (
        <p className="app-text-caption mt-1 whitespace-pre-wrap text-app-ink/70">
          {description}
        </p>
      ) : null}
      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="app-text-caption text-app-ink/50">
          {[assigneeName ? `담당 ${assigneeName}` : null, dueDate ? `기한 ${dueDate}` : null]
            .filter(Boolean)
            .join(' · ') || '추가 정보 없음'}
        </p>
        <OpenInChatButton insight={insight} state={openState} />
      </div>
    </li>
  );
}

function DecisionCard({
  insight,
  openState,
}: {
  insight: MeetingInsightItem;
  openState: OpenInChatState;
}) {
  const payload = insight.payload;
  const statement = typeof payload.statement === 'string' ? payload.statement : '';
  const rationale = typeof payload.rationale === 'string' ? payload.rationale : null;
  return (
    <li className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3">
      <p className="app-text-body text-app-ink">{statement || '(내용 없음)'}</p>
      {rationale ? (
        <p className="app-text-caption mt-1 whitespace-pre-wrap text-app-ink/70">
          {rationale}
        </p>
      ) : null}
      <div className="mt-2 flex justify-end">
        <OpenInChatButton insight={insight} state={openState} />
      </div>
    </li>
  );
}

function FollowupCard({
  insight,
  followupContext,
  openState,
}: {
  insight: MeetingInsightItem;
  followupContext: MeetingFollowupResult | null;
  openState: OpenInChatState;
}) {
  const payload = insight.payload;
  const title =
    typeof payload.proposed_title === 'string' ? payload.proposed_title : '';
  const duration =
    typeof payload.duration_minutes === 'number' ? payload.duration_minutes : null;
  const slots = renderSlotList(payload.proposed_slots);
  const attendeeCount = Array.isArray(payload.attendee_user_ids)
    ? payload.attendee_user_ids.length
    : followupContext?.attendee_user_ids.length ?? 0;
  const busyBlocks = followupContext?.availability?.items
    ? followupContext.availability.items.reduce(
        (sum, item) => sum + item.blocks.length,
        0,
      )
    : null;
  const summaryParts = [
    `제안 슬롯 ${slots.length}개`,
    `참석자 ${attendeeCount}명`,
    busyBlocks !== null ? `겹치는 일정 ${busyBlocks}건` : null,
  ].filter(Boolean);
  return (
    <li className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3">
      <p className="app-text-body text-app-ink">{title || '(제목 없음)'}</p>
      {duration !== null ? (
        <p className="app-text-caption mt-1 text-app-ink/70">
          예상 소요 {duration}분
        </p>
      ) : null}
      {slots.length > 0 ? (
        <p className="app-text-caption mt-1 text-app-ink/70">{slots.join(' · ')}</p>
      ) : null}
      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="app-text-caption text-app-ink/50">
          {summaryParts.join(' · ') || '요약 정보 없음'}
        </p>
        <OpenInChatButton insight={insight} state={openState} />
      </div>
    </li>
  );
}

export function MeetingInsightSection({
  meeting,
  workspaceSlug: _workspaceSlug,
  token,
  onOpenInChat,
}: MeetingInsightSectionProps) {
  const [actionsState, setActionsState] = useState<GroupState<MeetingInsightItem>>(
    emptyGroup,
  );
  const [decisionsState, setDecisionsState] = useState<GroupState<MeetingInsightItem>>(
    emptyGroup,
  );
  const [followupState, setFollowupState] = useState<
    GroupState<MeetingInsightItem> & { context: MeetingFollowupResult | null }
  >({ items: [], loading: false, error: null, context: null });
  const [refreshing, setRefreshing] = useState(false);
  const [openingInsightId, setOpeningInsightId] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const latestRequestTokenRef = useRef(0);

  const handleOpenInChat = useCallback(
    (insight: MeetingInsightItem) => {
      if (openingInsightId !== null) return;
      setOpeningInsightId(insight.id);
      setOpenError(null);
      // Wrap with Promise.resolve so callers returning void (e.g. test mocks)
      // still go through the same loading-state teardown path.
      void Promise.resolve(onOpenInChat(insight))
        .catch((err: unknown) => {
          setOpenError(
            err instanceof Error ? err.message : 'AI 대화를 시작할 수 없습니다.',
          );
        })
        .finally(() => {
          setOpeningInsightId(null);
        });
    },
    [onOpenInChat, openingInsightId],
  );

  const openState: OpenInChatState = useMemo(
    () => ({ openingInsightId, onOpen: handleOpenInChat }),
    [openingInsightId, handleOpenInChat],
  );

  // Re-fetch when the meeting changes or any recording transitions
  // (e.g. extraction finishes) so new drafts surface without forcing
  // the user to reload. The signature captures both recording count
  // and per-recording status.
  const recordingSignature = useMemo(
    () =>
      meeting.recordings
        .map((recording) => `${recording.id}:${recording.transcription_status}`)
        .join('|'),
    [meeting.recordings],
  );

  const hasDoneRecording = meeting.recordings.some(
    (recording) => recording.transcription_status === 'done',
  );
  const isExtracting = meeting.recordings.some((recording) =>
    EXTRACTING_STATUSES.has(recording.transcription_status),
  );

  useEffect(() => {
    if (!token) return;
    const requestToken = ++latestRequestTokenRef.current;
    setActionsState((prev) => ({ ...prev, loading: true, error: null }));
    setDecisionsState((prev) => ({ ...prev, loading: true, error: null }));
    setFollowupState((prev) => ({ ...prev, loading: true, error: null }));

    // Auto-refetch is also triggered when a recording transitions
    // (e.g. extracting_insights → done). A transient failure in one
    // tool must not erase the other groups' visible cards — hence the
    // `prev.items` preservation on rejection. Only `fulfilled` replaces
    // the items snapshot; `rejected` leaves the existing list alone
    // and surfaces the error inline.
    void Promise.allSettled([
      extractActions(token, meeting.id),
      extractDecisions(token, meeting.id),
      draftFollowupSchedule(token, meeting.id),
    ]).then(([actions, decisions, followup]) => {
      if (latestRequestTokenRef.current !== requestToken) return;
      setActionsState((prev) => ({
        items:
          actions.status === 'fulfilled'
            ? (actions.value as MeetingInsightListResult).items
            : prev.items,
        loading: false,
        error:
          actions.status === 'rejected' ? errorMessage(actions.reason) : null,
      }));
      setDecisionsState((prev) => ({
        items:
          decisions.status === 'fulfilled'
            ? (decisions.value as MeetingInsightListResult).items
            : prev.items,
        loading: false,
        error:
          decisions.status === 'rejected' ? errorMessage(decisions.reason) : null,
      }));
      setFollowupState((prev) => {
        if (followup.status === 'fulfilled') {
          const value = followup.value as MeetingFollowupResult;
          return {
            items: value.items,
            loading: false,
            error: null,
            context: value,
          };
        }
        return {
          items: prev.items,
          loading: false,
          error: errorMessage(followup.reason),
          context: prev.context,
        };
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, meeting.id, recordingSignature]);

  const refreshAll = useCallback(async () => {
    if (!token || refreshing) return;
    setRefreshing(true);
    const requestToken = ++latestRequestTokenRef.current;
    setActionsState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const value = await extractActions(token, meeting.id, { refresh: true });
      if (latestRequestTokenRef.current === requestToken) {
        setActionsState({ items: value.items, loading: false, error: null });
      }
    } catch (error) {
      if (latestRequestTokenRef.current === requestToken) {
        setActionsState((prev) => ({
          ...prev,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }
    setDecisionsState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const value = await extractDecisions(token, meeting.id, { refresh: true });
      if (latestRequestTokenRef.current === requestToken) {
        setDecisionsState({ items: value.items, loading: false, error: null });
      }
    } catch (error) {
      if (latestRequestTokenRef.current === requestToken) {
        setDecisionsState((prev) => ({
          ...prev,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }
    setFollowupState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const value = await draftFollowupSchedule(token, meeting.id, {
        refresh: true,
      });
      if (latestRequestTokenRef.current === requestToken) {
        setFollowupState({
          items: value.items,
          loading: false,
          error: null,
          context: value,
        });
      }
    } catch (error) {
      if (latestRequestTokenRef.current === requestToken) {
        setFollowupState((prev) => ({
          ...prev,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }
    if (latestRequestTokenRef.current === requestToken) {
      setRefreshing(false);
    }
  }, [token, meeting.id, refreshing]);

  const attendeeNames = useMemo(() => attendeeNameMap(meeting), [meeting]);
  const totalCount =
    actionsState.items.length +
    decisionsState.items.length +
    followupState.items.length;
  const hasAnyError = Boolean(
    actionsState.error || decisionsState.error || followupState.error,
  );
  const allEmpty = totalCount === 0 && !hasAnyError;
  const refreshDisabled = !hasDoneRecording || refreshing;

  const refreshButton = (
    <button
      type="button"
      onClick={() => void refreshAll()}
      disabled={refreshDisabled}
      className="app-text-caption inline-flex items-center gap-1 text-app-accent hover:underline disabled:text-app-ink/40 disabled:hover:no-underline"
    >
      {refreshing ? <Loader2 size={12} className="animate-spin" /> : null}
      재추출
    </button>
  );

  return (
    <Section
      icon={<Sparkles size={14} />}
      title="AI 제안"
      count={totalCount}
      headerAction={refreshButton}
    >
      {isExtracting ? (
        <p className="app-text-caption mb-2 text-app-ink/60">
          AI 제안을 생성 중입니다.
        </p>
      ) : null}

      {openError ? (
        <p
          role="alert"
          className="app-text-caption mb-2 text-[var(--ui-color-danger)]"
        >
          {openError}
        </p>
      ) : null}

      {allEmpty ? (
        isExtracting ? null : (
          <EmptyRow text="이 회의에서 발견된 AI 제안이 없습니다." />
        )
      ) : (
        <div className="space-y-4">
          {actionsState.items.length > 0 || actionsState.error ? (
            <div>
              <p className="app-text-overline mb-1 text-app-ink/60">액션 아이템</p>
              {actionsState.error ? (
                <p className="app-text-caption mb-1 text-[var(--ui-color-danger)]">
                  {actionsState.error}
                </p>
              ) : null}
              <ul className="space-y-2">
                {actionsState.items.map((insight) => {
                  const assigneeId =
                    typeof insight.payload.proposed_assignee_user_id === 'string'
                      ? insight.payload.proposed_assignee_user_id
                      : null;
                  const assigneeName = assigneeId
                    ? attendeeNames.get(assigneeId) ?? null
                    : null;
                  return (
                    <ActionCard
                      key={insight.id}
                      insight={insight}
                      assigneeName={assigneeName}
                      openState={openState}
                    />
                  );
                })}
              </ul>
            </div>
          ) : null}

          {decisionsState.items.length > 0 || decisionsState.error ? (
            <div>
              <p className="app-text-overline mb-1 text-app-ink/60">결정사항</p>
              {decisionsState.error ? (
                <p className="app-text-caption mb-1 text-[var(--ui-color-danger)]">
                  {decisionsState.error}
                </p>
              ) : null}
              <ul className="space-y-2">
                {decisionsState.items.map((insight) => (
                  <DecisionCard
                    key={insight.id}
                    insight={insight}
                    openState={openState}
                  />
                ))}
              </ul>
            </div>
          ) : null}

          {followupState.items.length > 0 || followupState.error ? (
            <div>
              <p className="app-text-overline mb-1 text-app-ink/60">후속 회의</p>
              {followupState.error ? (
                <p className="app-text-caption mb-1 text-[var(--ui-color-danger)]">
                  {followupState.error}
                </p>
              ) : null}
              <ul className="space-y-2">
                {followupState.items.map((insight) => (
                  <FollowupCard
                    key={insight.id}
                    insight={insight}
                    followupContext={followupState.context}
                    openState={openState}
                  />
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </Section>
  );
}
