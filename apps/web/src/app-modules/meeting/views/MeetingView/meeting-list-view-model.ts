import {
  parseServerDateTime,
  type MeetingListItem,
  type MeetingScope,
} from '../../api/meeting-api';
import { formatDateTime } from '@/src/platform/time/time-utils';

export type MeetingTab = 'upcoming' | 'mine' | 'recordings';

export const MEETING_CREATE_EVENT = 'meeting:create-event';

export const MEETING_TABS: {
  id: MeetingTab;
  labelKey: string;
  scope: MeetingScope;
}[] = [
  { id: 'upcoming', labelKey: 'meeting.scheduled', scope: 'upcoming' },
  { id: 'mine', labelKey: 'meeting.mine', scope: 'mine' },
  { id: 'recordings', labelKey: 'meeting.recordings', scope: 'mine' },
];

export interface MeetingListViewState {
  createOpen: boolean;
  error: string | null;
  items: MeetingListItem[] | null;
  loading: boolean;
}

export type MeetingListViewAction =
  | { type: 'load-started' }
  | { items: MeetingListItem[]; type: 'load-succeeded' }
  | { error: string; type: 'load-failed' }
  | { type: 'create-opened' }
  | { type: 'create-closed' };

export const INITIAL_MEETING_LIST_VIEW_STATE: MeetingListViewState = {
  createOpen: false,
  error: null,
  items: null,
  loading: false,
};

const STATUS_LABEL_KEYS: Record<string, string> = {
  scheduled: 'meeting.scheduled',
  in_progress: 'meeting.inProgress',
  completed: 'meeting.completed',
  cancelled: 'meeting.cancelled',
};

const STATUS_COLORS: Record<string, string> = {
  scheduled: 'bg-app-accent/15 text-app-accent',
  in_progress: 'bg-[var(--ui-color-success)]/15 text-[var(--ui-color-success)]',
  completed: 'bg-app-ink/10 text-app-ink/60 dark:text-app-ink/70',
  cancelled: 'bg-[var(--ui-color-danger)]/15 text-[var(--ui-color-danger)]',
};

const FALLBACK_STATUS_CLASS =
  'bg-app-ink/10 text-app-ink/60 dark:text-app-ink/70';

export interface MeetingListRow {
  item: MeetingListItem;
  isActive: boolean;
  statusClassName: string;
  statusLabelKey: string | null;
  timeRange: string;
}

export function meetingListViewReducer(
  state: MeetingListViewState,
  action: MeetingListViewAction,
): MeetingListViewState {
  switch (action.type) {
    case 'load-started':
      return { ...state, error: null, loading: true };
    case 'load-succeeded':
      return { ...state, items: action.items, loading: false };
    case 'load-failed':
      return {
        ...state,
        error: action.error,
        items: [],
        loading: false,
      };
    case 'create-opened':
      return { ...state, createOpen: true };
    case 'create-closed':
      return { ...state, createOpen: false };
  }
}

export function buildMeetingListRows({
  activeId,
  items,
  locale,
  timeZone,
}: {
  activeId: string | null;
  items: MeetingListItem[];
  locale: string;
  timeZone: string;
}): MeetingListRow[] {
  return Array.from(items)
    .sort((a, b) => a.start_at.localeCompare(b.start_at))
    .map((item) => ({
      item,
      isActive: item.id === activeId,
      statusClassName: STATUS_COLORS[item.status] ?? FALLBACK_STATUS_CLASS,
      statusLabelKey: STATUS_LABEL_KEYS[item.status] ?? null,
      timeRange: formatTimeRange(item.start_at, item.end_at, timeZone, locale),
    }));
}

export function formatTimeRange(
  start: string,
  end: string,
  timeZone: string,
  locale: string,
): string {
  const startDate = parseServerDateTime(start);
  const endDate = parseServerDateTime(end);
  const dateLabel = formatDateTime(startDate, {
    locale,
    month: 'short',
    day: 'numeric',
    weekday: 'short',
    timeZone,
  });
  const startTime = formatDateTime(startDate, {
    hour: '2-digit',
    locale,
    minute: '2-digit',
    timeZone,
  });
  const endTime = formatDateTime(endDate, {
    hour: '2-digit',
    locale,
    minute: '2-digit',
    timeZone,
  });
  return `${dateLabel} · ${startTime} – ${endTime}`;
}

export function resolveMeetingTab(value: string | null): MeetingTab {
  return MEETING_TABS.some((tab) => tab.id === value)
    ? (value as MeetingTab)
    : 'upcoming';
}

export function resolveMeetingScope(tab: MeetingTab): MeetingScope {
  return MEETING_TABS.find((item) => item.id === tab)?.scope ?? 'upcoming';
}

export function createMeetingTabSearchParams({
  searchParams,
  tab,
}: {
  searchParams: URLSearchParams;
  tab: MeetingTab;
}): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.set('tab', tab);
  return next;
}

export function consumeMeetingCreateSearchParam(
  searchParams: URLSearchParams,
): URLSearchParams | null {
  if (searchParams.get('create') !== '1') {
    return null;
  }
  const next = new URLSearchParams(searchParams);
  next.delete('create');
  return next;
}
