import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  getMeetingAvailability,
  parseServerDateTime,
  type MeetingAvailabilityBlock,
  type MeetingAvailabilityItem,
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

export const HALF_HOUR_MS = 30 * 60 * 1000;
/** Legacy fixed-width constants — still referenced by inline previews that
 *  use pixel-based layouts. The main availability modal now lays out the
 *  week strip responsively with percentages. */
export const DAY_WIDTH_PX = 192;
export const SLOT_WIDTH_PX = DAY_WIDTH_PX / 48;
export const AVAILABILITY_NAME_COLUMN_PX = 208;

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

function formatShortDate(date: Date, timeZone: string): string {
  return formatDateTime(date, {
    day: 'numeric',
    locale: 'ko-KR',
    month: 'numeric',
    timeZone,
  });
}

export function formatAvailabilityWeekLabel(
  weekStart: Date,
  timeZone = DEFAULT_TIME_ZONE,
  locale = 'ko-KR',
): string {
  const weekEndInclusive = addLocalDays(weekStart, 6);
  const format = (date: Date) => formatDateTime(date, {
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

export function parseAvailabilityBoundary(value: string, allDay: boolean): Date {
  if (allDay || !value.includes('T')) {
    return parseLocalDateOnly(value);
  }
  return parseServerDateTime(value);
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
    const matching = item.blocks.filter((block) => blockOverlapsRange(block, meetingStart, meetingEnd));
    if (matching.length === 0) {
      return [];
    }
    return [
      {
        userId: item.userId,
        fullName: item.fullName,
        block: matching[0],
        label: formatAvailabilityBlockLabel(matching[0], timeZone, locale, labels),
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
  const [items, setItems] = useState<MeetingAvailabilityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        setError(err.message ?? t('meeting.availabilityLoadFailed'));
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, token, workspaceSlug, uniqueUserIds, userIdsKey, rangeStartMs, rangeEndMs, t]);

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
