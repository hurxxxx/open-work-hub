import type { MeetingAvailabilityBlock } from '../../api/meeting-api';

import { parseAvailabilityBoundary } from './meetingAvailability';

export type AvailabilityBlockPositionPct = {
  leftPct: number;
  widthPct: number;
};

export type AvailabilityBlockTone = {
  backgroundColor: string;
  borderColor: string;
};

const PLANNER_EVENT_TONE: AvailabilityBlockTone = {
  backgroundColor: 'var(--ui-color-meeting-availability-planner-bg)',
  borderColor: 'var(--ui-color-meeting-availability-planner-border)',
};

const BUSY_TONE: AvailabilityBlockTone = {
  backgroundColor: 'var(--ui-color-meeting-availability-busy-bg)',
  borderColor: 'var(--ui-color-meeting-availability-busy-border)',
};

export function getAvailabilityBlockTone(
  block: MeetingAvailabilityBlock,
): AvailabilityBlockTone {
  if (!block.masked && block.sourceType === 'planner_event') {
    return PLANNER_EVENT_TONE;
  }
  return BUSY_TONE;
}

export function getAvailabilityBlockPositionPct(
  block: MeetingAvailabilityBlock,
  weekStart: Date,
  weekEnd: Date,
): AvailabilityBlockPositionPct | null {
  return getRangePositionPct(
    parseAvailabilityBoundary(block.start, block.allDay),
    parseAvailabilityBoundary(block.end, block.allDay),
    weekStart,
    weekEnd,
  );
}

export function getCurrentMeetingPositionPct({
  meetingStart,
  meetingEnd,
  weekStart,
  weekEnd,
}: {
  meetingStart: Date | null;
  meetingEnd: Date | null;
  weekStart: Date | null;
  weekEnd: Date | null;
}): AvailabilityBlockPositionPct | null {
  if (!weekStart || !weekEnd || !meetingStart || !meetingEnd) {
    return null;
  }
  return getRangePositionPct(meetingStart, meetingEnd, weekStart, weekEnd);
}

function getRangePositionPct(
  start: Date,
  end: Date,
  weekStart: Date,
  weekEnd: Date,
): AvailabilityBlockPositionPct | null {
  const weekStartMs = weekStart.getTime();
  const weekEndMs = weekEnd.getTime();
  const clampedStart = Math.max(start.getTime(), weekStartMs);
  const clampedEnd = Math.min(end.getTime(), weekEndMs);
  if (clampedEnd <= clampedStart) {
    return null;
  }
  const weekMs = weekEndMs - weekStartMs;
  return {
    leftPct: ((clampedStart - weekStartMs) / weekMs) * 100,
    widthPct: ((clampedEnd - clampedStart) / weekMs) * 100,
  };
}
