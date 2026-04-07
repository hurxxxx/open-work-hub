import { useMemo } from 'react';
import { cn } from '@/src/lib/utils';
import type { PmsIssue } from '@/src/domains/pms/pms-api';
import { STATUS_DOT_COLOR } from './pms-constants';

export const GanttView = ({ issues }: { issues: PmsIssue[] }) => {
  const { dates, startDate } = useMemo(() => {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const d = Array.from({ length: daysInMonth }, (_, i) => i + 1);
    return { dates: d, startDate: start };
  }, []);

  function getBarStyle(issue: PmsIssue) {
    const start = issue.start_date ? new Date(issue.start_date) : null;
    const end = issue.due_date ? new Date(issue.due_date) : null;
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
      <div className="flex border-b border-clickup-border bg-clickup-sidebar/30">
        <div className="w-64 border-r border-clickup-border p-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest shrink-0">Task Name</div>
        <div className="flex-1 flex overflow-x-auto custom-scrollbar">
          {dates.map(date => (
            <div key={date} className="flex-shrink-0 w-10 py-3 text-center border-r border-clickup-border last:border-r-0">
              <div className="text-[10px] font-bold text-clickup-text">{date}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {issues.map(issue => {
          const barStyle = getBarStyle(issue);
          return (
            <div key={issue.id} className="flex border-b border-clickup-border hover:bg-clickup-hover transition-colors">
              <div className="w-64 border-r border-clickup-border p-4 flex items-center gap-3 shrink-0">
                <div className={cn("w-2 h-2 rounded-full shrink-0", STATUS_DOT_COLOR[issue.status])} />
                <span className="text-xs text-clickup-text truncate font-medium">{issue.title}</span>
              </div>
              <div className="flex-1 flex relative" style={{ minWidth: `${dates.length * 40}px` }}>
                {barStyle && (
                  <div
                    className={cn(
                      "absolute top-1/2 -translate-y-1/2 h-5 rounded-full flex items-center px-2 text-[9px] font-bold text-white",
                      STATUS_DOT_COLOR[issue.status] ?? 'bg-gray-500',
                    )}
                    style={barStyle}
                  >
                    {issue.status_label}
                  </div>
                )}
                {dates.map(date => (
                  <div key={date} className="flex-shrink-0 w-10 border-r border-clickup-border last:border-r-0 h-12" />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
