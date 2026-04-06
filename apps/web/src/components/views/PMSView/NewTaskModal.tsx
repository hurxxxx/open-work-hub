import { motion } from 'motion/react';
import { 
  Minimize2, 
  X, 
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
  Bell 
} from 'lucide-react';
import { cn } from '@/src/lib/utils';

export const NewTaskModal = ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="bg-clickup-bg border border-clickup-border rounded-xl shadow-2xl w-full max-w-3xl overflow-hidden flex flex-col"
      >
        {/* Header Tabs */}
        <div className="flex items-center justify-between px-6 pt-4 border-b border-clickup-border">
          <div className="flex items-center gap-6">
            {['Task', 'Doc', 'Reminder', 'Whiteboard', 'Dashboard'].map((tab, i) => (
              <button 
                key={tab} 
                className={cn(
                  "pb-3 text-sm font-medium transition-all relative",
                  i === 0 ? "text-clickup-text" : "text-gray-500 hover:text-clickup-text"
                )}
              >
                {tab}
                {i === 0 && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-clickup-text" />}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 pb-3">
            <button className="p-1.5 text-gray-500 hover:bg-clickup-hover rounded-md transition-colors">
              <Minimize2 size={18} />
            </button>
            <button 
              onClick={onClose}
              className="p-1.5 text-gray-500 hover:bg-clickup-hover rounded-md transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Content Area */}
        <div className="p-6 space-y-6 overflow-y-auto max-h-[70vh] custom-scrollbar text-clickup-text">
          {/* Selectors */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-clickup-sidebar border border-clickup-border rounded-md text-sm text-clickup-text cursor-pointer hover:bg-clickup-hover transition-colors">
              <Layout size={16} className="text-gray-500" />
              <span>Project 1</span>
              <ChevronDown size={14} className="text-gray-500" />
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-clickup-sidebar border border-clickup-border rounded-md text-sm text-clickup-text cursor-pointer hover:bg-clickup-hover transition-colors">
              <Circle size={16} className="text-gray-500" />
              <span>Task</span>
              <ChevronDown size={14} className="text-gray-500" />
            </div>
          </div>

          {/* Task Name Input */}
          <div className="relative">
            <input 
              type="text" 
              placeholder="Task Name or type '/' for commands" 
              className="w-full bg-transparent text-xl font-medium text-clickup-text placeholder:text-gray-600 focus:outline-none border border-clickup-border rounded-lg px-4 py-3 focus:border-clickup-purple transition-all"
              autoFocus
            />
          </div>

          {/* Description & AI */}
          <div className="space-y-4">
            <button className="flex items-center gap-2 text-gray-500 hover:text-clickup-text transition-colors text-sm">
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
            <button className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded text-xs font-bold uppercase tracking-wider hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
              TO DO
            </button>
            <button className="flex items-center gap-2 px-3 py-1.5 border border-clickup-border rounded text-sm text-gray-500 hover:bg-clickup-hover transition-colors">
              <User size={16} />
              <span>Assignee</span>
            </button>
            <button className="flex items-center gap-2 px-3 py-1.5 border border-clickup-border rounded text-sm text-gray-500 hover:bg-clickup-hover transition-colors">
              <Calendar size={16} />
              <span>Due date</span>
            </button>
            <button className="flex items-center gap-2 px-3 py-1.5 border border-clickup-border rounded text-sm text-gray-500 hover:bg-clickup-hover transition-colors">
              <Flag size={16} />
              <span>Priority</span>
            </button>
            <button className="flex items-center gap-2 px-3 py-1.5 border border-clickup-border rounded text-sm text-gray-500 hover:bg-clickup-hover transition-colors">
              <Tag size={16} />
              <span>Tags</span>
            </button>
            <button className="p-1.5 border border-clickup-border rounded text-gray-500 hover:bg-clickup-hover transition-colors">
              <MoreHorizontal size={16} />
            </button>
          </div>

          {/* Fields Section */}
          <div className="space-y-3 pt-4">
            <h4 className="text-xs font-bold text-gray-500 uppercase tracking-widest">Fields</h4>
            <button className="flex items-center gap-2 px-4 py-2 bg-clickup-sidebar border border-clickup-border rounded-md text-sm text-clickup-text hover:bg-clickup-hover transition-colors">
              <Plus size={16} />
              <span>Create new field</span>
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-clickup-border flex items-center justify-between bg-clickup-sidebar/30">
          <button className="flex items-center gap-2 px-4 py-2 border border-clickup-border rounded-md text-sm text-clickup-text hover:bg-clickup-hover transition-colors">
            <LayoutTemplate size={16} className="text-gray-500" />
            <span>Templates</span>
          </button>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-4 text-gray-500">
              <Paperclip size={20} className="cursor-pointer hover:text-clickup-text transition-colors" />
              <div className="flex items-center gap-1 cursor-pointer hover:text-clickup-text transition-colors">
                <Bell size={20} />
                <span className="text-xs font-bold">1</span>
              </div>
            </div>
            <div className="flex items-center">
              <button 
                onClick={onClose}
                className="px-6 py-2 bg-clickup-purple text-white rounded-l-md font-bold hover:opacity-90 transition-opacity"
              >
                Create Task
              </button>
              <button className="px-2 py-2 bg-clickup-purple text-white rounded-r-md border-l border-white/20 hover:opacity-90 transition-opacity">
                <ChevronDown size={20} />
              </button>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
};
