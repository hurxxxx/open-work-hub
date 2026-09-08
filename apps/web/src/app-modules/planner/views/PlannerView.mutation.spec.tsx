import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FloatingTodayPlannerWidget } from './FloatingTodayPlannerWidget';
import { PlannerView } from './PlannerView';

const calendarHarness = vi.hoisted(() => ({
  refresh: vi.fn(),
  removeEvent: vi.fn(),
  upsertEvent: vi.fn(),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token', user: { time_zone: 'UTC' } }),
}));

vi.mock('@/src/platform/calendar/use-calendar-events', () => ({
  useCalendarEvents: () => ({
    events: [],
    loading: false,
    error: null,
    hasUsableSnapshot: true,
    ...calendarHarness,
  }),
}));

vi.mock('@/src/components/calendar/UnifiedCalendar', () => ({
  UnifiedCalendar: () => <div data-testid="unified-calendar" />,
}));

vi.mock('@/src/app-modules/meeting', () => ({
  MeetingCreateModal: () => null,
}));

vi.mock('./calendar/MeetingPreviewModal', () => ({
  MeetingPreviewModal: () => null,
}));

vi.mock('./PlannerEventChoicePopover', () => ({
  PlannerEventChoicePopover: () => null,
}));

vi.mock('./PlannerTimelineView', () => ({
  PlannerTimelineView: () => <div data-testid="planner-timeline" />,
}));

vi.mock('./PlannerEventModal', () => ({
  PlannerEventModal: ({
    onDeleted,
    onSaved,
  }: {
    onDeleted: (eventId: string) => void;
    onSaved: (event: Record<string, unknown>) => void;
  }) => (
    <div>
      <button
        type="button"
        onClick={() =>
          onSaved({
            id: 'event-1',
            ownerId: 'user-1',
            ownerName: 'Planner User',
            title: 'Saved immediately',
            description: '',
            location: '',
            timeZone: 'UTC',
            allDay: false,
            startHasTime: true,
            endHasTime: true,
            start: '2026-08-29T01:00:00+00:00',
            end: '2026-08-29T02:00:00+00:00',
            calendarStart: '2026-08-29T01:00:00+00:00',
            calendarEnd: '2026-08-29T02:00:00+00:00',
            calendarAllDay: false,
            createdAt: '2026-08-28T00:00:00+00:00',
            updatedAt: '2026-08-28T00:00:00+00:00',
          })
        }
      >
        Save fixture event
      </button>
      <button type="button" onClick={() => onDeleted('event-1')}>
        Delete fixture event
      </button>
    </div>
  ),
}));

describe('Planner mutation callback wiring', () => {
  beforeEach(() => {
    calendarHarness.refresh.mockReset();
    calendarHarness.removeEvent.mockReset();
    calendarHarness.upsertEvent.mockReset();
  });

  it('projects modal save and delete into the open Planner view before refresh', () => {
    render(
      <MemoryRouter>
        <PlannerView />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save fixture event' }));
    expect(calendarHarness.upsertEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'planner-event-event-1',
        title: 'Saved immediately',
      }),
    );
    expect(calendarHarness.refresh).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getByRole('button', { name: 'Delete fixture event' }),
    );
    expect(calendarHarness.removeEvent).toHaveBeenCalledWith(
      'planner-event-event-1',
    );
    expect(calendarHarness.refresh).toHaveBeenCalledTimes(2);
  });

  it('projects modal mutations into the floating Planner and notifies its owner', () => {
    const onChanged = vi.fn();
    render(
      <MemoryRouter>
        <FloatingTodayPlannerWidget onChanged={onChanged} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save fixture event' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Delete fixture event' }),
    );

    expect(calendarHarness.upsertEvent).toHaveBeenCalledOnce();
    expect(calendarHarness.removeEvent).toHaveBeenCalledWith(
      'planner-event-event-1',
    );
    expect(calendarHarness.refresh).toHaveBeenCalledTimes(2);
    expect(onChanged).toHaveBeenCalledTimes(2);
  });
});
