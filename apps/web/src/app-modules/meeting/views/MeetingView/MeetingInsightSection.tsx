import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import { AiApiError } from '@/src/app-modules/ai/public-api';
import type { MeetingDetail } from '../../api/meeting-api';
import {
  draftFollowupSchedule,
  extractActions,
  extractDecisions,
  type MeetingFollowupResult,
  type MeetingInsightItem,
  type MeetingInsightListResult,
} from '../../api/meeting-insights-api';
import { formatDateTime } from '@/src/platform/time/time-utils';

import { EmptyRow, Section } from './MeetingSection';

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
  timeZone: string;
  onOpenInChat: (insight: MeetingInsightItem) => void | Promise<void>;
}

function errorMessage(error: unknown, t: TFunction): string {
  if (error instanceof AiApiError) {
    if (error.status === 409) {
      return t('meeting.insights.summaryNotReady');
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return t('meeting.insights.loadFailed');
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

function renderSlotList(slots: unknown, timeZone: string, locale: string): string[] {
  if (!Array.isArray(slots)) return [];
  const out: string[] = [];
  for (const raw of slots.slice(0, 3)) {
    if (!raw || typeof raw !== 'object') continue;
    const start = (raw as { start_at?: unknown }).start_at;
    if (typeof start !== 'string') continue;
    const formatted = formatDateTime(start, {
      fallback: '',
      hour: '2-digit',
      minute: '2-digit',
      month: 'numeric',
      day: 'numeric',
      locale,
      timeZone,
    });
    if (formatted) out.push(formatted);
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
  const { t } = useTranslation('apps');
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
      {t('meeting.insights.openInChat')}
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
  const { t } = useTranslation('apps');
  const payload = insight.payload;
  const title = typeof payload.title === 'string' ? payload.title : '';
  const description =
    typeof payload.description === 'string' ? payload.description : null;
  const dueDate = formatDueDate(payload.proposed_due_date);
  return (
    <li className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3">
      <p className="app-text-body text-app-ink">{title || t('meeting.insights.noTitle')}</p>
      {description ? (
        <p className="app-text-caption mt-1 whitespace-pre-wrap text-app-ink/70">
          {description}
        </p>
      ) : null}
      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="app-text-caption text-app-ink/50">
          {[assigneeName ? t('meeting.insights.assignedTo', { name: assigneeName }) : null, dueDate ? t('meeting.insights.dueDate', { date: dueDate }) : null]
            .filter(Boolean)
            .join(' · ') || t('meeting.insights.noDetails')}
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
  const { t } = useTranslation('apps');
  const payload = insight.payload;
  const statement = typeof payload.statement === 'string' ? payload.statement : '';
  const rationale = typeof payload.rationale === 'string' ? payload.rationale : null;
  return (
    <li className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3">
      <p className="app-text-body text-app-ink">{statement || t('meeting.insights.noContent')}</p>
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
  timeZone,
}: {
  insight: MeetingInsightItem;
  followupContext: MeetingFollowupResult | null;
  openState: OpenInChatState;
  timeZone: string;
}) {
  const { t, i18n } = useTranslation('apps');
  const payload = insight.payload;
  const title =
    typeof payload.proposed_title === 'string' ? payload.proposed_title : '';
  const duration =
    typeof payload.duration_minutes === 'number' ? payload.duration_minutes : null;
  const slots = renderSlotList(payload.proposed_slots, timeZone, i18n.language);
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
    t('meeting.insights.slotCount', { count: slots.length }),
    t('meeting.insights.attendeeCount', { count: attendeeCount }),
    busyBlocks !== null ? t('meeting.insights.busyBlockCount', { count: busyBlocks }) : null,
  ].filter(Boolean);
  return (
    <li className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-3">
      <p className="app-text-body text-app-ink">{title || t('meeting.insights.noTitle')}</p>
      {duration !== null ? (
        <p className="app-text-caption mt-1 text-app-ink/70">
          {t('meeting.insights.durationMinutes', { count: duration })}
        </p>
      ) : null}
      {slots.length > 0 ? (
        <p className="app-text-caption mt-1 text-app-ink/70">{slots.join(' · ')}</p>
      ) : null}
      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="app-text-caption text-app-ink/50">
          {summaryParts.join(' · ') || t('meeting.insights.noSummary')}
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
  timeZone,
  onOpenInChat,
}: MeetingInsightSectionProps) {
  const { t } = useTranslation('apps');
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
            err instanceof Error ? err.message : t('meeting.insights.openFailed'),
          );
        })
        .finally(() => {
          setOpeningInsightId(null);
        });
    },
    [onOpenInChat, openingInsightId, t],
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
          actions.status === 'rejected' ? errorMessage(actions.reason, t) : null,
      }));
      setDecisionsState((prev) => ({
        items:
          decisions.status === 'fulfilled'
            ? (decisions.value as MeetingInsightListResult).items
            : prev.items,
        loading: false,
        error:
          decisions.status === 'rejected' ? errorMessage(decisions.reason, t) : null,
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
          error: errorMessage(followup.reason, t),
          context: prev.context,
        };
      });
    });
  }, [token, meeting.id, recordingSignature, t]);

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
          error: errorMessage(error, t),
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
          error: errorMessage(error, t),
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
          error: errorMessage(error, t),
        }));
      }
    }
    if (latestRequestTokenRef.current === requestToken) {
      setRefreshing(false);
    }
  }, [token, meeting.id, refreshing, t]);

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
      {t('meeting.insights.refresh')}
    </button>
  );

  return (
    <Section
      icon={<Sparkles size={14} />}
      title={t('meeting.insights.title')}
      count={totalCount}
      headerAction={refreshButton}
    >
      {isExtracting ? (
        <p className="app-text-caption mb-2 text-app-ink/60">
          {t('meeting.insights.extracting')}
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
          <EmptyRow text={t('meeting.insights.empty')} />
        )
      ) : (
        <div className="space-y-4">
          {actionsState.items.length > 0 || actionsState.error ? (
            <div>
              <p className="app-text-overline mb-1 text-app-ink/60">
                {t('meeting.insights.actionItems')}
              </p>
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
              <p className="app-text-overline mb-1 text-app-ink/60">
                {t('meeting.insights.decisions')}
              </p>
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
              <p className="app-text-overline mb-1 text-app-ink/60">
                {t('meeting.insights.followupMeetings')}
              </p>
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
                    timeZone={timeZone}
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
