import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PlannerView } from './PlannerView';

const plannerHarness = vi.hoisted(() => {
  const fixedToday = new Date(2026, 3, 2);
  let calendarState = {
    view: 'dayGridMonth',
    currentDate: new Date(2026, 2, 15),
    rangeStart: new Date(2026, 2, 1),
    rangeEnd: new Date(2026, 3, 1),
  };
  let latestProps: {
    onDatesSet?: (state: {
      view: 'dayGridMonth' | 'timeGridWeek' | 'timeGridDay' | 'listWeek';
      currentDate: Date;
      rangeStart: Date;
      rangeEnd: Date;
    }) => void;
    onDateSelect?: (range: { start: Date; end: Date; allDay: boolean }) => void;
  } | null = null;

  const useCalendarEvents = vi.fn((options: unknown) => {
    void options;
    return {
      events: [],
      loading: false,
      error: null,
      refresh: vi.fn(),
    };
  });
  const updateMeeting = vi.fn();
  const updateIssue = vi.fn();
  const updatePlannerEvent = vi.fn();

  const cloneDate = (date: Date) => new Date(date.getTime());
  const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const addDays = (date: Date, days: number) => {
    const next = startOfDay(date);
    next.setDate(next.getDate() + days);
    return next;
  };
  const startOfWeek = (date: Date) => addDays(date, -startOfDay(date).getDay());

  const syncRange = () => {
    const currentDate = startOfDay(calendarState.currentDate);
    calendarState.currentDate = currentDate;
    if (calendarState.view === 'dayGridMonth') {
      calendarState.rangeStart = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
      calendarState.rangeEnd = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1);
      return;
    }
    if (calendarState.view === 'timeGridDay') {
      calendarState.rangeStart = currentDate;
      calendarState.rangeEnd = addDays(currentDate, 1);
      return;
    }
    calendarState.rangeStart = startOfWeek(currentDate);
    calendarState.rangeEnd = addDays(calendarState.rangeStart, 7);
  };

  const emitDatesSet = () => {
    latestProps?.onDatesSet?.({
      view: calendarState.view as 'dayGridMonth' | 'timeGridWeek' | 'timeGridDay' | 'listWeek',
      currentDate: cloneDate(calendarState.currentDate),
      rangeStart: cloneDate(calendarState.rangeStart),
      rangeEnd: cloneDate(calendarState.rangeEnd),
    });
  };

  return {
    fixedToday,
    useCalendarEvents,
    updateMeeting,
    updateIssue,
    updatePlannerEvent,
    setLatestProps(props: typeof latestProps) {
      latestProps = props;
    },
    emitDatesSet,
    emitDateSelect(range: { start: Date; end: Date; allDay: boolean }) {
      latestProps?.onDateSelect?.(range);
    },
    resetCalendarState(next?: Partial<typeof calendarState>) {
      calendarState = {
        view: 'dayGridMonth',
        currentDate: new Date(2026, 2, 15),
        rangeStart: new Date(2026, 2, 1),
        rangeEnd: new Date(2026, 3, 1),
        ...next,
      };
    },
    changeView(view: 'dayGridMonth' | 'timeGridWeek' | 'timeGridDay' | 'listWeek') {
      calendarState.view = view;
      syncRange();
      emitDatesSet();
    },
    prev() {
      const next = cloneDate(calendarState.currentDate);
      if (calendarState.view === 'dayGridMonth') {
        next.setMonth(next.getMonth() - 1);
      } else if (calendarState.view === 'timeGridDay') {
        next.setDate(next.getDate() - 1);
      } else {
        next.setDate(next.getDate() - 7);
      }
      calendarState.currentDate = next;
      syncRange();
      emitDatesSet();
    },
    next() {
      const next = cloneDate(calendarState.currentDate);
      if (calendarState.view === 'dayGridMonth') {
        next.setMonth(next.getMonth() + 1);
      } else if (calendarState.view === 'timeGridDay') {
        next.setDate(next.getDate() + 1);
      } else {
        next.setDate(next.getDate() + 7);
      }
      calendarState.currentDate = next;
      syncRange();
      emitDatesSet();
    },
    today() {
      calendarState.currentDate = cloneDate(fixedToday);
      syncRange();
      emitDatesSet();
    },
    gotoDate(date: Date | string) {
      calendarState.currentDate = typeof date === 'string' ? new Date(date) : cloneDate(date);
      syncRange();
      emitDatesSet();
    },
  };
});

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
  }),
}));

vi.mock('@/src/domains/calendar/use-calendar-events', () => ({
  useCalendarEvents: (options: unknown) => plannerHarness.useCalendarEvents(options),
}));

vi.mock('@/src/domains/meeting/meeting-api', () => ({
  updateMeeting: plannerHarness.updateMeeting,
}));

vi.mock('@/src/domains/pms/pms-api', () => ({
  updateIssue: plannerHarness.updateIssue,
}));

vi.mock('@/src/domains/planner/planner-api', () => ({
  updatePlannerEvent: plannerHarness.updatePlannerEvent,
}));

