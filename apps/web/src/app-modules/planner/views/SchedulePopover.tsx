import { useState } from 'react';
import { motion } from 'motion/react';
import { X, Video, Users, Link as LinkIcon, MapPin, AlignLeft, Calendar as CalendarIcon, Clock, Coffee } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/src/lib/utils';

interface SchedulePopoverProps {
  isOpen: boolean;
  onClose: () => void;
  initialDate?: string;
  initialStartTime?: string;
  initialEndTime?: string;
}

type ScheduleTab = 'Event' | 'Task' | 'Focus time' | 'OOO';

const SCHEDULE_TAB_LABEL_KEYS: Record<ScheduleTab, string> = {
  Event: 'planner.schedulePopover.tabs.event',
  Task: 'planner.schedulePopover.tabs.task',
  'Focus time': 'planner.schedulePopover.tabs.focusTime',
  OOO: 'planner.schedulePopover.tabs.ooo',
};

export const SchedulePopover = ({ isOpen, onClose, initialDate, initialStartTime, initialEndTime }: SchedulePopoverProps) => {
  const { t } = useTranslation('apps');
  const [activeTab, setActiveTab] = useState<ScheduleTab>('Event');

  if (!isOpen) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 10, scale: 0.95 }}
      className="fixed left-1/2 bottom-6 z-50 w-[400px] -translate-x-1/2 bg-app-bg border border-app-border rounded-xl shadow-2xl overflow-hidden"
    >
      <div className="flex items-center justify-between p-2 border-b border-app-border bg-app-surface-sidebar/50">
        <div className="flex items-center gap-1">
          {(['Event', 'Task', 'Focus time', 'OOO'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "app-text-control-sm rounded-md px-3 py-1.5 transition-colors",
                activeTab === tab ? "bg-app-bg text-app-ink shadow-sm" : "text-gray-500 hover:text-app-ink hover:bg-app-surface-hover"
              )}
            >
              {t(SCHEDULE_TAB_LABEL_KEYS[tab])}
            </button>
          ))}
        </div>
        <button
          onClick={onClose}
          aria-label={t('common:actions.close')}
          className="p-1.5 text-gray-500 hover:text-app-ink hover:bg-app-surface-hover rounded-md"
        >
          <X size={14} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        <input
          type="text"
          placeholder={t('planner.schedulePopover.titlePlaceholder')}
          className="app-text-body w-full rounded-md border border-app-border bg-transparent px-3 py-2 text-app-ink transition-colors focus:border-app-accent focus:outline-none"
          autoFocus
        />

        <div className="app-text-caption flex items-center gap-2 text-app-ink">
          <span>{initialDate || 'Apr 7, 2026'}</span>
          <span className="text-gray-500">{initialStartTime || '6:45 AM'}</span>
          <span className="text-gray-500">→</span>
          <span className="text-gray-500">{initialEndTime || '10:30 AM'}</span>
        </div>

        <button className="app-text-control flex w-full items-center justify-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar py-2 text-app-ink transition-colors hover:bg-app-surface-hover">
          <Video size={16} />
          <span>{t('planner.schedulePopover.addVideoCall')}</span>
        </button>

        <div className="space-y-3">
          <button className="app-text-body flex w-full items-center gap-3 text-left text-gray-500 transition-colors hover:text-app-ink">
            <Users size={16} />
            <span>{t('planner.schedulePopover.addParticipants')}</span>
          </button>
          <button className="app-text-body flex w-full items-center gap-3 text-left text-gray-500 transition-colors hover:text-app-ink">
            <LinkIcon size={16} />
            <span>{t('planner.schedulePopover.addTasksDocs')}</span>
          </button>
          <button className="app-text-body flex w-full items-center gap-3 text-left text-gray-500 transition-colors hover:text-app-ink">
            <MapPin size={16} />
            <span>{t('planner.schedulePopover.addLocation')}</span>
          </button>
          <button className="app-text-body flex w-full items-center gap-3 text-left text-gray-500 transition-colors hover:text-app-ink">
            <AlignLeft size={16} />
            <span>{t('planner.schedulePopover.addDescription')}</span>
          </button>
        </div>
      </div>

      <div className="p-3 border-t border-app-border bg-app-surface-sidebar/30 flex items-center gap-4">
        <button className="app-text-caption flex items-center gap-1.5 text-gray-500 hover:text-app-ink">
          <CalendarIcon size={14} />
        </button>
        <div className="app-text-caption flex items-center gap-3 text-gray-500">
          <button className="flex items-center gap-1.5 hover:text-app-ink">
            <div className="w-2 h-2 rounded-full bg-blue-500"></div>
            {t('planner.schedulePopover.defaultCalendar')}
          </button>
          <button className="flex items-center gap-1.5 hover:text-app-ink">
            <Clock size={14} />
            {t('planner.schedulePopover.busy')}
          </button>
          <button className="flex items-center gap-1.5 hover:text-app-ink">
            <Coffee size={14} />
          </button>
        </div>
        <div className="flex-1"></div>
        <button className="app-text-control-sm rounded-md bg-app-accent px-4 py-1.5 text-app-bg transition-colors hover:bg-opacity-90">
          {t('common:actions.save')}
        </button>
      </div>
    </motion.div>
  );
};
