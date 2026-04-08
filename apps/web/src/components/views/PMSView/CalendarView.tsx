import { useMemo } from 'react';
import { cn } from '@/src/lib/utils';
import type { PmsIssue, PmsProjectStatus } from '@/src/domains/pms/pms-api';

const STATUS_COLORS: Record<string, string> = {
  backlog: '#6b7280',
  todo: '#9ca3af',
  in_progress: '#3b82f6',
  done: '#22c55e',
  canceled: '#ef4444',
};

function getStatusColor(slug: string, projectStatuses?: PmsProjectStatus[]): string {
  if (STATUS_COLORS[slug]) return STATUS_COLORS[slug];
  const ps = projectStatuses?.find(s => s.slug === slug);
  return ps?.color ?? '#6b7280';
}

export const CalendarView = ({ issues, projectStatuses }: { issues: PmsIssue[]; projectStatuses?: PmsProjectStatus[] }) => {
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
      <div className="grid grid-cols-7 border-b border-clickup-border bg-clickup-sidebar/30">
        {days.map(day => (
          <div key={day} className="py-3 text-center text-[10px] font-bold uppercase tracking-widest text-gray-500 border-r border-clickup-border last:border-r-0">
            {day}
          </div>
        ))}
      </div>
      <div className="flex-1 grid grid-cols-7 grid-rows-5 overflow-y-auto custom-scrollbar">
        {calendarDays.map((date, i) => (
          <div
            key={i}
            className={cn(
              "p-2 border-r border-b border-clickup-border last:border-r-0 min-h-[120px] hover:bg-clickup-hover/50 transition-colors",
              date === null && "bg-clickup-sidebar/20"
            )}
          >
            <div className="text-[10px] font-bold text-gray-600 mb-2">
              {date ?? ''}
            </div>
            <div className="space-y-1">
              {date && issuesByDate[date]?.map(issue => (
                <div
                  key={issue.id}
                  className="px-1.5 py-1 rounded text-[9px] truncate border-l-2 bg-clickup-sidebar/60 text-clickup-text"
                  style={{ borderLeftColor: getStatusColor(issue.status, projectStatuses) }}
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
