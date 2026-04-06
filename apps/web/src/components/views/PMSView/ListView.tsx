import { 
  Activity, 
  Plus, 
  Layout, 
  ChevronDown, 
  Circle, 
  User2 
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { Task } from '@/src/types';
import { STATUS_COLORS, PRIORITY_COLORS } from '@/src/mockData';

export const ListView = ({ tasks, onSelectTask }: { tasks: Task[], onSelectTask: (t: Task) => void }) => {
  const groups = ['TO DO', 'IN PROGRESS', 'REVIEW', 'DONE'] as const;

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4 text-xs font-medium text-gray-500 bg-clickup-sidebar/30 p-2 rounded-md border border-clickup-border">
        <button className="flex items-center gap-1 px-2 py-1 bg-clickup-purple/10 text-clickup-purple rounded">
          <Activity size={14} />
          Group: Status
        </button>
        <button className="flex items-center gap-1 px-2 py-1 hover:bg-clickup-hover rounded">
          <Plus size={14} />
          Subtasks
        </button>
        <button className="flex items-center gap-1 px-2 py-1 hover:bg-clickup-hover rounded">
          <Layout size={14} />
          Columns
        </button>
      </div>

      {groups.map(status => {
        const statusTasks = tasks.filter(t => t.status === status);
        
        return (
          <div key={status} className="space-y-2">
            <div className="flex items-center gap-2 px-2 py-1">
              <ChevronDown size={14} className="text-gray-500" />
              <div className={cn("px-2 py-0.5 rounded text-[10px] font-bold text-white", STATUS_COLORS[status])}>
                {status}
              </div>
              <span className="text-[10px] text-gray-600 font-bold">{statusTasks.length}</span>
            </div>

            <div className="border border-clickup-border rounded-lg overflow-hidden bg-clickup-sidebar/20">
              <table className="w-full text-left text-[11px]">
                <thead>
                  <tr className="bg-clickup-sidebar/50 border-b border-clickup-border text-gray-500">
                    <th className="w-10 py-2 px-4"></th>
                    <th className="py-2 px-4 font-medium w-1/3">NAME</th>
                    <th className="py-2 px-4 font-medium">ASSIGNEE</th>
                    <th className="py-2 px-4 font-medium">DUE DATE</th>
                    <th className="py-2 px-4 font-medium">PRIORITY</th>
                    <th className="py-2 px-4 font-medium">STATUS</th>
                    <th className="py-2 px-4 font-medium">COMMENTS</th>
                    <th className="py-2 px-4 font-medium text-right"><Plus size={14} className="inline cursor-pointer" /></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-clickup-border">
                  {statusTasks.map(task => (
                    <tr 
                      key={task.id} 
                      onClick={() => onSelectTask(task)}
                      className="hover:bg-clickup-hover transition-colors group cursor-pointer"
                    >
                      <td className="py-2 px-4">
                        <Circle size={14} className="text-gray-600" />
                      </td>
                      <td className="py-2 px-4">
                        <span className="text-clickup-text font-medium">{task.name}</span>
                      </td>
                      <td className="py-2 px-4">
                        {task.assignee ? (
                          <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-[8px] font-bold text-white border border-clickup-border">
                            {task.assignee.avatar}
                          </div>
                        ) : (
                          <User2 size={14} className="text-gray-700" />
                        )}
                      </td>
                      <td className="py-2 px-4">
                        <span className="text-gray-500">{task.dueDate || 'Not set'}</span>
                      </td>
                      <td className="py-2 px-4">
                        <span className={cn("text-[10px] font-bold", PRIORITY_COLORS[task.priority])}>{task.priority}</span>
                      </td>
                      <td className="py-2 px-4">
                        <div className={cn("px-2 py-0.5 rounded text-[9px] font-bold text-white inline-block", STATUS_COLORS[task.status])}>
                          {task.status}
                        </div>
                      </td>
                      <td className="py-2 px-4">
                        <span className="text-gray-600">0</span>
                      </td>
                      <td className="py-2 px-4 text-right">
                        <Plus size={14} className="inline opacity-0 group-hover:opacity-100 text-gray-500 transition-opacity" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
};
