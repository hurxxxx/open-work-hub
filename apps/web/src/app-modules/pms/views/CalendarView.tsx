import { useMemo } from 'react';
import { cn } from '@/src/lib/utils';
import type { PmsIssue, PmsTaskListStatus } from '../api/pms-api';

const STATUS_COLORS: Record<string, string> = {
  backlog: '#6b7280',
  todo: '#9ca3af',
  in_progress: '#3b82f6',
  done: '#22c55e',
  canceled: '#ef4444',
};

function getStatusColor(slug: string, taskListStatuses?: PmsTaskListStatus[]): string {
  if (STATUS_COLORS[slug]) return STATUS_COLORS[slug];
  const ps = taskListStatuses?.find(s => s.slug === slug);
  return ps?.color ?? '#6b7280';
}

export const CalendarView = ({ issues, taskListStatuses }: { issues: PmsIssue[]; taskListStatuses?: PmsTaskListStatus[] }) => {
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  const { calendarDays, issuesByDate } = useMemo(() => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const calDays: (number | null)[] = [];
    for (let i = 0; i < firstDay; i++) calDays.push(null);
    for (let d = 1; d <= daysInMonth; d++) calDays.push(d);
    while (calDays.length < 35) calDays.push(null);

    const byDate: Record<number, PmsIssue[]> = {};
    for (const issue of issues) {
      if (!issue.due_date) continue;
      const d = new Date(issue.due_date);
      if (d.getFullYear() === year && d.getMonth() === month) {
        const day = d.getDate();
        (byDate[day] ??= []).push(issue);
      }
    }

    return { calendarDays: calDays, issuesByDate: byDate };
  }, [issues]);

  return (
    <div className="h-full flex flex-col card p-0 overflow-hidden">
      <div className="grid grid-cols-7 border-b border-app-border bg-app-surface-sidebar/30">
        {days.map(day => (
          <div key={day} className="app-text-overline border-r border-app-border py-3 text-center text-gray-500 last:border-r-0">
            {day}
          </div>
        ))}
      </div>
      <div className="flex-1 grid grid-cols-7 grid-rows-5 overflow-y-auto custom-scrollbar">
        {calendarDays.map((date, i) => (
          <div
            key={i}
            className={cn(
              "p-2 border-r border-b border-app-border last:border-r-0 min-h-[120px] hover:bg-app-surface-hover/50 transition-colors",
              date === null && "bg-app-surface-sidebar/20"
            )}
          >
            <div className="app-text-micro mb-2 font-bold text-gray-600">
              {date ?? ''}
            </div>
            <div className="space-y-1">
              {date && issuesByDate[date]?.map(issue => (
                <div
                  key={issue.id}
                  className="app-text-micro truncate rounded border-l-2 bg-app-surface-sidebar/60 px-1.5 py-1 text-app-ink"
                  style={{ borderLeftColor: getStatusColor(issue.status, taskListStatuses) }}
                >
                  {issue.reference} {issue.title}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