vi.mock('./calendar/MeetingPreviewModal', () => ({
  MeetingPreviewModal: () => null,
}));

vi.mock('@/src/app-modules/meeting', () => ({
  MeetingCreateModal: ({ isOpen }: { isOpen: boolean }) => (isOpen ? <div data-testid="mock-meeting-create-modal" /> : null),
}));

vi.mock('./PlannerEventModal', () => ({
  PlannerEventModal: ({ isOpen }: { isOpen: boolean }) => (isOpen ? <div data-testid="mock-planner-event-modal" /> : null),
}));

vi.mock('@/src/components/calendar/UnifiedCalendar', async () => {
  const React = await import('react');

  const MockUnifiedCalendar = React.forwardRef(function MockUnifiedCalendar(props: Record<string, unknown>, ref) {
    plannerHarness.setLatestProps(props as never);

    React.useEffect(() => {
      plannerHarness.emitDatesSet();
    }, [props]);

    React.useImperativeHandle(ref, () => ({
      changeView: plannerHarness.changeView,
      prev: plannerHarness.prev,
      next: plannerHarness.next,
      today: plannerHarness.today,
      gotoDate: plannerHarness.gotoDate,
      getCurrentView: () => undefined,
    }), []);

    return <div data-testid="mock-calendar" />;
  });

  return {
    UnifiedCalendar: MockUnifiedCalendar,
  };
});

function renderPlannerView() {
  return render(
    <MemoryRouter initialEntries={['/w/hq/planner']}>
      <Routes>
        <Route path="/w/:workspaceSlug/planner" element={<PlannerView />} />
      </Routes>
    </MemoryRouter>,
  );
}

function getLastCalendarRequest(): { from: string; to: string } {
  const call = plannerHarness.useCalendarEvents.mock.calls.at(-1);
  expect(call).toBeTruthy();
  return call?.[0] as unknown as { from: string; to: string };
}

describe('PlannerView', () => {
  beforeEach(() => {
    plannerHarness.useCalendarEvents.mockClear();
    plannerHarness.updateMeeting.mockClear();
    plannerHarness.updateIssue.mockClear();
    plannerHarness.updatePlannerEvent.mockClear();
    plannerHarness.resetCalendarState();
  });

  it('uses local YYYY-MM-DD ranges and opens planner event creation from the toolbar', async () => {
    renderPlannerView();

    await waitFor(() => {
      const lastCall = getLastCalendarRequest();
      expect(lastCall.from).toBe('2026-03-01');
      expect(lastCall.to).toBe('2026-04-01');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    fireEvent.click(screen.getByRole('button', { name: 'Event' }));

    expect(screen.getByTestId('mock-planner-event-modal')).toBeTruthy();
  });

  it('keeps week navigation and Today in sync with the visible range', async () => {
    plannerHarness.resetCalendarState({
      view: 'timeGridWeek',
      currentDate: new Date(2026, 2, 10),
      rangeStart: new Date(2026, 2, 8),
      rangeEnd: new Date(2026, 2, 15),
    });

    renderPlannerView();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'March 2026' })).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next period' }));
    await waitFor(() => {
      const lastCall = getLastCalendarRequest();
      expect(lastCall.from).toBe('2026-03-15');
      expect(lastCall.to).toBe('2026-03-22');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Today' }));
    await waitFor(() => {
      const lastCall = getLastCalendarRequest();
      expect(lastCall.from).toBe('2026-03-29');
      expect(lastCall.to).toBe('2026-04-05');
      expect(screen.getByRole('button', { name: 'April 2026' })).toBeTruthy();
    });
  });

  it('drives day view navigation from the date picker selection', async () => {
    plannerHarness.resetCalendarState({
      view: 'timeGridDay',
      currentDate: new Date(2026, 2, 10),
      rangeStart: new Date(2026, 2, 10),
      rangeEnd: new Date(2026, 2, 11),
    });

    renderPlannerView();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'March 10, 2026' })).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: 'March 10, 2026' }));
    fireEvent.click(screen.getByRole('button', { name: '18' }));

    await waitFor(() => {
      const lastCall = getLastCalendarRequest();
      expect(lastCall.from).toBe('2026-03-18');
      expect(lastCall.to).toBe('2026-03-19');
      expect(screen.getByRole('button', { name: 'March 18, 2026' })).toBeTruthy();
    });
  });

  it('opens the planner event modal from empty-calendar selection', async () => {
    renderPlannerView();

    await act(async () => {
      plannerHarness.emitDateSelect({
        start: new Date(2026, 2, 21),
        end: new Date(2026, 2, 22),
        allDay: true,
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Create event or meeting' })).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: '이벤트' }));

    await waitFor(() => {
      expect(screen.getByTestId('mock-planner-event-modal')).toBeTruthy();
    });
  });

  it('opens the planner meeting flow from the sidebar event bus', async () => {
    renderPlannerView();

    await act(async () => {
      window.dispatchEvent(new CustomEvent('planner:create-meeting'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('mock-meeting-create-modal')).toBeTruthy();
    });
  });
});
