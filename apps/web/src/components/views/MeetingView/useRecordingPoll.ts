import { useEffect } from 'react';

import { getMeeting, type MeetingDetail } from '@/src/domains/meeting/meeting-api';

const ACTIVE_STATUSES = new Set(['pending', 'transcribing', 'summarizing', 'generating_doc']);

export function useRecordingPoll(
  token: string | null,
  workspaceSlug: string,
  meetingId: string,
  meeting: MeetingDetail | null,
  onMeetingUpdated: (meeting: MeetingDetail) => void,
  /** Current authenticated user id — used to gate the lock-watch poll. */
  currentUserId?: string | null,
) {
  useEffect(() => {
    if (!token || !meeting) {
      return;
    }
    const hasActiveRecording = meeting.recordings.some((recording) =>
      ACTIVE_STATUSES.has(recording.transcription_status),
    );
    // Also poll when a recording lock is held by a DIFFERENT user — so the
    // viewer's UI auto-clears the moment the recorder finishes (or crashes
    // and the stale window expires server-side).
    const lock = meeting.active_recording_lock;
    const hasForeignLock = Boolean(
      lock && currentUserId && lock.user_id !== currentUserId,
    );
    if (!hasActiveRecording && !hasForeignLock) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const nextMeeting = await getMeeting(token, workspaceSlug, meetingId);
        onMeetingUpdated(nextMeeting);
      } catch {
        // Keep the previous UI state and retry on the next interval.
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [meeting, meetingId, onMeetingUpdated, token, workspaceSlug, currentUserId]);
}
