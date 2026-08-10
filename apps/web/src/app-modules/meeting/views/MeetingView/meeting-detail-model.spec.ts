import { describe, expect, it } from 'vitest';

import type {
  ActiveRecordingLock,
  MeetingRecording,
} from '../../api/meeting-api';
import {
  activeRecordingLockForOtherUser,
  formatMeetingFileSize,
  formatMeetingRange,
  transcriptStatusKey,
} from './meeting-detail-model';

function recording(
  overrides: Partial<MeetingRecording> = {},
): MeetingRecording {
  return {
    id: 'recording-1',
    meeting_id: 'meeting-1',
    sequence_no: 1,
    file_url: 'https://example.test/audio.webm',
    file_size: 1024,
    mime_type: 'audio/webm',
    source: 'live_recording',
    uploaded_by_id: 'user-1',
    uploaded_by_name: 'User',
    transcription_status: 'pending',
    transcript_extracted: false,
    summary_generated: false,
    raw_transcript_doc_id: null,
    minutes_doc_id: null,
    error_message: null,
    created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
    ...overrides,
  } as MeetingRecording;
}

function lock(userId: string): ActiveRecordingLock {
  return {
    user_id: userId,
    user_name: 'Recorder',
    started_at: '2026-05-30T00:00:00Z',
    stale_after_seconds: 300,
  } as ActiveRecordingLock;
}

describe('meeting detail model', () => {
  it('maps transcript statuses to display translation keys', () => {
    expect(
      transcriptStatusKey(recording({ transcription_status: 'pending' })),
    ).toBe('meeting.recordingStatus.transcriptQueued');
    expect(
      transcriptStatusKey(recording({ transcription_status: 'transcribing' })),
    ).toBe('meeting.recordingStatus.transcriptExtracting');
    expect(
      transcriptStatusKey(recording({ transcription_status: 'failed' })),
    ).toBe('meeting.recordingStatus.transcriptFailed');
    expect(
      transcriptStatusKey(recording({ transcription_status: 'summarizing' })),
    ).toBe('meeting.recordingStatus.transcriptExtracted');
    expect(transcriptStatusKey(recording({ transcript_extracted: true }))).toBe(
      'meeting.recordingStatus.transcriptExtracted',
    );
  });

  it('formats file sizes with meeting display units', () => {
    expect(formatMeetingFileSize(512)).toBe('512 B');
    expect(formatMeetingFileSize(1023)).toBe('1023 B');
    expect(formatMeetingFileSize(1024)).toBe('1.0 KB');
    expect(formatMeetingFileSize(1536)).toBe('1.5 KB');
    expect(formatMeetingFileSize(1024 * 1024)).toBe('1.0 MB');
    expect(formatMeetingFileSize(5 * 1024 * 1024)).toBe('5.0 MB');
  });

  it('keeps only locks held by another user', () => {
    const otherLock = lock('user-2');

    expect(activeRecordingLockForOtherUser(otherLock, 'user-1')).toBe(
      otherLock,
    );
    expect(activeRecordingLockForOtherUser(otherLock, 'user-2')).toBeNull();
    expect(activeRecordingLockForOtherUser(null, 'user-1')).toBeNull();
    expect(activeRecordingLockForOtherUser(otherLock, null)).toBeNull();
  });

  it('formats meeting ranges through the app date parser', () => {
    expect(
      formatMeetingRange(
        '2026-05-30T01:00:00',
        '2026-05-30T02:30:00',
        'UTC',
        'en-US',
      ),
    ).toContain('02:30 AM');
  });
});
