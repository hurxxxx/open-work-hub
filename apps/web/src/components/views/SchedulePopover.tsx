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
                "app-text-control-sm rounded-md px-3 py-1.5 transition-colors",
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
          className="app-text-body w-full rounded-md border border-clickup-border bg-transparent px-3 py-2 text-clickup-text transition-colors focus:border-clickup-purple focus:outline-none"
          autoFocus
        />

        <div className="app-text-caption flex items-center gap-2 text-clickup-text">
          <span>{initialDate || 'Apr 7, 2026'}</span>
          <span className="text-gray-500">{initialStartTime || '6:45 AM'}</span>
          <span className="text-gray-500">→</span>
          <span className="text-gray-500">{initialEndTime || '10:30 AM'}</span>
        </div>

        <button className="app-text-control flex w-full items-center justify-center gap-2 rounded-md border border-clickup-border bg-clickup-sidebar py-2 text-clickup-text transition-colors hover:bg-clickup-hover">
          <Video size={16} />
          <span>Add video call</span>
        </button>

        <div className="space-y-3">
          <button className="app-text-body flex w-full items-center gap-3 text-left text-gray-500 transition-colors hover:text-clickup-text">
            <Users size={16} />
            <span>Add participants</span>
          </button>
          <button className="app-text-body flex w-full items-center gap-3 text-left text-gray-500 transition-colors hover:text-clickup-text">
            <LinkIcon size={16} />
            <span>Add ClickUp tasks and docs</span>
          </button>
          <button className="app-text-body flex w-full items-center gap-3 text-left text-gray-500 transition-colors hover:text-clickup-text">
            <MapPin size={16} />
            <span>Add location or room</span>
          </button>
          <button className="app-text-body flex w-full items-center gap-3 text-left text-gray-500 transition-colors hover:text-clickup-text">
            <AlignLeft size={16} />
            <span>Add description</span>
          </button>
        </div>
      </div>

      <div className="p-3 border-t border-clickup-border bg-clickup-sidebar/30 flex items-center gap-4">
        <button className="app-text-caption flex items-center gap-1.5 text-gray-500 hover:text-clickup-text">
          <CalendarIcon size={14} />
        </button>
        <div className="app-text-caption flex items-center gap-3 text-gray-500">
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
        <button className="app-text-control-sm rounded-md bg-clickup-purple px-4 py-1.5 text-clickup-bg transition-colors hover:bg-opacity-90">
          Save
        </button>
      </div>
    </motion.div>
  );
};
