import type { TFunction } from 'i18next';

import { AiApiError } from '@/src/app-modules/ai/public-api';
import type { MeetingDetail } from '../../api/meeting-api';
import type {
  MeetingFollowupResult,
  MeetingInsightItem,
  MeetingInsightListResult,
} from '../../api/meeting-insights-api';
import { formatDateTime } from '@/src/platform/time/time-utils';

export const EXTRACTING_STATUSES = new Set([
  'extracting_insights',
  'generating_doc',
]);

export interface GroupState<T> {
  items: T[];
  loading: boolean;
  error: string | null;
}

export type InsightListState = GroupState<MeetingInsightItem>;

export type FollowupGroupState = InsightListState & {
  context: MeetingFollowupResult | null;
};

export interface MeetingInsightsState {
  actions: InsightListState;
  decisions: InsightListState;
  followup: FollowupGroupState;
  refreshing: boolean;
  openingInsightId: string | null;
  openError: string | null;
}

export type InsightSettledPayload = {
  actions: PromiseSettledResult<MeetingInsightListResult>;
  decisions: PromiseSettledResult<MeetingInsightListResult>;
  followup: PromiseSettledResult<MeetingFollowupResult>;
  t: TFunction;
};

export type MeetingInsightsAction =
  | { type: 'loadStarted' }
  | ({ type: 'loadSettled'; refreshing: boolean } & InsightSettledPayload)
  | { type: 'refreshStarted' }
  | { type: 'openStarted'; insightId: string }
  | { type: 'openFailed'; message: string }
  | { type: 'openFinished' };

const emptyGroup = <T>(): GroupState<T> => ({
  items: [],
  loading: false,
  error: null,
});

export const INITIAL_MEETING_INSIGHTS_STATE: MeetingInsightsState = {
  actions: emptyGroup(),
  decisions: emptyGroup(),
  followup: { ...emptyGroup<MeetingInsightItem>(), context: null },
  refreshing: false,
  openingInsightId: null,
  openError: null,
};

export function meetingInsightsReducer(
  state: MeetingInsightsState,
  action: MeetingInsightsAction,
): MeetingInsightsState {
  switch (action.type) {
    case 'loadStarted':
      return {
        ...state,
        ...markGroupsLoading(state),
      };
    case 'refreshStarted':
      return {
        ...state,
        ...markGroupsLoading(state),
        refreshing: true,
      };
    case 'loadSettled':
      return {
        ...state,
        actions: listStateFromResult(state.actions, action.actions, action.t),
        decisions: listStateFromResult(
          state.decisions,
          action.decisions,
          action.t,
        ),
        followup: followupStateFromResult(
          state.followup,
          action.followup,
          action.t,
        ),
        refreshing: action.refreshing,
      };
    case 'openStarted':
      return {
        ...state,
        openingInsightId: action.insightId,
        openError: null,
      };
    case 'openFailed':
      return {
        ...state,
        openError: action.message,
      };
    case 'openFinished':
      return {
        ...state,
        openingInsightId: null,
      };
    default:
      return state;
  }
}

export function errorMessage(error: unknown, t: TFunction): string {
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

export function attendeeNameMap(meeting: MeetingDetail): Map<string, string> {
  const map = new Map<string, string>();
  for (const attendee of meeting.attendees) {
    map.set(attendee.user_id, attendee.full_name);
  }
  return map;
}

export function formatDueDate(value: unknown): string | null {
  if (typeof value !== 'string' || !value) return null;
  return value;
}

export function renderSlotList(
  slots: unknown,
  timeZone: string,
  locale: string,
): string[] {
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

export function buildRecordingSignature(
  recordings: MeetingDetail['recordings'],
): string {
  return recordings
    .map((recording) => `${recording.id}:${recording.transcription_status}`)
    .join('|');
}

export function hasDoneRecording(
  recordings: MeetingDetail['recordings'],
): boolean {
  return recordings.some(
    (recording) => recording.transcription_status === 'done',
  );
}

export function isExtractingRecording(
  recordings: MeetingDetail['recordings'],
): boolean {
  return recordings.some((recording) =>
    EXTRACTING_STATUSES.has(recording.transcription_status),
  );
}

function listStateFromResult(
  previous: InsightListState,
  result: PromiseSettledResult<MeetingInsightListResult>,
  t: TFunction,
): InsightListState {
  if (result.status === 'fulfilled') {
    return {
      items: result.value.items,
      loading: false,
      error: null,
    };
  }
  return {
    items: previous.items,
    loading: false,
    error: errorMessage(result.reason, t),
  };
}

function followupStateFromResult(
  previous: FollowupGroupState,
  result: PromiseSettledResult<MeetingFollowupResult>,
  t: TFunction,
): FollowupGroupState {
  if (result.status === 'fulfilled') {
    return {
      items: result.value.items,
      loading: false,
      error: null,
      context: result.value,
    };
  }
  return {
    items: previous.items,
    loading: false,
    error: errorMessage(result.reason, t),
    context: previous.context,
  };
}

function markGroupsLoading(
  state: MeetingInsightsState,
): Pick<MeetingInsightsState, 'actions' | 'decisions' | 'followup'> {
  return {
    actions: { ...state.actions, loading: true, error: null },
    decisions: { ...state.decisions, loading: true, error: null },
    followup: { ...state.followup, loading: true, error: null },
  };
}
