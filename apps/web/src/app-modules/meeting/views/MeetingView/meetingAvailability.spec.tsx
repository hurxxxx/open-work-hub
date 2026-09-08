import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  deriveMeetingAvailabilityQueryRange,
  isValidMeetingAvailabilityWindow,
  projectMeetingAvailabilityAttendeeIds,
  projectMeetingAvailabilityPanelQuery,
  selectMeetingAvailabilityPanelDisplayState,
  useMeetingAvailabilityQuery,
} from './meetingAvailability';

const availabilityHarness = vi.hoisted(() => ({
  getMeetingAvailability: vi.fn(),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
  }),
}));

vi.mock('../../api/meeting-api', async () => {
  const actual = await vi.importActual<typeof import('../../api/meeting-api')>(
    '../../api/meeting-api',
  );
  return {
    ...actual,
    getMeetingAvailability: availabilityHarness.getMeetingAvailability,
  };
});

describe('useMeetingAvailabilityQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    availabilityHarness.getMeetingAvailability.mockResolvedValue({
      items: [],
    });
  });

  it('does not refetch endlessly when caller recreates identical dates and user arrays', async () => {
    const firstRangeStart = new Date(2026, 2, 29, 0, 0, 0, 0);
    const firstRangeEnd = new Date(2026, 3, 5, 0, 0, 0, 0);
    const { rerender } = renderHook(
      ({ userIds, rangeStart, rangeEnd }) =>
        useMeetingAvailabilityQuery({
          userIds,
          rangeStart,
          rangeEnd,
          enabled: true,
        }),
      {
        initialProps: {
          userIds: ['user-1'],
          rangeStart: firstRangeStart,
          rangeEnd: firstRangeEnd,
        },
      },
    );

    await waitFor(() => {
      expect(availabilityHarness.getMeetingAvailability).toHaveBeenCalledTimes(
        1,
      );
    });

    rerender({
      userIds: ['user-1'],
      rangeStart: new Date(firstRangeStart.getTime()),
      rangeEnd: new Date(firstRangeEnd.getTime()),
    });

    await waitFor(() => {
      expect(availabilityHarness.getMeetingAvailability).toHaveBeenCalledTimes(
        1,
      );
    });
  });
});

describe('meeting availability panel projection', () => {
  it('validates meeting windows', () => {
    const start = new Date(2026, 4, 31, 9, 0);

    expect(
      isValidMeetingAvailabilityWindow(start, new Date(2026, 4, 31, 10, 0)),
    ).toBe(true);
    expect(
      isValidMeetingAvailabilityWindow(start, new Date(2026, 4, 31, 9, 0)),
    ).toBe(false);
    expect(isValidMeetingAvailabilityWindow(start, null)).toBe(false);
    expect(
      isValidMeetingAvailabilityWindow(null, new Date(2026, 4, 31, 10, 0)),
    ).toBe(false);
  });

  it('projects attendee ids in first-seen order without duplicates', () => {
    expect(
      projectMeetingAvailabilityAttendeeIds([
        { id: 'user-1' },
        { id: 'user-2' },
        { id: 'user-1' },
      ]),
    ).toEqual(['user-1', 'user-2']);
  });

  it('derives the containing local availability week range', () => {
    const { rangeEnd, rangeStart } = deriveMeetingAvailabilityQueryRange(
      new Date(2026, 4, 31, 14, 30),
    );

    expect(rangeStart).toEqual(new Date(2026, 4, 31, 0, 0, 0, 0));
    expect(rangeEnd).toEqual(new Date(2026, 5, 7, 0, 0, 0, 0));
  });

  it('projects panel query readiness from window, attendees, and range', () => {
    expect(
      projectMeetingAvailabilityPanelQuery({
        attendeeUsers: [{ id: 'user-1' }, { id: 'user-1' }],
        meetingEnd: new Date(2026, 4, 31, 10, 0),
        meetingStart: new Date(2026, 4, 31, 9, 0),
      }),
    ).toMatchObject({
      attendeeIds: ['user-1'],
      canQuery: true,
      validMeetingWindow: true,
    });

    expect(
      projectMeetingAvailabilityPanelQuery({
        attendeeUsers: [{ id: 'user-1' }],
        meetingEnd: new Date(2026, 4, 31, 9, 0),
        meetingStart: new Date(2026, 4, 31, 9, 0),
      }).canQuery,
    ).toBe(false);

    expect(
      projectMeetingAvailabilityPanelQuery({
        attendeeUsers: [],
        meetingEnd: new Date(2026, 4, 31, 10, 0),
        meetingStart: new Date(2026, 4, 31, 9, 0),
      }).canQuery,
    ).toBe(false);
  });

  it('selects panel display state by render precedence', () => {
    expect(
      selectMeetingAvailabilityPanelDisplayState({
        attendeeCount: 1,
        conflictCount: 1,
        error: 'Failed',
        loading: true,
        validMeetingWindow: false,
      }),
    ).toEqual({ type: 'invalid-window' });

    expect(
      selectMeetingAvailabilityPanelDisplayState({
        attendeeCount: 0,
        conflictCount: 1,
        error: 'Failed',
        loading: true,
        validMeetingWindow: true,
      }),
    ).toEqual({ type: 'no-attendees' });

    expect(
      selectMeetingAvailabilityPanelDisplayState({
        attendeeCount: 1,
        conflictCount: 1,
        error: 'Failed',
        loading: true,
        validMeetingWindow: true,
      }),
    ).toEqual({ type: 'loading' });

    expect(
      selectMeetingAvailabilityPanelDisplayState({
        attendeeCount: 1,
        conflictCount: 1,
        error: 'Failed',
        loading: false,
        validMeetingWindow: true,
      }),
    ).toEqual({ message: 'Failed', type: 'error' });

    expect(
      selectMeetingAvailabilityPanelDisplayState({
        attendeeCount: 1,
        conflictCount: 0,
        error: null,
        loading: false,
        validMeetingWindow: true,
      }),
    ).toEqual({ type: 'no-conflicts' });

    expect(
      selectMeetingAvailabilityPanelDisplayState({
        attendeeCount: 1,
        conflictCount: 2,
        error: null,
        loading: false,
        validMeetingWindow: true,
      }),
    ).toEqual({ count: 2, type: 'conflicts' });
  });
});
