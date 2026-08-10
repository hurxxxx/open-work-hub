import { describe, expect, it } from 'vitest';

import type { MeetingAvailabilityBlock } from '../../api/meeting-api';

import {
  getAvailabilityBlockPositionPct,
  getAvailabilityBlockTone,
  getCurrentMeetingPositionPct,
} from './meeting-availability-modal-model';

const WEEK_START = new Date(2026, 2, 29, 0, 0, 0, 0);
const WEEK_END = new Date(2026, 3, 5, 0, 0, 0, 0);
const WEEK_MS = WEEK_END.getTime() - WEEK_START.getTime();

describe('meeting availability modal model', () => {
  it('selects planner and busy block tones', () => {
    expect(
      getAvailabilityBlockTone(
        availabilityBlock({
          masked: false,
          sourceType: 'planner_event',
        }),
      ),
    ).toEqual({
      backgroundColor: 'var(--ui-color-meeting-availability-planner-bg)',
      borderColor: 'var(--ui-color-meeting-availability-planner-border)',
    });
    expect(
      getAvailabilityBlockTone(
        availabilityBlock({
          masked: true,
          sourceType: 'planner_event',
        }),
      ),
    ).toEqual({
      backgroundColor: 'var(--ui-color-meeting-availability-busy-bg)',
      borderColor: 'var(--ui-color-meeting-availability-busy-border)',
    });
  });

  it('positions timed blocks within the visible week', () => {
    const position = getAvailabilityBlockPositionPct(
      availabilityBlock({
        start: new Date(2026, 2, 30, 12).toISOString(),
        end: new Date(2026, 2, 31, 12).toISOString(),
      }),
      WEEK_START,
      WEEK_END,
    );

    expect(position).toEqual({
      leftPct: pct(new Date(2026, 2, 30, 12).getTime() - WEEK_START.getTime()),
      widthPct: pct(24 * 60 * 60 * 1000),
    });
  });

  it('clamps all-day blocks to the visible week', () => {
    const position = getAvailabilityBlockPositionPct(
      availabilityBlock({
        start: '2026-03-28',
        end: '2026-03-31',
        allDay: true,
      }),
      WEEK_START,
      WEEK_END,
    );

    expect(position).toEqual({
      leftPct: 0,
      widthPct: pct(2 * 24 * 60 * 60 * 1000),
    });
  });

  it('returns null for blocks outside the week', () => {
    expect(
      getAvailabilityBlockPositionPct(
        availabilityBlock({
          start: new Date(2026, 2, 20).toISOString(),
          end: new Date(2026, 2, 21).toISOString(),
        }),
        WEEK_START,
        WEEK_END,
      ),
    ).toBeNull();
    expect(
      getAvailabilityBlockPositionPct(
        availabilityBlock({
          start: new Date(2026, 3, 5).toISOString(),
          end: new Date(2026, 3, 6).toISOString(),
        }),
        WEEK_START,
        WEEK_END,
      ),
    ).toBeNull();
  });

  it('positions the current meeting highlight and rejects invalid windows', () => {
    expect(
      getCurrentMeetingPositionPct({
        meetingStart: new Date(2026, 2, 29, 6),
        meetingEnd: new Date(2026, 2, 29, 12),
        weekStart: WEEK_START,
        weekEnd: WEEK_END,
      }),
    ).toEqual({
      leftPct: pct(6 * 60 * 60 * 1000),
      widthPct: pct(6 * 60 * 60 * 1000),
    });
    expect(
      getCurrentMeetingPositionPct({
        meetingStart: new Date(2026, 2, 29, 12),
        meetingEnd: new Date(2026, 2, 29, 12),
        weekStart: WEEK_START,
        weekEnd: WEEK_END,
      }),
    ).toBeNull();
    expect(
      getCurrentMeetingPositionPct({
        meetingStart: null,
        meetingEnd: new Date(2026, 2, 29, 12),
        weekStart: WEEK_START,
        weekEnd: WEEK_END,
      }),
    ).toBeNull();
  });
});

function availabilityBlock(
  overrides: Partial<MeetingAvailabilityBlock> = {},
): MeetingAvailabilityBlock {
  return {
    id: 'block-1',
    start: new Date(2026, 2, 30, 9).toISOString(),
    end: new Date(2026, 2, 30, 10).toISOString(),
    allDay: false,
    sourceType: 'meeting',
    masked: false,
    title: 'Schedule',
    location: null,
    ...overrides,
  };
}

function pct(durationMs: number): number {
  return (durationMs / WEEK_MS) * 100;
}
