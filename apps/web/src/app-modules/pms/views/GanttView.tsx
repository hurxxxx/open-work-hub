import { useMemo } from 'react';
import { cn } from '@/src/lib/utils';
import { parseDateOnlyParts } from '@/src/platform/time/time-utils';
import type { PmsIssue, PmsTaskListStatus } from '../api/pms-api';
import { STATUS_DOT_COLOR } from './pms-constants';

function getGanttDotColor(slug: string): string {
  if (STATUS_DOT_COLOR[slug]) return STATUS_DOT_COLOR[slug];
  return '';
}

function getGanttDotStyle(slug: string, taskListStatuses?: PmsTaskListStatus[]): React.CSSProperties | undefined {
  if (STATUS_DOT_COLOR[slug]) return undefined;
  const ps = taskListStatuses?.find(s => s.slug === slug);
  return ps ? { backgroundColor: ps.color } : { backgroundColor: '#6b7280' };
}

function dateOnlyToLocalDate(value: string | null | undefined): Date | null {
  const parts = parseDateOnlyParts(value);
  return parts ? new Date(parts.year, parts.month - 1, parts.day) : null;
}

export const GanttView = ({ issues, taskListStatuses }: { issues: PmsIssue[]; taskListStatuses?: PmsTaskListStatus[] }) => {
  const { dates, startDate } = useMemo(() => {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const d = Array.from({ length: daysInMonth }, (_, i) => i + 1);
    return { dates: d, startDate: start };
  }, []);

  function getBarStyle(issue: PmsIssue) {
    const start = dateOnlyToLocalDate(issue.start_date);
    const end = dateOnlyToLocalDate(issue.due_date);
    if (!start && !end) return null;

    const monthStart = startDate.getTime();
    const dayWidth = 40; // px per day
    const startDay = start ? Math.max(0, Math.floor((start.getTime() - monthStart) / 86400000)) : 0;
    const endDay = end ? Math.floor((end.getTime() - monthStart) / 86400000) : startDay + 3;
    const width = Math.max(1, endDay - startDay + 1) * dayWidth;

    return { left: `${startDay * dayWidth}px`, width: `${width}px` };
  }

  return (
    <div className="h-full flex flex-col card p-0 overflow-hidden">
      <div className="flex border-b border-app-border bg-app-surface-sidebar/30">
        <div className="app-text-overline w-64 shrink-0 border-r border-app-border p-4 text-gray-500">Task Name</div>
        <div className="flex-1 flex overflow-x-auto custom-scrollbar">
          {dates.map(date => (
            <div key={date} className="flex-shrink-0 w-10 py-3 text-center border-r border-app-border last:border-r-0">
              <div className="app-text-micro font-bold text-app-ink">{date}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {issues.map(issue => {
          const barStyle = getBarStyle(issue);
          return (
            <div key={issue.id} className="flex border-b border-app-border hover:bg-app-surface-hover transition-colors">
              <div className="w-64 border-r border-app-border p-4 flex items-center gap-3 shrink-0">
                <div className={cn("w-2 h-2 rounded-full shrink-0", getGanttDotColor(issue.status))} style={getGanttDotStyle(issue.status, taskListStatuses)} />
                <span className="app-text-body-sm truncate font-medium text-app-ink">{issue.title}</span>
              </div>
              <div className="flex-1 flex relative" style={{ minWidth: `${dates.length * 40}px` }}>
                {barStyle && (
                  <div
                    className={cn(
                      "app-text-micro absolute top-1/2 flex h-5 items-center rounded-full px-2 font-bold text-white -translate-y-1/2",
                      getGanttDotColor(issue.status) || 'bg-gray-500',
                    )}
                    style={barStyle}
                  >
                    {issue.status_label}
                  </div>
                )}
                {dates.map(date => (
                  <div key={date} className="flex-shrink-0 w-10 border-r border-app-border last:border-r-0 h-12" />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
