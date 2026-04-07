import {
  Eye,
  Share2,
  MoreHorizontal,
  ChevronRight,
  Plus,
  Flag,
  Paperclip,
  MessageCircle,
  Clock,
} from 'lucide-react';
import { DetailDrawer, Button, Badge } from '@aidoo/ui';
import { cn } from '@/src/lib/utils';
import { Task } from '@/src/types';
import { STATUS_COLORS, PRIORITY_COLORS } from '@/src/mockData';

/** Map STATUS_COLORS bg classes to Badge tones */
const STATUS_TONE: Record<string, 'neutral' | 'accent' | 'success' | 'warning' | 'danger'> = {
  'TO DO': 'neutral',
  'IN PROGRESS': 'accent',
  'REVIEW': 'warning',
  'DONE': 'success',
};

export const TaskDetail = ({ task, onClose }: { task: Task; onClose: () => void }) => {
  return (
    <DetailDrawer
      open={true}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title={task.name}
      description={
        <div className="flex items-center gap-2 text-xs text-clickup-text/60">
          <span>Spaces</span>
          <ChevronRight size={12} />
          <span>Team Space</span>
          <ChevronRight size={12} />
          <span>Project 1</span>
        </div>
      }
      actions={
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon"><Share2 size={18} /></Button>
          <Button variant="ghost" size="icon"><MoreHorizontal size={18} /></Button>
        </div>
      }
    >
      <div className="space-y-8">
        {/* Status & Watch */}
        <div className="flex items-center gap-4">
          <Badge tone={STATUS_TONE[task.status] ?? 'neutral'}>{task.status}</Badge>
          <button className="flex items-center gap-2 text-clickup-text/60 hover:text-clickup-text cursor-pointer transition-colors">
            <Eye size={16} />
            <span className="text-xs">Watch</span>
          </button>
        </div>

        {/* Fields */}
        <div className="grid grid-cols-2 gap-8">
          <div className="space-y-6">
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-clickup-text/50">Assignees</label>
              <div className="flex items-center gap-2">
                {task.assignee ? (
                  <div className="flex items-center gap-2 px-2 py-1 bg-clickup-sidebar border border-clickup-border rounded-full">
                    <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-[10px] font-bold text-white">{task.assignee.avatar}</div>
                    <span className="text-xs text-clickup-text/70">{task.assignee.name}</span>
                  </div>
                ) : (
                  <Button variant="ghost" size="icon" className="border border-dashed border-clickup-border rounded-full">
                    <Plus size={16} />
                  </Button>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-clickup-text/50">Dates</label>
              <div className="flex items-center gap-4">
                <div className="flex flex-col">
                  <span className="text-[10px] text-clickup-text/40">Start Date</span>
                  <span className="text-xs text-clickup-text/60">Not set</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] text-clickup-text/40">Due Date</span>
                  <span className="text-xs text-clickup-text">{task.dueDate || 'Not set'}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="space-y-6">
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-clickup-text/50">Priority</label>
              <div className="flex items-center gap-2">
                <Flag size={16} className={PRIORITY_COLORS[task.priority]} />
                <span className="text-xs text-clickup-text/70">{task.priority}</span>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-clickup-text/50">Tags</label>
              <div className="flex flex-wrap gap-1">
                {task.tags.map(tag => (
                  <Badge key={tag} tone="neutral">{tag}</Badge>
                ))}
                <Button variant="ghost" size="icon"><Plus size={14} /></Button>
              </div>
            </div>
          </div>
        </div>

        {/* Description */}
        <div className="space-y-4">
          <div className="flex items-center gap-4 border-b border-clickup-border">
            <button className="text-xs font-bold text-clickup-text border-b-2 border-clickup-purple pb-2">Description</button>
            <button className="text-xs font-bold text-clickup-text/50 hover:text-clickup-text pb-2">Custom Fields</button>
            <button className="text-xs font-bold text-clickup-text/50 hover:text-clickup-text pb-2">Attachments</button>
          </div>
          <div className="p-4 bg-clickup-sidebar rounded-xl border border-clickup-border min-h-[150px] text-sm text-clickup-text/60 leading-relaxed">
            {task.description || 'Add a description...'}
          </div>
        </div>

        {/* Activity */}
        <div className="space-y-4">
          <h3 className="text-sm font-bold text-clickup-text flex items-center gap-2">
            <MessageCircle size={16} className="text-clickup-text/50" />
            Activity
          </h3>
          <div className="space-y-6">
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-clickup-purple flex items-center justify-center text-xs font-bold text-white">GH</div>
              <div className="flex-1 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-clickup-text">Gunwoo Hur</span>
                  <span className="text-[10px] text-clickup-text/40">2 hours ago</span>
                </div>
                <div className="p-3 bg-clickup-sidebar border border-clickup-border rounded-lg text-xs text-clickup-text/60">
                  Updated the status to <span className="text-clickup-purple font-bold">In Progress</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Comment Input */}
        <div className="flex items-center gap-3 pt-4 border-t border-clickup-border">
          <div className="w-8 h-8 rounded-full bg-clickup-purple flex items-center justify-center text-xs font-bold text-white">GH</div>
          <div className="flex-1 relative">
            <input
              type="text"
              placeholder="Write a comment..."
              className="w-full bg-clickup-bg border border-clickup-border rounded-full px-4 py-2 text-xs text-clickup-text focus:outline-none focus:border-clickup-purple transition-all"
            />
            <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2 text-clickup-text/50">
              <Paperclip size={14} className="cursor-pointer hover:text-clickup-text" />
              <Clock size={14} className="cursor-pointer hover:text-clickup-text" />
            </div>
          </div>
        </div>
      </div>
    </DetailDrawer>
  );
};
