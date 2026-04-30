import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMeetingAvailabilityQuery } from './meetingAvailability';

const availabilityHarness = vi.hoisted(() => ({
  getMeetingAvailability: vi.fn(),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
  }),
}));

vi.mock('../../api/meeting-api', async () => {
  const actual = await vi.importActual<typeof import('../../api/meeting-api')>('../../api/meeting-api');
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
      ({ userIds, rangeStart, rangeEnd }) => useMeetingAvailabilityQuery({
        workspaceSlug: 'hq',
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
      expect(availabilityHarness.getMeetingAvailability).toHaveBeenCalledTimes(1);
    });

    rerender({
      userIds: ['user-1'],
      rangeStart: new Date(firstRangeStart.getTime()),
      rangeEnd: new Date(firstRangeEnd.getTime()),
    });

    await waitFor(() => {
      expect(availabilityHarness.getMeetingAvailability).toHaveBeenCalledTimes(1);
    });
  });
});
