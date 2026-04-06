import { cn } from '@/src/lib/utils';
import { Task } from '@/src/types';
import { STATUS_COLORS } from '@/src/mockData';

export const CalendarView = ({ tasks }: { tasks: Task[] }) => {
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const dates = Array.from({ length: 35 }, (_, i) => i - 3); // Mock dates for a month view

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
        {dates.map((date, i) => (
          <div 
            key={i} 
            className={cn(
              "p-2 border-r border-b border-clickup-border last:border-r-0 min-h-[120px] hover:bg-clickup-hover/50 transition-colors group",
              (date < 1 || date > 31) && "bg-clickup-sidebar/20"
            )}
          >
            <div className="text-[10px] font-bold text-gray-600 mb-2">
              {date > 0 && date <= 31 ? date : ''}
            </div>
            
            <div className="space-y-1">
              {tasks.filter(t => t.dueDate === `Apr ${date < 10 ? '0' + date : date}`).map((task, idx) => (
                <div key={idx} className={cn(
                  "px-1.5 py-1 rounded text-[9px] truncate border-l-2 shadow-sm",
                  STATUS_COLORS[task.status],
                  "bg-opacity-20 text-white border-opacity-100"
                )} style={{ borderLeftColor: 'currentColor' }}>
                  {task.name}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
