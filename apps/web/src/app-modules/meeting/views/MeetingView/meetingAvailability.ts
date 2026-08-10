import { useEffect, useMemo, useReducer } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  getMeetingAvailability,
  parseServerDateTime,
  type MeetingAvailabilityBlock,
  type MeetingAvailabilityItem,
  type MeetingUser,
} from '../../api/meeting-api';
import {
  DEFAULT_TIME_ZONE,
  formatDateOnly,
  formatDateTime,
} from '@/src/platform/time/time-utils';

interface AvailabilityBlockLabels {
  busy: string;
  schedule: string;
}

const DEFAULT_AVAILABILITY_BLOCK_LABELS: AvailabilityBlockLabels = {
  busy: 'Busy',
  schedule: 'Schedule',
};

export const AVAILABILITY_NAME_COLUMN_PX = 208;

export interface AvailabilityConflictItem {
  userId: string;
  fullName: string;
  block: MeetingAvailabilityBlock;
  label: string;
}

export type MeetingAvailabilityPanelDisplayState =
  | { type: 'invalid-window' }
  | { type: 'no-attendees' }
  | { type: 'loading' }
  | { type: 'error'; message: string }
  | { type: 'no-conflicts' }
  | { type: 'conflicts'; count: number };

export interface MeetingAvailabilityPanelQueryProjection {
  attendeeIds: string[];
  canQuery: boolean;
  rangeEnd: Date | null;
  rangeStart: Date | null;
  validMeetingWindow: boolean;
}

interface MeetingAvailabilityQueryState {
  items: MeetingAvailabilityItem[];
  loading: boolean;
  error: string | null;
}

type MeetingAvailabilityQueryAction =
  | { type: 'idle' }
  | { type: 'loading' }
  | { type: 'loaded'; items: MeetingAvailabilityItem[] }
  | { type: 'failed'; message: string };

const INITIAL_MEETING_AVAILABILITY_QUERY_STATE: MeetingAvailabilityQueryState =
  {
    items: [],
    loading: false,
    error: null,
  };

function meetingAvailabilityQueryReducer(
  state: MeetingAvailabilityQueryState,
  action: MeetingAvailabilityQueryAction,
): MeetingAvailabilityQueryState {
  switch (action.type) {
    case 'idle':
      if (!state.loading && state.error === null && state.items.length === 0) {
        return state;
      }
      return INITIAL_MEETING_AVAILABILITY_QUERY_STATE;
    case 'loading':
      if (state.loading && state.error === null) {
        return state;
      }
      return {
        ...state,
        loading: true,
        error: null,
      };
    case 'loaded':
      return {
        items: action.items,
        loading: false,
        error: null,
      };
    case 'failed':
      return {
        items: [],
        loading: false,
        error: action.message,
      };
    default:
      return state;
  }
}

export function startOfAvailabilityWeek(date: Date): Date {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  start.setDate(start.getDate() - start.getDay());
  start.setHours(0, 0, 0, 0);
  return start;
}

export function addLocalDays(date: Date, days: number): Date {
  const next = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  next.setDate(next.getDate() + days);
  return next;
}

export function isValidMeetingAvailabilityWindow(
  start: Date | null,
  end: Date | null,
): boolean {
  return Boolean(start && end && end > start);
}

export function projectMeetingAvailabilityAttendeeIds(
  attendeeUsers: Pick<MeetingUser, 'id'>[],
): string[] {
  return Array.from(
    new Set(attendeeUsers.map((user) => user.id).filter(Boolean)),
  );
}

export function deriveMeetingAvailabilityQueryRange(
  meetingStart: Date | null,
): {
  rangeEnd: Date | null;
  rangeStart: Date | null;
} {
  const rangeStart = meetingStart
    ? startOfAvailabilityWeek(meetingStart)
    : null;
  return {
    rangeEnd: rangeStart ? addLocalDays(rangeStart, 7) : null,
    rangeStart,
  };
}

export function projectMeetingAvailabilityPanelQuery(options: {
  attendeeUsers: Pick<MeetingUser, 'id'>[];
  meetingEnd: Date | null;
  meetingStart: Date | null;
}): MeetingAvailabilityPanelQueryProjection {
  const attendeeIds = projectMeetingAvailabilityAttendeeIds(
    options.attendeeUsers,
  );
  const { rangeEnd, rangeStart } = deriveMeetingAvailabilityQueryRange(
    options.meetingStart,
  );
  const validMeetingWindow = isValidMeetingAvailabilityWindow(
    options.meetingStart,
    options.meetingEnd,
  );
  return {
    attendeeIds,
    canQuery: validMeetingWindow && attendeeIds.length > 0,
    rangeEnd,
    rangeStart,
    validMeetingWindow,
  };
}

export function selectMeetingAvailabilityPanelDisplayState(options: {
  attendeeCount: number;
  conflictCount: number;
  error: string | null;
  loading: boolean;
  validMeetingWindow: boolean;
}): MeetingAvailabilityPanelDisplayState {
  if (!options.validMeetingWindow) {
    return { type: 'invalid-window' };
  }
  if (options.attendeeCount === 0) {
    return { type: 'no-attendees' };
  }
  if (options.loading) {
    return { type: 'loading' };
  }
  if (options.error) {
    return { type: 'error', message: options.error };
  }
  if (options.conflictCount === 0) {
    return { type: 'no-conflicts' };
  }
  return { type: 'conflicts', count: options.conflictCount };
}

export function formatAvailabilityWeekLabel(
  weekStart: Date,
  timeZone = DEFAULT_TIME_ZONE,
  locale = 'ko-KR',
): string {
  const weekEndInclusive = addLocalDays(weekStart, 6);
  const format = (date: Date) =>
    formatDateTime(date, {
      day: 'numeric',
      locale,
      month: 'numeric',
      timeZone,
    });
  return `${format(weekStart)} - ${format(weekEndInclusive)}`;
}

