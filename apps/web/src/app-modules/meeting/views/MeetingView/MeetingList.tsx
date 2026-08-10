import { CheckSquare, FileText, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { MeetingListItem } from '../../api/meeting-api';
import { buildMeetingListRows } from './meeting-list-view-model';

interface MeetingListProps {
  items: MeetingListItem[];
  activeId: string | null;
  timeZone: string;
  onSelect: (id: string) => void;
}

export function MeetingList({
  items,
  activeId,
  timeZone,
  onSelect,
}: MeetingListProps) {
  const { t, i18n } = useTranslation('apps');
  const rows = buildMeetingListRows({
    activeId,
    items,
    locale: i18n.language,
    timeZone,
  });

  return (
    <ul className="divide-y divide-app-border">
      {rows.map((row) => {
        return (
          <li key={row.item.id}>
            <button
              type="button"
              onClick={() => onSelect(row.item.id)}
              className={`flex w-full flex-col gap-1 px-6 py-4 text-left transition-colors hover:bg-app-surface-hover ${
                row.isActive ? 'bg-app-surface-hover' : ''
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="app-text-body font-medium text-app-ink line-clamp-1">
                    {row.item.title}
                  </p>
                  <p className="app-text-caption text-app-ink/60 dark:text-app-ink/70">
                    {row.timeRange} · {row.item.organizer_name}
                  </p>
                </div>
                <span
                  className={`app-text-overline shrink-0 rounded-full px-2 py-0.5 ${row.statusClassName}`}
                >
                  {row.statusLabelKey ? t(row.statusLabelKey) : row.item.status}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-3 text-app-ink/60 dark:text-app-ink/70">
                <span className="app-text-caption inline-flex items-center gap-1">
                  <Users size={12} />
                  {row.item.attendee_count}
                </span>
                <span className="app-text-caption inline-flex items-center gap-1">
                  <CheckSquare size={12} />
                  {row.item.task_link_count}
                </span>
                <span className="app-text-caption inline-flex items-center gap-1">
                  <FileText size={12} />
                  {row.item.doc_link_count}
                </span>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
