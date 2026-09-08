import type { TFunction } from 'i18next';
import { Loader2, Sparkles } from 'lucide-react';
import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import type { MeetingDetail } from '../../api/meeting-api';
import {
  draftFollowupSchedule,
  extractActions,
  extractDecisions,
  type MeetingFollowupResult,
  type MeetingInsightItem,
} from '../../api/meeting-insights-api';

import { EmptyRow, Section } from './MeetingSection';
import {
  attendeeNameMap,
  buildRecordingSignature,
  formatDueDate,
  hasDoneRecording,
  INITIAL_MEETING_INSIGHTS_STATE,
  isExtractingRecording,
  meetingInsightsReducer,
  renderSlotList,
  type FollowupGroupState,
  type InsightListState,
} from './meeting-insight-section-model';

interface MeetingInsightSectionProps {
  meeting: MeetingDetail;

  token: string | null;
  timeZone: string;
  onOpenInChat: (insight: MeetingInsightItem) => void | Promise<void>;
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
    <li className="rounded-md border border-app-border bg-app-surface-sidebar p-3">
      <p className="app-text-body text-app-ink">
        {title || t('meeting.insights.noTitle')}
      </p>
      {description ? (
        <p className="app-text-caption mt-1 whitespace-pre-wrap text-app-ink/70">
          {description}
        </p>
      ) : null}
      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="app-text-caption text-app-ink/50">
          {[
            assigneeName
              ? t('meeting.insights.assignedTo', { name: assigneeName })
              : null,
            dueDate ? t('meeting.insights.dueDate', { date: dueDate }) : null,
          ]
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
  const statement =
    typeof payload.statement === 'string' ? payload.statement : '';
  const rationale =
    typeof payload.rationale === 'string' ? payload.rationale : null;
  return (
    <li className="rounded-md border border-app-border bg-app-surface-sidebar p-3">
      <p className="app-text-body text-app-ink">
        {statement || t('meeting.insights.noContent')}
      </p>
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
    typeof payload.duration_minutes === 'number'
      ? payload.duration_minutes
      : null;
  const slots = renderSlotList(payload.proposed_slots, timeZone, i18n.language);
  const attendeeCount = Array.isArray(payload.attendee_user_ids)
    ? payload.attendee_user_ids.length
    : (followupContext?.attendee_user_ids.length ?? 0);
  const busyBlocks = followupContext?.availability?.items
    ? followupContext.availability.items.reduce(
        (sum, item) => sum + item.blocks.length,
        0,
      )
    : null;
  const summaryParts = [
    t('meeting.insights.slotCount', { count: slots.length }),
    t('meeting.insights.attendeeCount', { count: attendeeCount }),
    busyBlocks !== null
      ? t('meeting.insights.busyBlockCount', { count: busyBlocks })
      : null,
  ].filter(Boolean);
  return (
    <li className="rounded-md border border-app-border bg-app-surface-sidebar p-3">
      <p className="app-text-body text-app-ink">
        {title || t('meeting.insights.noTitle')}
      </p>
      {duration !== null ? (
        <p className="app-text-caption mt-1 text-app-ink/70">
          {t('meeting.insights.durationMinutes', { count: duration })}
        </p>
      ) : null}
      {slots.length > 0 ? (
        <p className="app-text-caption mt-1 text-app-ink/70">
          {slots.join(' · ')}
        </p>
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

interface InsightGroupsProps {
  actionsState: InsightListState;
  decisionsState: InsightListState;
  followupState: FollowupGroupState;
  attendeeNames: Map<string, string>;
  openState: OpenInChatState;
  timeZone: string;
  t: TFunction;
}

function InsightGroups({
  actionsState,
  decisionsState,
  followupState,
  attendeeNames,
  openState,
  timeZone,
  t,
}: InsightGroupsProps) {
  return (
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
                ? (attendeeNames.get(assigneeId) ?? null)
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
  );
}

export function MeetingInsightSection({
  meeting,
  token,
  timeZone,
  onOpenInChat,
}: MeetingInsightSectionProps) {
  const { t } = useTranslation('apps');
  const [state, dispatch] = useReducer(
    meetingInsightsReducer,
    INITIAL_MEETING_INSIGHTS_STATE,
  );
  const latestRequestTokenRef = useRef(0);
  const {
    actions: actionsState,
    decisions: decisionsState,
    followup: followupState,
    refreshing,
    openingInsightId,
    openError,
  } = state;

  const handleOpenInChat = useCallback(
    (insight: MeetingInsightItem) => {
      if (openingInsightId !== null) return;
      dispatch({ type: 'openStarted', insightId: insight.id });
      // Wrap with Promise.resolve so callers returning void (e.g. test mocks)
      // still go through the same loading-state teardown path.
      void Promise.resolve(onOpenInChat(insight))
        .catch((err: unknown) => {
          dispatch({
            type: 'openFailed',
            message:
              err instanceof Error
                ? err.message
                : t('meeting.insights.openFailed'),
          });
        })
        .finally(() => {
          dispatch({ type: 'openFinished' });
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
    () => buildRecordingSignature(meeting.recordings),
    [meeting.recordings],
  );
  const recordingHasDone = hasDoneRecording(meeting.recordings);
  const isExtracting = isExtractingRecording(meeting.recordings);

  useEffect(() => {
    if (!token) return;
    const requestToken = ++latestRequestTokenRef.current;
    dispatch({ type: 'loadStarted' });

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
      dispatch({
        type: 'loadSettled',
        actions,
        decisions,
        followup,
        refreshing: false,
        t,
      });
    });
  }, [token, meeting.id, recordingSignature, t]);

  const refreshAll = useCallback(async () => {
    if (!token || refreshing) return;
    const requestToken = ++latestRequestTokenRef.current;
    dispatch({ type: 'refreshStarted' });
    const [actions, decisions, followup] = await Promise.allSettled([
      extractActions(token, meeting.id, { refresh: true }),
      extractDecisions(token, meeting.id, { refresh: true }),
      draftFollowupSchedule(token, meeting.id, { refresh: true }),
    ]);
    if (latestRequestTokenRef.current === requestToken) {
      dispatch({
        type: 'loadSettled',
        actions,
        decisions,
        followup,
        refreshing: false,
        t,
      });
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
  const refreshDisabled = !recordingHasDone || refreshing;

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
        <InsightGroups
          actionsState={actionsState}
          decisionsState={decisionsState}
          followupState={followupState}
          attendeeNames={attendeeNames}
          openState={openState}
          timeZone={timeZone}
          t={t}
        />
      )}
    </Section>
  );
}
