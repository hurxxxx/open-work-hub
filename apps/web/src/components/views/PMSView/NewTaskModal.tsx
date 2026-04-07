import {
  Layout,
  ChevronDown,
  Circle,
  FileText,
  Sparkles,
  User,
  Calendar,
  Flag,
  Tag,
  MoreHorizontal,
  Plus,
  LayoutTemplate,
  Paperclip,
  Bell,
} from 'lucide-react';
import { Dialog, Button, Badge } from '@aidoo/ui';

export const NewTaskModal = ({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) => {
  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title="New Task"
      maxWidth="max-w-3xl"
      actions={
        <div className="flex items-center justify-between w-full">
          <Button variant="secondary" className="gap-2">
            <LayoutTemplate size={16} className="text-clickup-text/50" />
            Templates
          </Button>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-4 text-clickup-text/50">
              <Paperclip size={20} className="cursor-pointer hover:text-clickup-text transition-colors" />
              <div className="flex items-center gap-1 cursor-pointer hover:text-clickup-text transition-colors">
                <Bell size={20} />
                <span className="text-xs font-bold">1</span>
              </div>
            </div>
            <div className="flex items-center">
              <Button variant="primary" onClick={onClose} className="rounded-r-none">
                Create Task
              </Button>
              <Button variant="primary" size="icon" className="rounded-l-none border-l border-white/20">
                <ChevronDown size={20} />
              </Button>
            </div>
          </div>
        </div>
      }
    >
      <div className="space-y-6 text-clickup-text">
        {/* Selectors */}
        <div className="flex items-center gap-3">
          <Button variant="secondary" className="gap-2">
            <Layout size={16} className="text-clickup-text/50" />
            Project 1
            <ChevronDown size={14} className="text-clickup-text/50" />
          </Button>
          <Button variant="secondary" className="gap-2">
            <Circle size={16} className="text-clickup-text/50" />
            Task
            <ChevronDown size={14} className="text-clickup-text/50" />
          </Button>
        </div>

        {/* Task Name Input */}
        <input
          type="text"
          placeholder="Task Name or type '/' for commands"
          className="w-full bg-transparent text-xl font-medium text-clickup-text placeholder:text-clickup-text/40 focus:outline-none border border-clickup-border rounded-lg px-4 py-3 focus:border-clickup-purple transition-all"
          autoFocus
        />

        {/* Description & AI */}
        <div className="space-y-4">
          <button className="flex items-center gap-2 text-clickup-text/50 hover:text-clickup-text transition-colors text-sm">
            <FileText size={18} />
            <span>Add description</span>
          </button>
          <button className="flex items-center gap-2 text-clickup-purple hover:opacity-80 transition-opacity text-sm font-medium">
            <Sparkles size={18} />
            <span>Write with AI</span>
          </button>
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral" className="uppercase tracking-wider font-bold">TO DO</Badge>
          <Button variant="secondary" size="dense" className="gap-2">
            <User size={16} />
            Assignee
          </Button>
          <Button variant="secondary" size="dense" className="gap-2">
            <Calendar size={16} />
            Due date
          </Button>
          <Button variant="secondary" size="dense" className="gap-2">
            <Flag size={16} />
            Priority
          </Button>
          <Button variant="secondary" size="dense" className="gap-2">
            <Tag size={16} />
            Tags
          </Button>
          <Button variant="ghost" size="icon">
            <MoreHorizontal size={16} />
          </Button>
        </div>

        {/* Fields Section */}
        <div className="space-y-3 pt-4">
          <h4 className="text-xs font-bold text-clickup-text/50 uppercase tracking-widest">Fields</h4>
          <Button variant="secondary" className="gap-2">
            <Plus size={16} />
            Create new field
          </Button>
        </div>
      </div>
    </Dialog>
  );
};