function parseLocalDateOnly(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

export function parseAvailabilityBoundary(
  value: string,
  allDay: boolean,
): Date {
  if (allDay || !value.includes('T')) {
    return parseLocalDateOnly(value);
  }
  return parseServerDateTime(value);
}

function blockOverlapsRange(
  block: MeetingAvailabilityBlock,
  rangeStart: Date,
  rangeEnd: Date,
): boolean {
  const blockStart = parseAvailabilityBoundary(block.start, block.allDay);
  const blockEnd = parseAvailabilityBoundary(block.end, block.allDay);
  return blockEnd > rangeStart && blockStart < rangeEnd;
}

export function formatAvailabilityBlockLabel(
  block: MeetingAvailabilityBlock,
  timeZone = DEFAULT_TIME_ZONE,
  locale = 'ko-KR',
  labels = DEFAULT_AVAILABILITY_BLOCK_LABELS,
): string {
  const title = block.masked ? labels.busy : (block.title ?? labels.schedule);
  if (block.allDay) {
    const start = parseAvailabilityBoundary(block.start, true);
    const endExclusive = parseAvailabilityBoundary(block.end, true);
    const endInclusive = addLocalDays(endExclusive, -1);
    const startLabel = formatDateOnly(block.start, {
      day: 'numeric',
      locale,
      month: 'numeric',
    });
    const endLabel = formatDateOnly(
      `${endInclusive.getFullYear()}-${String(endInclusive.getMonth() + 1).padStart(2, '0')}-${String(endInclusive.getDate()).padStart(2, '0')}`,
      {
        day: 'numeric',
        locale,
        month: 'numeric',
      },
    );
    if (start.getTime() === endInclusive.getTime()) {
      return `${title} · ${startLabel}`;
    }
    return `${title} · ${startLabel} - ${endLabel}`;
  }
  const start = parseAvailabilityBoundary(block.start, false);
  const end = parseAvailabilityBoundary(block.end, false);
  return `${title} · ${formatDateTime(start, {
    hour: '2-digit',
    hour12: false,
    locale,
    minute: '2-digit',
    timeZone,
  })}-${formatDateTime(end, {
    hour: '2-digit',
    hour12: false,
    locale,
    minute: '2-digit',
    timeZone,
  })}`;
}

export function buildAvailabilityConflicts(
  items: MeetingAvailabilityItem[],
  meetingStart: Date,
  meetingEnd: Date,
  timeZone = DEFAULT_TIME_ZONE,
  locale = 'ko-KR',
  labels = DEFAULT_AVAILABILITY_BLOCK_LABELS,
): AvailabilityConflictItem[] {
  return items.flatMap((item) => {
    const matching = item.blocks.filter((block) =>
      blockOverlapsRange(block, meetingStart, meetingEnd),
    );
    if (matching.length === 0) {
      return [];
    }
    return [
      {
        userId: item.userId,
        fullName: item.fullName,
        block: matching[0],
        label: formatAvailabilityBlockLabel(
          matching[0],
          timeZone,
          locale,
          labels,
        ),
      },
    ];
  });
}

export function useMeetingAvailabilityQuery(options: {
  workspaceSlug: string;
  userIds: string[];
  rangeStart: Date | null;
  rangeEnd: Date | null;
  enabled?: boolean;
}) {
  const { token } = useAuth();
  const { t } = useTranslation('apps');
  const {
    workspaceSlug,
    userIds,
    rangeStart,
    rangeEnd,
    enabled = true,
  } = options;
  const [{ items, loading, error }, dispatch] = useReducer(
    meetingAvailabilityQueryReducer,
    INITIAL_MEETING_AVAILABILITY_QUERY_STATE,
  );

  const userIdsKey = useMemo(
    () => Array.from(new Set(userIds.filter(Boolean))).join('\u0000'),
    [userIds],
  );
  const uniqueUserIds = useMemo(
    () => userIdsKey.split('\u0000').filter(Boolean),
    [userIdsKey],
  );
  const rangeStartMs = rangeStart?.getTime() ?? null;
  const rangeEndMs = rangeEnd?.getTime() ?? null;

  useEffect(() => {
    let cancelled = false;
    if (
      !enabled ||
      !token ||
      !workspaceSlug ||
      uniqueUserIds.length === 0 ||
      rangeStartMs === null ||
      rangeEndMs === null
    ) {
      dispatch({ type: 'idle' });
      return () => {
        cancelled = true;
      };
    }

    dispatch({ type: 'loading' });
    getMeetingAvailability(token, workspaceSlug, {
      userIds: uniqueUserIds,
      from: new Date(rangeStartMs).toISOString(),
      to: new Date(rangeEndMs).toISOString(),
    })
      .then((response) => {
        if (cancelled) return;
        dispatch({ type: 'loaded', items: response.items });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        dispatch({
          type: 'failed',
          message: err.message ?? t('meeting.availabilityLoadFailed'),
        });
      });

    return () => {
      cancelled = true;
    };
  }, [
    enabled,
    token,
    workspaceSlug,
    uniqueUserIds,
    userIdsKey,
    rangeStartMs,
    rangeEndMs,
    t,
  ]);

  return {
    items,
    loading,
    error,
  };
}

export function formatAvailabilityDayLabel(
  date: Date,
  timeZone = DEFAULT_TIME_ZONE,
  locale = 'ko-KR',
): string {
  return formatDateTime(date, {
    day: 'numeric',
    locale,
    month: 'numeric',
    timeZone,
    weekday: 'short',
  });
}
