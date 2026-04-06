import { motion } from 'motion/react';
import { 
  Plus, 
  MoreHorizontal, 
  Flag, 
  Calendar, 
  User2 
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { Task } from '@/src/types';
import { STATUS_COLORS, PRIORITY_COLORS } from '@/src/mockData';

export const BoardView = ({ tasks, onSelectTask }: { tasks: Task[], onSelectTask: (t: Task) => void }) => {
  const statuses = ['TO DO', 'IN PROGRESS', 'REVIEW', 'DONE'] as const;

  return (
    <div className="flex gap-6 h-full overflow-x-auto pb-4 custom-scrollbar">
      {statuses.map(status => (
        <div key={status} className="flex-shrink-0 w-80 flex flex-col gap-4">
          <div className="flex items-center justify-between px-2">
            <div className="flex items-center gap-2">
              <div className={cn("w-2 h-2 rounded-full", STATUS_COLORS[status])} />
              <h3 className="text-xs font-bold text-clickup-text uppercase tracking-wider">{status}</h3>
              <span className="text-[10px] text-gray-600 font-bold">{tasks.filter(t => t.status === status).length}</span>
            </div>
            <div className="flex items-center gap-1 text-gray-600">
              <Plus size={14} className="cursor-pointer hover:text-white" />
              <MoreHorizontal size={14} className="cursor-pointer hover:text-white" />
            </div>
          </div>

          <div className="flex-1 space-y-3">
            {tasks.filter(t => t.status === status).map(task => (
              <motion.div
                key={task.id}
                layoutId={task.id}
                onClick={() => onSelectTask(task)}
                className="card p-4 hover:border-clickup-purple transition-all cursor-pointer group space-y-4"
              >
                <div className="flex flex-wrap gap-1">
                  {task.tags.map(tag => (
                    <span key={tag} className="px-1.5 py-0.5 bg-clickup-sidebar border border-clickup-border rounded text-[9px] text-gray-500">
                      {tag}
                    </span>
                  ))}
                </div>
                <h4 className="text-sm font-medium text-clickup-text leading-tight group-hover:text-clickup-purple transition-colors">
                  {task.name}
                </h4>
                <div className="flex items-center justify-between pt-2 border-t border-clickup-border/50">
                  <div className="flex items-center gap-3">
                    <Flag size={14} className={PRIORITY_COLORS[task.priority]} />
                    {task.dueDate && (
                      <div className="flex items-center gap-1 text-[10px] text-gray-500">
                        <Calendar size={10} />
                        <span>{task.dueDate}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center -space-x-2">
                    {task.assignee ? (
                      <div className="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center text-[9px] font-bold text-white border-2 border-clickup-bg">
                        {task.assignee.avatar}
                      </div>
                    ) : (
                      <div className="w-6 h-6 rounded-full bg-clickup-sidebar border-2 border-clickup-bg flex items-center justify-center text-gray-600">
                        <User2 size={12} />
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
            <button className="w-full py-2 border border-dashed border-clickup-border rounded-lg text-[10px] text-gray-600 hover:text-gray-400 hover:border-gray-400 transition-all">
              + Add Task
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};
