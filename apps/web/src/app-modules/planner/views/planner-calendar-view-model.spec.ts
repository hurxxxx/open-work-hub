import { afterEach, describe, expect, it } from 'vitest';

import {
  buildPlannerDatePickerGrid,
  buildInitialPlannerRange,
  formatLocalYmd,
  formatPlannerHeading,
  persistTimelineRangeDays,
  readTimelineRangeDays,
  shouldBlockPlannerCalendar,
} from './planner-calendar-view-model';

describe('planner calendar error presentation', () => {
  it('blocks only when no usable calendar snapshot exists', () => {
    expect(shouldBlockPlannerCalendar('Initial load failed', false)).toBe(true);
    expect(shouldBlockPlannerCalendar('Refresh failed', true)).toBe(false);
    expect(shouldBlockPlannerCalendar(null, false)).toBe(false);
  });
});

describe('planner calendar view model', () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it('builds month, week, and day query ranges from the local date', () => {
    const currentDate = new Date(2026, 4, 26, 15, 30);

    expect(buildInitialPlannerRange(currentDate, 'Month', 'calendar')).toEqual({
      currentDate: new Date(2026, 4, 26),
      rangeStart: '2026-04-26',
      rangeEnd: '2026-06-07',
    });
    expect(buildInitialPlannerRange(currentDate, 'Week', 'calendar')).toEqual({
      currentDate: new Date(2026, 4, 26),
      rangeStart: '2026-05-24',
      rangeEnd: '2026-05-31',
    });
    expect(buildInitialPlannerRange(currentDate, 'Day', 'calendar')).toEqual({
      currentDate: new Date(2026, 4, 26),
      rangeStart: '2026-05-26',
      rangeEnd: '2026-05-27',
    });
  });

  it('builds timeline ranges from the start of the visible week', () => {
    expect(
      buildInitialPlannerRange(new Date(2026, 4, 26), 'Month', 'timeline', 14),
    ).toEqual({
      currentDate: new Date(2026, 4, 26),
      rangeStart: '2026-05-24',
      rangeEnd: '2026-06-07',
    });
  });

  it('persists only supported timeline range sizes', () => {
    expect(readTimelineRangeDays()).toBe(28);

    persistTimelineRangeDays(56);
    expect(readTimelineRangeDays()).toBe(56);

    window.localStorage.setItem(
      'open-work-hub:planner-timeline-range-days',
      '7',
    );
    expect(readTimelineRangeDays()).toBe(28);
  });

  it('formats calendar and timeline headings from model state', () => {
    const currentDate = new Date(2026, 4, 26);

    expect(
      formatPlannerHeading(
        'Day',
        currentDate,
        'en-US',
        'calendar',
        '2026-05-26',
        '2026-05-27',
      ),
    ).toBe('May 26, 2026');
    expect(
      formatPlannerHeading(
        'Month',
        currentDate,
        'en-US',
        'calendar',
        '2026-04-26',
        '2026-06-07',
      ),
    ).toBe('May 2026');
    expect(
      formatPlannerHeading(
        'Month',
        currentDate,
        'en-US',
        'timeline',
        '2026-05-24',
        '2026-06-07',
      ),
    ).toBe('May 24 - Jun 6, 2026');
  });

  it('formats local dates without UTC conversion', () => {
    expect(formatLocalYmd(new Date(2026, 0, 2, 23, 59))).toBe('2026-01-02');
  });

  it('builds a stable 42-cell date picker grid with leading blanks', () => {
    const cells = buildPlannerDatePickerGrid({
      pickerYear: 2026,
      pickerMonth: 1,
      viewYear: 2026,
      viewMonth: 1,
      selectedDate: 14,
      today: new Date(2026, 1, 14),
      getHolidayNames: () => null,
    });

    const leadingBlanks = new Date(2026, 1, 1).getDay();

    expect(cells).toHaveLength(42);
    expect(
      cells.slice(0, leadingBlanks).every((cell) => cell.kind === 'blank'),
    ).toBe(true);
    expect(
      cells.filter((cell) => cell.kind === 'day').map((cell) => cell.day),
    ).toEqual(Array.from({ length: 28 }, (_, index) => index + 1));
  });

  it('projects selected, today, sunday, and holiday flags for day cells', () => {
    const cells = buildPlannerDatePickerGrid({
      pickerYear: 2026,
      pickerMonth: 1,
      viewYear: 2026,
      viewMonth: 1,
      selectedDate: 1,
      today: new Date(2026, 1, 2),
      getHolidayNames: (_year, _month, day) =>
        day === 2 ? ['Observed holiday'] : null,
    });
    const first = cells.find((cell) => cell.kind === 'day' && cell.day === 1);
    const second = cells.find((cell) => cell.kind === 'day' && cell.day === 2);

    expect(first).toMatchObject({
      kind: 'day',
      isSelected: true,
      isSunday: true,
      isToday: false,
      holidayNames: null,
    });
    expect(second).toMatchObject({
      kind: 'day',
      isSelected: false,
      isSunday: false,
      isToday: true,
      holidayNames: ['Observed holiday'],
    });
  });

  it('does not mark selected dates outside the current view month', () => {
    const selectedInDifferentMonth = buildPlannerDatePickerGrid({
      pickerYear: 2026,
      pickerMonth: 1,
      viewYear: 2026,
      viewMonth: 2,
      selectedDate: 1,
      today: new Date(2026, 1, 1),
      getHolidayNames: () => null,
    });

    expect(
      selectedInDifferentMonth.some(
        (cell) => cell.kind === 'day' && cell.isSelected,
      ),
    ).toBe(false);
  });
});
