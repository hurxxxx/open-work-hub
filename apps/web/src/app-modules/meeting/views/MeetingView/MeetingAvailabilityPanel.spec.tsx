import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MeetingAvailabilityPanel } from './MeetingAvailabilityPanel';
import {
  addLocalDays,
  startOfAvailabilityWeek,
} from './meetingAvailability';

const availabilityHarness = vi.hoisted(() => ({
  useMeetingAvailabilityQuery: vi.fn(),
}));

const MEETING_START_ISO = '2026-04-14T05:00:00.000Z';
const MEETING_END_ISO = '2026-04-14T06:00:00.000Z';

vi.mock('@aidoo/ui', () => ({
  Dialog: ({
    open,
    title,
    description,
    children,
  }: {
    open: boolean;
    title: string;
    description?: string;
    children?: ReactNode;
  }) => (open ? (
    <div>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      <div>{children}</div>
    </div>
  ) : null),
}));

vi.mock('./meetingAvailability', async () => {
  const actual = await vi.importActual<typeof import('./meetingAvailability')>('./meetingAvailability');
  return {
    ...actual,
    useMeetingAvailabilityQuery: availabilityHarness.useMeetingAvailabilityQuery,
  };
});

describe('MeetingAvailabilityPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    availabilityHarness.useMeetingAvailabilityQuery.mockReturnValue({
      items: [
        {
          userId: 'user-1',
          fullName: 'Alice Kim',
          blocks: [
            {
              id: 'meeting-1',
              start: '2026-04-14T05:00:00Z',
              end: '2026-04-14T06:00:00Z',
              allDay: false,
              sourceType: 'meeting',
              masked: true,
              title: null,
              location: null,
            },
          ],
        },
        {
          userId: 'user-2',
          fullName: 'Bob Lee',
          blocks: [
            {
              id: 'planner-event-1',
              start: '2026-04-14T05:30:00Z',
              end: '2026-04-14T07:00:00Z',
              allDay: false,
              sourceType: 'planner_event',
              masked: false,
              title: '출장',
              location: '판교',
            },
          ],
        },
      ],
      loading: false,
      error: null,
    });
  });

  it('shows conflict summaries and opens the attendee schedule modal', async () => {
    render(
      <MeetingAvailabilityPanel
        workspaceSlug="hq"
        attendeeUsers={[
          { id: 'user-1', email: 'alice@aidoo.ai', full_name: 'Alice Kim' },
          { id: 'user-2', email: 'bob@aidoo.ai', full_name: 'Bob Lee' },
        ]}
        meetingStart={new Date(MEETING_START_ISO)}
        meetingEnd={new Date(MEETING_END_ISO)}
      />,
    );

    expect(screen.getByText('일정 충돌 2건이 감지되었습니다.')).toBeTruthy();
    expect(screen.getByText(/Busy/)).toBeTruthy();
    expect(screen.getByText(/출장/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '스케줄 보기' }));

    expect(screen.getByRole('heading', { name: '참석자 스케줄' })).toBeTruthy();
    expect(screen.getAllByText('Alice Kim').length).toBeGreaterThan(0);
    expect(screen.getByText('alice@aidoo.ai')).toBeTruthy();
    expect(screen.getAllByText('Bob Lee').length).toBeGreaterThan(0);
    expect(screen.getByText('bob@aidoo.ai')).toBeTruthy();
  });

  it('moves the compared week when the modal navigation buttons are clicked', async () => {
    const meetingStart = new Date(MEETING_START_ISO);
    const expectedWeekStart = startOfAvailabilityWeek(meetingStart);
    const expectedWeekEnd = addLocalDays(expectedWeekStart, 7);
    const expectedNextWeekStart = addLocalDays(expectedWeekStart, 7);
    const expectedNextWeekEnd = addLocalDays(expectedWeekStart, 14);

    render(
      <MeetingAvailabilityPanel
        workspaceSlug="hq"
        attendeeUsers={[
          { id: 'user-1', email: 'alice@aidoo.ai', full_name: 'Alice Kim' },
        ]}
        meetingStart={meetingStart}
        meetingEnd={new Date(MEETING_END_ISO)}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '스케줄 보기' }));

    await waitFor(() => {
      expect(availabilityHarness.useMeetingAvailabilityQuery).toHaveBeenCalled();
    });

    const initialOpenCall = availabilityHarness.useMeetingAvailabilityQuery.mock.calls.at(-1)?.[0] as {
      enabled: boolean;
      rangeStart: Date;
      rangeEnd: Date;
    };
    expect(initialOpenCall.enabled).toBe(true);
    expect(initialOpenCall.rangeStart.getTime()).toBe(expectedWeekStart.getTime());
    expect(initialOpenCall.rangeEnd.getTime()).toBe(expectedWeekEnd.getTime());

    fireEvent.click(screen.getByRole('button', { name: 'Next availability week' }));

    await waitFor(() => {
      const nextCall = availabilityHarness.useMeetingAvailabilityQuery.mock.calls.at(-1)?.[0] as {
        rangeStart: Date;
        rangeEnd: Date;
      };
      expect(nextCall.rangeStart.getTime()).toBe(expectedNextWeekStart.getTime());
      expect(nextCall.rangeEnd.getTime()).toBe(expectedNextWeekEnd.getTime());
    });
  });
});
