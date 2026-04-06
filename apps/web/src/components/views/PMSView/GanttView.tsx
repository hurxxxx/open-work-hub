import { cn } from '@/src/lib/utils';
import { Task } from '@/src/types';
import { STATUS_COLORS } from '@/src/mockData';

export const GanttView = ({ tasks }: { tasks: Task[] }) => {
  const dates = Array.from({ length: 14 }, (_, i) => i + 1); // Mock 14 days

  return (
    <div className="h-full flex flex-col card p-0 overflow-hidden">
      <div className="flex border-b border-clickup-border bg-clickup-sidebar/30">
        <div className="w-64 border-r border-clickup-border p-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">Task Name</div>
        <div className="flex-1 flex overflow-x-auto custom-scrollbar">
          {dates.map(date => (
            <div key={date} className="flex-shrink-0 w-20 py-4 text-center border-r border-clickup-border last:border-r-0">
              <div className="text-[10px] text-gray-600">Apr</div>
              <div className="text-xs font-bold text-clickup-text">{date < 10 ? `0${date}` : date}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {tasks.map(task => (
          <div key={task.id} className="flex border-b border-clickup-border hover:bg-clickup-hover transition-colors group">
            <div className="w-64 border-r border-clickup-border p-4 flex items-center gap-3">
              <div className={cn("w-2 h-2 rounded-full", STATUS_COLORS[task.status])} />
              <span className="text-xs text-clickup-text truncate font-medium">{task.name}</span>
            </div>
            <div className="flex-1 flex relative">
              {/* Mock Gantt Bar */}
              <div 
                className={cn(
                  "absolute top-1/2 -translate-y-1/2 h-6 rounded-full shadow-lg flex items-center px-3 text-[9px] font-bold text-white",
                  STATUS_COLORS[task.status]
                )}
                style={{ 
                  left: `${(parseInt(task.id) * 40) % 200}px`, 
                  width: `${100 + (parseInt(task.id) * 20) % 150}px` 
                }}
              >
                {task.status}
              </div>
              {dates.map(date => (
                <div key={date} className="flex-shrink-0 w-20 border-r border-clickup-border last:border-r-0 h-14" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
