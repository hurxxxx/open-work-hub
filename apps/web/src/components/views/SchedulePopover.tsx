import { useState } from 'react';
import { motion } from 'motion/react';
import { X, Video, Users, Link as LinkIcon, MapPin, AlignLeft, Calendar as CalendarIcon, Clock, Coffee } from 'lucide-react';
import { cn } from '@/src/lib/utils';

interface SchedulePopoverProps {
  isOpen: boolean;
  onClose: () => void;
  position: { top: number; left: number };
  initialDate?: string;
  initialStartTime?: string;
  initialEndTime?: string;
}

export const SchedulePopover = ({ isOpen, onClose, position, initialDate, initialStartTime, initialEndTime }: SchedulePopoverProps) => {
  const [activeTab, setActiveTab] = useState<'Event' | 'Task' | 'Focus time' | 'OOO'>('Event');

  if (!isOpen) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 10, scale: 0.95 }}
      style={{ top: position.top, left: position.left }}
      className="absolute z-50 w-[400px] bg-clickup-bg border border-clickup-border rounded-xl shadow-2xl overflow-hidden"
    >
      <div className="flex items-center justify-between p-2 border-b border-clickup-border bg-clickup-sidebar/50">
        <div className="flex items-center gap-1">
          {(['Event', 'Task', 'Focus time', 'OOO'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
                activeTab === tab ? "bg-clickup-bg text-clickup-text shadow-sm" : "text-gray-500 hover:text-clickup-text hover:bg-clickup-hover"
              )}
            >
              {tab}
            </button>
          ))}
        </div>
        <button onClick={onClose} className="p-1.5 text-gray-500 hover:text-clickup-text hover:bg-clickup-hover rounded-md">
          <X size={14} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        <input
          type="text"
          placeholder="Add title, @ for people, @@ for tasks"
          className="w-full bg-transparent border border-clickup-border rounded-md px-3 py-2 text-sm text-clickup-text focus:outline-none focus:border-clickup-purple transition-colors"
          autoFocus
        />

        <div className="flex items-center gap-2 text-xs text-clickup-text">
          <span>{initialDate || 'Apr 7, 2026'}</span>
          <span className="text-gray-500">{initialStartTime || '6:45 AM'}</span>
          <span className="text-gray-500">→</span>
          <span className="text-gray-500">{initialEndTime || '10:30 AM'}</span>
        </div>

        <button className="w-full flex items-center justify-center gap-2 py-2 bg-clickup-sidebar hover:bg-clickup-hover border border-clickup-border rounded-md text-sm text-clickup-text transition-colors">
          <Video size={16} />
          <span>Add video call</span>
        </button>

        <div className="space-y-3">
          <button className="flex items-center gap-3 text-sm text-gray-500 hover:text-clickup-text transition-colors w-full text-left">
            <Users size={16} />
            <span>Add participants</span>
          </button>
          <button className="flex items-center gap-3 text-sm text-gray-500 hover:text-clickup-text transition-colors w-full text-left">
            <LinkIcon size={16} />
            <span>Add ClickUp tasks and docs</span>
          </button>
          <button className="flex items-center gap-3 text-sm text-gray-500 hover:text-clickup-text transition-colors w-full text-left">
            <MapPin size={16} />
            <span>Add location or room</span>
          </button>
          <button className="flex items-center gap-3 text-sm text-gray-500 hover:text-clickup-text transition-colors w-full text-left">
            <AlignLeft size={16} />
            <span>Add description</span>
          </button>
        </div>
      </div>

      <div className="p-3 border-t border-clickup-border bg-clickup-sidebar/30 flex items-center gap-4">
        <button className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-clickup-text">
          <CalendarIcon size={14} />
        </button>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <button className="flex items-center gap-1.5 hover:text-clickup-text">
            <div className="w-2 h-2 rounded-full bg-blue-500"></div>
            Default
          </button>
          <button className="flex items-center gap-1.5 hover:text-clickup-text">
            <Clock size={14} />
            Busy
          </button>
          <button className="flex items-center gap-1.5 hover:text-clickup-text">
            <Coffee size={14} />
          </button>
        </div>
        <div className="flex-1"></div>
        <button className="px-4 py-1.5 bg-clickup-purple text-white text-xs font-medium rounded-md hover:bg-opacity-90 transition-colors">
          Save
        </button>
      </div>
    </motion.div>
  );
};
