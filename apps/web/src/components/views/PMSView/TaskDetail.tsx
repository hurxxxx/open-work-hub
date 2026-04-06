import { motion } from 'motion/react';
import { 
  Eye, 
  Share2, 
  MoreHorizontal, 
  X, 
  ChevronRight, 
  Plus, 
  Flag, 
  Tag, 
  Paperclip, 
  MessageCircle, 
  Clock, 
  CheckSquare, 
  Hash, 
  ArrowUpRight, 
  Link as LinkIcon 
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { Task } from '@/src/types';
import { STATUS_COLORS, PRIORITY_COLORS } from '@/src/mockData';

export const TaskDetail = ({ task, onClose }: { task: Task, onClose: () => void }) => {
  return (
    <motion.div 
      initial={{ x: '100%' }}
      animate={{ x: 0 }}
      exit={{ x: '100%' }}
      className="fixed top-0 right-0 w-[600px] h-full bg-clickup-bg border-l border-clickup-border z-50 shadow-2xl flex flex-col"
    >
      <div className="h-14 border-b border-clickup-border flex items-center justify-between px-6">
        <div className="flex items-center gap-4">
          <div className={cn("px-2 py-0.5 rounded text-[10px] font-bold text-white", STATUS_COLORS[task.status])}>
            {task.status}
          </div>
          <div className="flex items-center gap-2 text-gray-500 hover:text-white cursor-pointer transition-colors">
            <Eye size={16} />
            <span className="text-xs">Watch</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="p-2 hover:bg-clickup-hover rounded text-gray-400"><Share2 size={18} /></button>
          <button className="p-2 hover:bg-clickup-hover rounded text-gray-400"><MoreHorizontal size={18} /></button>
          <button onClick={onClose} className="p-2 hover:bg-clickup-hover rounded text-gray-400"><X size={18} /></button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8 space-y-8 custom-scrollbar">
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span>Spaces</span>
            <ChevronRight size={12} />
            <span>Team Space</span>
            <ChevronRight size={12} />
            <span>Project 1</span>
          </div>
          <h1 className="text-2xl font-bold text-clickup-text">{task.name}</h1>
        </div>

        <div className="grid grid-cols-2 gap-8">
          <div className="space-y-6">
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-gray-500">Assignees</label>
              <div className="flex items-center gap-2">
                {task.assignee ? (
                  <div className="flex items-center gap-2 px-2 py-1 bg-clickup-sidebar border border-clickup-border rounded-full">
                    <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-[10px] font-bold text-white">{task.assignee.avatar}</div>
                    <span className="text-xs text-gray-300">{task.assignee.name}</span>
                  </div>
                ) : (
                  <button className="p-1 border border-dashed border-gray-600 rounded-full text-gray-600 hover:text-gray-400 hover:border-gray-400 transition-all">
                    <Plus size={16} />
                  </button>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-gray-500">Dates</label>
              <div className="flex items-center gap-4">
                <div className="flex flex-col">
                  <span className="text-[10px] text-gray-600">Start Date</span>
                  <span className="text-xs text-gray-400">Not set</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] text-gray-600">Due Date</span>
                  <span className="text-xs text-clickup-text">{task.dueDate || 'Not set'}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="space-y-6">
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-gray-500">Priority</label>
              <div className="flex items-center gap-2">
                <Flag size={16} className={PRIORITY_COLORS[task.priority]} />
                <span className="text-xs text-gray-300">{task.priority}</span>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-gray-500">Tags</label>
              <div className="flex flex-wrap gap-1">
                {task.tags.map(tag => (
                  <span key={tag} className="px-2 py-0.5 bg-clickup-sidebar border border-clickup-border rounded text-[10px] text-gray-400">
                    {tag}
                  </span>
                ))}
                <button className="p-0.5 text-gray-600 hover:text-gray-400"><Plus size={14} /></button>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="flex items-center gap-4 border-b border-clickup-border">
            <button className="text-xs font-bold text-clickup-text border-b-2 border-clickup-purple pb-2">Description</button>
            <button className="text-xs font-bold text-gray-500 hover:text-clickup-text pb-2">Custom Fields</button>
            <button className="text-xs font-bold text-gray-500 hover:text-clickup-text pb-2">Attachments</button>
          </div>
          <div className="p-4 bg-clickup-sidebar rounded-xl border border-clickup-border min-h-[150px] text-sm text-gray-400 leading-relaxed">
            {task.description || 'Add a description...'}
          </div>
        </div>

        <div className="space-y-4">
          <h3 className="text-sm font-bold text-clickup-text flex items-center gap-2">
            <MessageCircle size={16} className="text-gray-500" />
            Activity
          </h3>
          <div className="space-y-6">
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-clickup-purple flex items-center justify-center text-xs font-bold text-white">GH</div>
              <div className="flex-1 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-clickup-text">Gunwoo Hur</span>
                  <span className="text-[10px] text-gray-600">2 hours ago</span>
                </div>
                <div className="p-3 bg-clickup-sidebar border border-clickup-border rounded-lg text-xs text-gray-400">
                  Updated the status to <span className="text-clickup-purple font-bold">In Progress</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="h-16 border-t border-clickup-border bg-clickup-sidebar/30 p-4 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-clickup-purple flex items-center justify-center text-xs font-bold text-white">GH</div>
        <div className="flex-1 relative">
          <input 
            type="text" 
            placeholder="Write a comment..." 
            className="w-full bg-clickup-bg border border-clickup-border rounded-full px-4 py-2 text-xs text-clickup-text focus:outline-none focus:border-clickup-purple transition-all"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2 text-gray-500">
            <Paperclip size={14} className="cursor-pointer hover:text-clickup-text" />
            <Clock size={14} className="cursor-pointer hover:text-clickup-text" />
          </div>
        </div>
      </div>
    </motion.div>
  );
};
