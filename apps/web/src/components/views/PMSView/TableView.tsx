import { MessageSquare, Flag, MoreHorizontal } from 'lucide-react';
import { Badge, Button } from '@aidoo/ui';
import { Task } from '@/src/types';
import { PRIORITY_COLORS } from '@/src/mockData';

const STATUS_TONE: Record<string, 'neutral' | 'accent' | 'success' | 'warning' | 'danger'> = {
  'TO DO': 'neutral',
  'IN PROGRESS': 'accent',
  'REVIEW': 'warning',
  'DONE': 'success',
};

export const TableView = ({
  tasks,
  onSelectTask,
}: {
  tasks: Task[];
  onSelectTask: (t: Task) => void;
}) => {
  return (
    <div className="overflow-hidden rounded-lg border border-clickup-border bg-clickup-card">
      <div className="overflow-x-auto custom-scrollbar">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-clickup-sidebar/50 border-b border-clickup-border text-clickup-text/50 uppercase tracking-wider font-bold">
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
                <td className="py-3 px-4 text-clickup-text/40">{i + 1}</td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <span className="text-clickup-text font-medium">{task.name}</span>
                    {task.comments > 0 && (
                      <div className="flex items-center gap-1 text-clickup-text/40">
                        <MessageSquare size={12} />
                        <span className="text-[10px]">{task.comments}</span>
                      </div>
                    )}
                  </div>
                </td>
                <td className="py-3 px-4">
                  <Badge tone={STATUS_TONE[task.status] ?? 'neutral'}>{task.status}</Badge>
                </td>
                <td className="py-3 px-4">
                  {task.assignee ? (
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center text-[10px] font-bold text-white border border-clickup-border">
                        {task.assignee.avatar}
                      </div>
                      <span className="text-clickup-text/60">{task.assignee.name}</span>
                    </div>
                  ) : (
                    <span className="text-clickup-text/30">-</span>
                  )}
                </td>
                <td className="py-3 px-4 text-clickup-text/60">{task.dueDate || '-'}</td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <Flag size={14} className={PRIORITY_COLORS[task.priority]} />
                    <span className="text-clickup-text/50">{task.priority}</span>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <div className="flex flex-wrap gap-1">
                    {task.tags.map((tag) => (
                      <Badge key={tag} tone="neutral">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </td>
                <td className="py-3 px-4 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="opacity-0 group-hover:opacity-100"
                  >
                    <MoreHorizontal size={14} />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
