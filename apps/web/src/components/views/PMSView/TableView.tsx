import { 
  MessageSquare, 
  Flag, 
  MoreHorizontal 
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { Task } from '@/src/types';
import { STATUS_COLORS, PRIORITY_COLORS } from '@/src/mockData';

export const TableView = ({ tasks, onSelectTask }: { tasks: Task[], onSelectTask: (t: Task) => void }) => {
  return (
    <div className="card p-0 overflow-hidden border border-clickup-border">
      <div className="overflow-x-auto custom-scrollbar">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-clickup-sidebar/50 border-b border-clickup-border text-gray-500 uppercase tracking-wider font-bold">
              <th className="py-3 px-4 w-12">#</th>
              <th className="py-3 px-4 min-w-[250px]">Task Name</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Assignee</th>
              <th className="py-3 px-4">Due Date</th>
              <th className="py-3 px-4">Priority</th>
              <th className="py-3 px-4">Tags</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-clickup-border">
            {tasks.map((task, i) => (
              <tr 
                key={task.id} 
                onClick={() => onSelectTask(task)}
                className="hover:bg-clickup-hover transition-colors group cursor-pointer"
              >
                <td className="py-3 px-4 text-gray-600">{i + 1}</td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <span className="text-clickup-text font-medium">{task.name}</span>
                    {task.comments > 0 && (
                      <div className="flex items-center gap-1 text-gray-600">
                        <MessageSquare size={12} />
                        <span className="text-[10px]">{task.comments}</span>
                      </div>
                    )}
                  </div>
                </td>
                <td className="py-3 px-4">
                  <div className={cn("inline-flex px-2 py-0.5 rounded text-[10px] font-bold text-white", STATUS_COLORS[task.status])}>
                    {task.status}
                  </div>
                </td>
                <td className="py-3 px-4">
                  {task.assignee ? (
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center text-[10px] font-bold text-white border border-clickup-border">
                        {task.assignee.avatar}
                      </div>
                      <span className="text-gray-400">{task.assignee.name}</span>
                    </div>
                  ) : (
                    <span className="text-gray-700">-</span>
                  )}
                </td>
                <td className="py-3 px-4 text-gray-400">{task.dueDate || '-'}</td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <Flag size={14} className={PRIORITY_COLORS[task.priority]} />
                    <span className="text-gray-500">{task.priority}</span>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <div className="flex flex-wrap gap-1">
                    {task.tags.map(tag => (
                      <span key={tag} className="px-1.5 py-0.5 bg-clickup-sidebar border border-clickup-border rounded text-[9px] text-gray-500">
                        {tag}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="py-3 px-4 text-right">
                  <MoreHorizontal size={14} className="text-gray-700 opacity-0 group-hover:opacity-100 inline" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
