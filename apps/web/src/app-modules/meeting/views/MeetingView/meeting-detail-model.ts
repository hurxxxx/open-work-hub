import { formatByteSize } from '@/src/platform/format/byte-size';
import { formatDateTime } from '@/src/platform/time/time-utils';

import {
  parseServerDateTime,
  type ActiveRecordingLock,
  type MeetingRecording,
} from '../../api/meeting-api';

const TRANSCRIPT_EXTRACTED_STATUSES = new Set([
  'summarizing',
  'extracting_insights',
  'generating_doc',
  'done',
]);

export function transcriptStatusKey(recording: MeetingRecording): string {
  if (
    recording.transcript_extracted === true ||
    TRANSCRIPT_EXTRACTED_STATUSES.has(recording.transcription_status)
  ) {
    return 'meeting.recordingStatus.transcriptExtracted';
  }
  if (recording.transcription_status === 'transcribing') {
    return 'meeting.recordingStatus.transcriptExtracting';
  }
  if (recording.transcription_status === 'failed') {
    return 'meeting.recordingStatus.transcriptFailed';
  }
  return 'meeting.recordingStatus.transcriptQueued';
}

export function formatMeetingRange(
  start: string,
  end: string,
  timeZone: string,
  locale: string,
): string {
  const startDate = parseServerDateTime(start);
  const endDate = parseServerDateTime(end);
  return `${formatDateTime(startDate, {
    locale,
    month: 'short',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  })} – ${formatDateTime(endDate, {
    hour: '2-digit',
    locale,
    minute: '2-digit',
    timeZone,
  })}`;
}

export function formatMeetingFileSize(bytes: number): string {
  return formatByteSize(bytes);
}

export function activeRecordingLockForOtherUser(
  lock: ActiveRecordingLock | null | undefined,
  userId: string | null | undefined,
): ActiveRecordingLock | null {
  if (!lock || !userId) return null;
  if (lock.user_id === userId) return null;
  return lock;
}
