import { useEffect, useState } from 'react';

import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  getMeetingAvailability,
  type MeetingAvailabilityBlock,
  type MeetingAvailabilityItem,
} from '@/src/domains/meeting/meeting-api';

export const HALF_HOUR_MS = 30 * 60 * 1000;
/** Legacy fixed-width constants — still referenced by inline previews that
 *  use pixel-based layouts. The main availability modal now lays out the
 *  week strip responsively with percentages. */
export const DAY_WIDTH_PX = 192;
export const SLOT_WIDTH_PX = DAY_WIDTH_PX / 48;
export const AVAILABILITY_NAME_COLUMN_PX = 208;

const SHORT_DATE_FORMATTER = new Intl.DateTimeFormat('ko-KR', {
  month: 'numeric',
  day: 'numeric',
});
const WEEKDAY_FORMATTER = new Intl.DateTimeFormat('ko-KR', {
  month: 'numeric',
  day: 'numeric',
  weekday: 'short',
});
const TIME_FORMATTER = new Intl.DateTimeFormat('ko-KR', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

export interface AvailabilityConflictItem {
  userId: string;
  fullName: string;
  block: MeetingAvailabilityBlock;
  label: string;
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

export function formatAvailabilityWeekLabel(weekStart: Date): string {
  const weekEndInclusive = addLocalDays(weekStart, 6);
  return `${SHORT_DATE_FORMATTER.format(weekStart)} - ${SHORT_DATE_FORMATTER.format(weekEndInclusive)}`;
}

function parseLocalDateOnly(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

export function parseAvailabilityBoundary(value: string, allDay: boolean): Date {
  if (allDay || !value.includes('T')) {
    return parseLocalDateOnly(value);
  }
  return new Date(value);
}

export function blockOverlapsRange(
  block: MeetingAvailabilityBlock,
  rangeStart: Date,
  rangeEnd: Date,
): boolean {
  const blockStart = parseAvailabilityBoundary(block.start, block.allDay);
  const blockEnd = parseAvailabilityBoundary(block.end, block.allDay);
  return blockEnd > rangeStart && blockStart < rangeEnd;
}

export function formatAvailabilityBlockLabel(block: MeetingAvailabilityBlock): string {
  const title = block.masked ? 'Busy' : (block.title ?? '일정');
  if (block.allDay) {
    const start = parseAvailabilityBoundary(block.start, true);
    const endExclusive = parseAvailabilityBoundary(block.end, true);
    const endInclusive = addLocalDays(endExclusive, -1);
    if (start.getTime() === endInclusive.getTime()) {
      return `${title} · ${SHORT_DATE_FORMATTER.format(start)}`;
    }
    return `${title} · ${SHORT_DATE_FORMATTER.format(start)} - ${SHORT_DATE_FORMATTER.format(endInclusive)}`;
  }
  const start = parseAvailabilityBoundary(block.start, false);
  const end = parseAvailabilityBoundary(block.end, false);
  return `${title} · ${TIME_FORMATTER.format(start)}-${TIME_FORMATTER.format(end)}`;
}

export function buildAvailabilityConflicts(
  items: MeetingAvailabilityItem[],
  meetingStart: Date,
  meetingEnd: Date,
): AvailabilityConflictItem[] {
  return items.flatMap((item) => {
    const matching = item.blocks.filter((block) => blockOverlapsRange(block, meetingStart, meetingEnd));
    if (matching.length === 0) {
      return [];
    }
    return [
      {
        userId: item.userId,
        fullName: item.fullName,
        block: matching[0],
        label: formatAvailabilityBlockLabel(matching[0]),
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
  const {
    workspaceSlug,
    userIds,
    rangeStart,
    rangeEnd,
    enabled = true,
  } = options;
  const [items, setItems] = useState<MeetingAvailabilityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const uniqueUserIds = Array.from(new Set(userIds.filter(Boolean)));
  const userIdsKey = uniqueUserIds.join('\u0000');
  const rangeStartMs = rangeStart?.getTime() ?? null;
  const rangeEndMs = rangeEnd?.getTime() ?? null;

  useEffect(() => {
    let cancelled = false;
    if (
      !enabled
      || !token
      || !workspaceSlug
      || uniqueUserIds.length === 0
      || rangeStartMs === null
      || rangeEndMs === null
    ) {
      setItems([]);
      setLoading(false);
      setError(null);
      return () => {
        cancelled = true;
      };
    }

    setLoading(true);
    setError(null);
    getMeetingAvailability(token, workspaceSlug, {
      userIds: uniqueUserIds,
      from: new Date(rangeStartMs).toISOString(),
      to: new Date(rangeEndMs).toISOString(),
    })
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? '참석자 일정을 불러올 수 없습니다.');
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, token, workspaceSlug, userIdsKey, rangeStartMs, rangeEndMs]);

  return {
    items,
    loading,
    error,
  };
}

export function formatAvailabilityDayLabel(date: Date): string {
  return WEEKDAY_FORMATTER.format(date);
}
