import { formatDateOnly } from '@/src/platform/time/time-utils';

export type SchedulePopoverTabId = 'Event' | 'Task' | 'Focus time' | 'OOO';

export interface SchedulePopoverTab {
  id: SchedulePopoverTabId;
  labelKey: string;
}

export interface BuildSchedulePopoverDisplayInput {
  initialDate?: string;
  initialStartTime?: string;
  initialEndTime?: string;
}

export interface SchedulePopoverDisplay {
  displayDate: string;
  displayStartTime: string;
  displayEndTime: string;
}

export const SCHEDULE_POPOVER_TABS = [
  {
    id: 'Event',
    labelKey: 'planner.schedulePopover.tabs.event',
  },
  {
    id: 'Task',
    labelKey: 'planner.schedulePopover.tabs.task',
  },
  {
    id: 'Focus time',
    labelKey: 'planner.schedulePopover.tabs.focusTime',
  },
  {
    id: 'OOO',
    labelKey: 'planner.schedulePopover.tabs.ooo',
  },
] as const satisfies readonly SchedulePopoverTab[];

export const DEFAULT_SCHEDULE_POPOVER_TAB =
  'Event' satisfies SchedulePopoverTabId;

const FALLBACK_DATE = '2026-04-07';
const FALLBACK_START_TIME = '6:45 AM';
const FALLBACK_END_TIME = '10:30 AM';

export function buildSchedulePopoverDisplay({
  initialDate,
  initialStartTime,
  initialEndTime,
}: BuildSchedulePopoverDisplayInput): SchedulePopoverDisplay {
  return {
    displayDate: initialDate || formatDateOnly(FALLBACK_DATE),
    displayStartTime: initialStartTime || FALLBACK_START_TIME,
    displayEndTime: initialEndTime || FALLBACK_END_TIME,
  };
}
