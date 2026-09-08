import { cn } from '@/src/lib/utils';
import {
  AlignLeft,
  Calendar as CalendarIcon,
  Clock,
  Coffee,
  Link as LinkIcon,
  MapPin,
  Users,
  Video,
  X,
} from 'lucide-react';
import { domAnimation, LazyMotion, m } from 'motion/react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  buildSchedulePopoverDisplay,
  DEFAULT_SCHEDULE_POPOVER_TAB,
  SCHEDULE_POPOVER_TABS,
  type SchedulePopoverTabId,
} from './schedule-popover-model';

interface SchedulePopoverProps {
  isOpen: boolean;
  onClose: () => void;
  initialDate?: string;
  initialStartTime?: string;
  initialEndTime?: string;
}

export const SchedulePopover = ({
  isOpen,
  onClose,
  initialDate,
  initialStartTime,
  initialEndTime,
}: SchedulePopoverProps) => {
  const { t } = useTranslation('apps');
  const [activeTab, setActiveTab] = useState<SchedulePopoverTabId>(
    DEFAULT_SCHEDULE_POPOVER_TAB,
  );
  const { displayDate, displayStartTime, displayEndTime } =
    buildSchedulePopoverDisplay({
      initialDate,
      initialStartTime,
      initialEndTime,
    });

  if (!isOpen) return null;

  return (
    <LazyMotion features={domAnimation}>
      <m.div
        initial={{ opacity: 0, y: 10, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.95 }}
        className="fixed left-1/2 bottom-6 z-50 w-[400px] -translate-x-1/2 bg-app-bg border border-app-border rounded-xl shadow-2xl overflow-hidden"
      >
        <div className="flex items-center justify-between p-2 border-b border-app-border bg-app-surface-sidebar/50">
          <div className="flex items-center gap-1">
            {SCHEDULE_POPOVER_TABS.map((tab) => (
              <button
                type="button"
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'app-text-control-sm rounded-md px-3 py-1.5 transition-colors',
                  activeTab === tab.id
                    ? 'bg-app-bg text-app-ink shadow-sm'
                    : 'text-app-ink/55 hover:text-app-ink hover:bg-app-surface-hover',
                )}
              >
                {t(tab.labelKey)}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common:actions.close')}
            className="p-1.5 text-app-ink/55 hover:text-app-ink hover:bg-app-surface-hover rounded-md"
          >
            <X size={14} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <input
            type="text"
            aria-label={t('planner.schedulePopover.titlePlaceholder')}
            placeholder={t('planner.schedulePopover.titlePlaceholder')}
            className="app-text-body w-full rounded-md border border-app-border bg-transparent px-3 py-2 text-app-ink transition-colors focus:border-app-accent focus:outline-none"
          />

          <div className="app-text-caption flex items-center gap-2 text-app-ink">
            <span>{displayDate}</span>
            <span className="text-app-ink/55">{displayStartTime}</span>
            <span className="text-app-ink/55">→</span>
            <span className="text-app-ink/55">{displayEndTime}</span>
          </div>

          <button
            type="button"
            className="app-text-control flex w-full items-center justify-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar py-2 text-app-ink transition-colors hover:bg-app-surface-hover"
          >
            <Video size={16} />
            <span>{t('planner.schedulePopover.addVideoCall')}</span>
          </button>

          <div className="space-y-3">
            <button
              type="button"
              className="app-text-body flex w-full items-center gap-3 text-left text-app-ink/55 transition-colors hover:text-app-ink"
            >
              <Users size={16} />
              <span>{t('planner.schedulePopover.addParticipants')}</span>
            </button>
            <button
              type="button"
              className="app-text-body flex w-full items-center gap-3 text-left text-app-ink/55 transition-colors hover:text-app-ink"
            >
              <LinkIcon size={16} />
              <span>{t('planner.schedulePopover.addTasksDocs')}</span>
            </button>
            <button
              type="button"
              className="app-text-body flex w-full items-center gap-3 text-left text-app-ink/55 transition-colors hover:text-app-ink"
            >
              <MapPin size={16} />
              <span>{t('planner.schedulePopover.addLocation')}</span>
            </button>
            <button
              type="button"
              className="app-text-body flex w-full items-center gap-3 text-left text-app-ink/55 transition-colors hover:text-app-ink"
            >
              <AlignLeft size={16} />
              <span>{t('planner.schedulePopover.addDescription')}</span>
            </button>
          </div>
        </div>

        <div className="p-3 border-t border-app-border bg-app-surface-sidebar/30 flex items-center gap-4">
          <button
            type="button"
            className="app-text-caption flex items-center gap-1.5 text-app-ink/55 hover:text-app-ink"
          >
            <CalendarIcon size={14} />
          </button>
          <div className="app-text-caption flex items-center gap-3 text-app-ink/55">
            <button
              type="button"
              className="flex items-center gap-1.5 hover:text-app-ink"
            >
              <div className="size-2 rounded-full bg-app-info"></div>
              {t('planner.schedulePopover.defaultCalendar')}
            </button>
            <button
              type="button"
              className="flex items-center gap-1.5 hover:text-app-ink"
            >
              <Clock size={14} />
              {t('planner.schedulePopover.busy')}
            </button>
            <button
              type="button"
              className="flex items-center gap-1.5 hover:text-app-ink"
            >
              <Coffee size={14} />
            </button>
          </div>
          <div className="flex-1"></div>
          <button
            type="button"
            className="app-text-control-sm rounded-md bg-app-accent px-4 py-1.5 text-app-accent-fg transition-colors hover:bg-opacity-90"
          >
            {t('common:actions.save')}
          </button>
        </div>
      </m.div>
    </LazyMotion>
  );
};
