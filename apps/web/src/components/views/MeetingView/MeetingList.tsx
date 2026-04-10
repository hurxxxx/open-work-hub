import { useMemo } from 'react';
import { CheckSquare, FileText, Users } from 'lucide-react';

import type { MeetingListItem } from '@/src/domains/meeting/meeting-api';

interface MeetingListProps {
  items: MeetingListItem[];
  activeId: string | null;
  onSelect: (id: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
  scheduled: '예정',
  in_progress: '진행 중',
  completed: '완료',
  cancelled: '취소됨',
};

const STATUS_COLORS: Record<string, string> = {
  scheduled: 'bg-app-accent/15 text-app-accent',
  in_progress:
    'bg-[var(--ui-color-success)]/15 text-[var(--ui-color-success)]',
  completed: 'bg-app-ink/10 text-app-ink/60 dark:text-app-ink/70',
  cancelled:
    'bg-[var(--ui-color-danger)]/15 text-[var(--ui-color-danger)]',
};

function formatTimeRange(start: string, end: string): string {
  const startDate = new Date(start);
  const endDate = new Date(end);
  const dateLabel = startDate.toLocaleDateString('ko-KR', {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
  });
  const startTime = startDate.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
  });
  const endTime = endDate.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return `${dateLabel} · ${startTime} – ${endTime}`;
}

export function MeetingList({ items, activeId, onSelect }: MeetingListProps) {
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
                    {formatTimeRange(item.start_at, item.end_at)} · {item.organizer_name}
                  </p>
                </div>
                <span
                  className={`app-text-overline shrink-0 rounded-full px-2 py-0.5 ${
                    STATUS_COLORS[item.status] ?? 'bg-app-ink/10 text-app-ink/60 dark:text-app-ink/70'
                  }`}
                >
                  {STATUS_LABELS[item.status] ?? item.status}
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
