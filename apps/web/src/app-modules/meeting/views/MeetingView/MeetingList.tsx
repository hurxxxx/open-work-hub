import { useMemo } from 'react';
import { CheckSquare, FileText, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  parseServerDateTime,
  type MeetingListItem,
} from '../../api/meeting-api';
import { formatDateTime } from '@/src/platform/time/time-utils';

interface MeetingListProps {
  items: MeetingListItem[];
  activeId: string | null;
  timeZone: string;
  onSelect: (id: string) => void;
}

const STATUS_LABEL_KEYS: Record<string, string> = {
  scheduled: 'meeting.scheduled',
  in_progress: 'meeting.inProgress',
  completed: 'meeting.completed',
  cancelled: 'meeting.cancelled',
};

const STATUS_COLORS: Record<string, string> = {
  scheduled: 'bg-app-accent/15 text-app-accent',
  in_progress:
    'bg-[var(--ui-color-success)]/15 text-[var(--ui-color-success)]',
  completed: 'bg-app-ink/10 text-app-ink/60 dark:text-app-ink/70',
  cancelled:
    'bg-[var(--ui-color-danger)]/15 text-[var(--ui-color-danger)]',
};

function formatTimeRange(start: string, end: string, timeZone: string, locale: string): string {
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

export function MeetingList({ items, activeId, timeZone, onSelect }: MeetingListProps) {
  const { t, i18n } = useTranslation('apps');
  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => a.start_at.localeCompare(b.start_at));
  }, [items]);

  return (
    <ul className="divide-y divide-app-border">
      {sortedItems.map((item) => {
        const isActive = item.id === activeId;
        return (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onSelect(item.id)}
              className={`flex w-full flex-col gap-1 px-6 py-4 text-left transition-colors hover:bg-app-surface-hover ${
                isActive ? 'bg-app-surface-hover' : ''
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="app-text-body font-medium text-app-ink line-clamp-1">
                    {item.title}
                  </p>
                  <p className="app-text-caption text-app-ink/60 dark:text-app-ink/70">
                    {formatTimeRange(item.start_at, item.end_at, timeZone, i18n.language)} · {item.organizer_name}
                  </p>
                </div>
                <span
                  className={`app-text-overline shrink-0 rounded-full px-2 py-0.5 ${
                    STATUS_COLORS[item.status] ?? 'bg-app-ink/10 text-app-ink/60 dark:text-app-ink/70'
                  }`}
                >
                  {STATUS_LABEL_KEYS[item.status] ? t(STATUS_LABEL_KEYS[item.status]) : item.status}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-3 text-app-ink/60 dark:text-app-ink/70">
                <span className="app-text-caption inline-flex items-center gap-1">
                  <Users size={12} />
                  {item.attendee_count}
                </span>
                <span className="app-text-caption inline-flex items-center gap-1">
                  <CheckSquare size={12} />
                  {item.task_link_count}
                </span>
                <span className="app-text-caption inline-flex items-center gap-1">
                  <FileText size={12} />
                  {item.doc_link_count}
                </span>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
