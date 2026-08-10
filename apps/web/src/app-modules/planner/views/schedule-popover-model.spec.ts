import { beforeEach, describe, expect, it } from 'vitest';

import { DATE_FORMAT_STORAGE_KEY } from '@/src/platform/time/time-utils';

import {
  buildSchedulePopoverDisplay,
  DEFAULT_SCHEDULE_POPOVER_TAB,
  SCHEDULE_POPOVER_TABS,
} from './schedule-popover-model';

describe('schedule popover model', () => {
  beforeEach(() => {
    window.localStorage.removeItem(DATE_FORMAT_STORAGE_KEY);
  });

  it('builds default-safe display strings when initial values are missing', () => {
    window.localStorage.setItem(DATE_FORMAT_STORAGE_KEY, 'iso');

    expect(buildSchedulePopoverDisplay({})).toEqual({
      displayDate: '2026-04-07',
      displayStartTime: '6:45 AM',
      displayEndTime: '10:30 AM',
    });
  });

  it('uses provided display values when initial values are present', () => {
    expect(
      buildSchedulePopoverDisplay({
        initialDate: '2026-05-31',
        initialStartTime: '9:00 AM',
        initialEndTime: '9:30 AM',
      }),
    ).toEqual({
      displayDate: '2026-05-31',
      displayStartTime: '9:00 AM',
      displayEndTime: '9:30 AM',
    });
  });

  it('exposes stable tab metadata order and label keys', () => {
    expect(DEFAULT_SCHEDULE_POPOVER_TAB).toBe('Event');
    expect(SCHEDULE_POPOVER_TABS).toEqual([
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
    ]);
  });
});
