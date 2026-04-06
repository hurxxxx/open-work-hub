import { useState } from 'react';
import { Calendar, Clock, AlertCircle, CheckCircle2 } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { Task } from '@/src/types';
import { MOCK_TASKS } from '@/src/mockData';

export const TodayOverdueView = () => {
  const [viewMode, setViewMode] = useState<'agenda' | 'day'>('day');

  // Mock data for today and overdue
  const overdueTasks = MOCK_TASKS.filter(t => t.priority === 'URGENT' || t.dueDate === 'Apr 01');
  const todayTasks = MOCK_TASKS.filter(t => t.priority !== 'URGENT' && t.dueDate !== 'Apr 01').slice(0, 3);

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-clickup-bg border-b border-clickup-border px-8 pt-6 pb-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-clickup-text">Today & Overdue</h1>
            <p className="text-gray-500 text-sm mt-1">Focus on what's important right now</p>
          </div>
          <div className="flex items-center bg-clickup-sidebar rounded-lg p-1 border border-clickup-border">
            <button
              onClick={() => setViewMode('agenda')}
              className={cn(
                "px-4 py-1.5 text-sm font-medium rounded-md transition-colors",
                viewMode === 'agenda' ? "bg-clickup-border text-clickup-text" : "text-gray-500 hover:text-clickup-text"
              )}
            >
              Agenda
            </button>
            <button
              onClick={() => setViewMode('day')}
              className={cn(
                "px-4 py-1.5 text-sm font-medium rounded-md transition-colors",
                viewMode === 'day' ? "bg-clickup-border text-clickup-text" : "text-gray-500 hover:text-clickup-text"
              )}
            >
              Day
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        {viewMode === 'agenda' ? (
          <AgendaView overdueTasks={overdueTasks} todayTasks={todayTasks} />
        ) : (
          <DayView tasks={[...overdueTasks, ...todayTasks]} />
        )}
      </main>
    </div>
  );
};

const AgendaView = ({ overdueTasks, todayTasks }: { overdueTasks: Task[], todayTasks: Task[] }) => {
  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Overdue Section */}
      <section>
        <div className="flex items-center gap-2 mb-4 text-red-500">
          <AlertCircle size={18} />
          <h2 className="text-lg font-semibold">Overdue</h2>
          <span className="bg-red-500/10 text-red-500 text-xs px-2 py-0.5 rounded-full">{overdueTasks.length}</span>
        </div>
        <div className="space-y-2">
          {overdueTasks.map(task => (
            <TaskAgendaItem key={task.id} task={task} isOverdue />
          ))}
        </div>
      </section>

      {/* Today Section */}
      <section>
        <div className="flex items-center gap-2 mb-4 text-blue-400">
          <Calendar size={18} />
          <h2 className="text-lg font-semibold">Today</h2>
          <span className="bg-blue-400/10 text-blue-400 text-xs px-2 py-0.5 rounded-full">{todayTasks.length}</span>
        </div>
        <div className="space-y-2">
          {todayTasks.map(task => (
            <TaskAgendaItem key={task.id} task={task} />
          ))}
        </div>
      </section>
    </div>
  );
};

const TaskAgendaItem = ({ task, isOverdue = false }: { task: Task, isOverdue?: boolean }) => {
  return (
    <div className="flex items-center justify-between p-4 bg-clickup-sidebar border border-clickup-border rounded-lg hover:border-gray-600 transition-colors group cursor-pointer">
      <div className="flex items-center gap-4">
        <button className="text-gray-500 hover:text-green-500 transition-colors">
          <CheckCircle2 size={20} />
        </button>
        <div>
          <h3 className="text-sm font-medium text-clickup-text group-hover:text-clickup-purple transition-colors">{task.name}</h3>
          <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
            <span className={cn("flex items-center gap-1", isOverdue ? "text-red-500" : "")}>
              <Calendar size={12} />
              {task.dueDate}
            </span>
            {task.tags.length > 0 && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                {task.tags[0]}
              </span>
            )}
          </div>
        </div>
      </div>
      {task.assignee && (
        <div className="w-6 h-6 rounded-full bg-indigo-500 flex items-center justify-center text-[10px] text-white font-medium">
          {task.assignee.avatar}
        </div>
      )}
    </div>
  );
};

const DayView = ({ tasks }: { tasks: Task[] }) => {
  const hours = Array.from({ length: 11 }, (_, i) => i + 8); // 8 AM to 6 PM

  return (
    <div className="max-w-5xl mx-auto bg-clickup-sidebar border border-clickup-border rounded-lg overflow-hidden flex">
      {/* Time Column */}
      <div className="w-20 border-r border-clickup-border bg-clickup-bg/50 flex flex-col">
        {hours.map(hour => (
          <div key={hour} className="h-24 border-b border-clickup-border relative">
            <span className="absolute -top-3 right-3 text-xs text-gray-500 font-medium">
              {hour === 12 ? '12 PM' : hour > 12 ? `${hour - 12} PM` : `${hour} AM`}
            </span>
          </div>
        ))}
      </div>

      {/* Tasks Area */}
      <div className="flex-1 relative bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwJSIgaGVpZ2h0PSI5NiIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMCA5NkwxMDAwMCA5NiIgc3Ryb2tlPSJyZ2JhKDI1NSwyNTUsMjU1LDAuMDUpIiBzdHJva2Utd2lkdGg9IjEiIGZpbGw9Im5vbmUiLz48L3N2Zz4=')]">
        {/* Current Time Indicator (Mocked at 10:30 AM) */}
        <div className="absolute left-0 right-0 h-px bg-red-500 z-10" style={{ top: '240px' }}>
          <div className="absolute -left-2 -top-1.5 w-3 h-3 rounded-full bg-red-500"></div>
        </div>

        {/* Mocked Task Blocks */}
        <div className="absolute top-[48px] left-4 right-4 h-[96px] bg-blue-500/20 border border-blue-500/50 rounded-md p-3 hover:bg-blue-500/30 transition-colors cursor-pointer">
          <h4 className="text-sm font-medium text-blue-100">{tasks[0]?.name || 'Morning Sync'}</h4>
          <p className="text-xs text-blue-300 mt-1">08:30 AM - 09:30 AM</p>
        </div>

        <div className="absolute top-[288px] left-4 right-4 h-[144px] bg-purple-500/20 border border-purple-500/50 rounded-md p-3 hover:bg-purple-500/30 transition-colors cursor-pointer">
          <h4 className="text-sm font-medium text-purple-100">{tasks[1]?.name || 'Deep Work Session'}</h4>
          <p className="text-xs text-purple-300 mt-1">11:00 AM - 12:30 PM</p>
        </div>

        <div className="absolute top-[576px] left-4 right-4 h-[96px] bg-orange-500/20 border border-orange-500/50 rounded-md p-3 hover:bg-orange-500/30 transition-colors cursor-pointer">
          <h4 className="text-sm font-medium text-orange-100">{tasks[2]?.name || 'Team Meeting'}</h4>
          <p className="text-xs text-orange-300 mt-1">02:00 PM - 03:00 PM</p>
        </div>
        
        {/* Empty grid lines to match hours */}
        {hours.map(hour => (
          <div key={hour} className="h-24 border-b border-transparent"></div>
        ))}
      </div>
    </div>
  );
};
