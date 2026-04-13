import { useEffect } from 'react';

import { getMeeting, type MeetingDetail } from '@/src/domains/meeting/meeting-api';

const ACTIVE_STATUSES = new Set(['pending', 'transcribing', 'summarizing', 'generating_doc']);

export function useRecordingPoll(
  token: string | null,
  meetingId: string,
  meeting: MeetingDetail | null,
  onMeetingUpdated: (meeting: MeetingDetail) => void,
) {
  useEffect(() => {
    if (!token || !meeting) {
      return;
    }
    const hasActiveRecording = meeting.recordings.some((recording) =>
      ACTIVE_STATUSES.has(recording.transcription_status),
    );
    if (!hasActiveRecording) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const nextMeeting = await getMeeting(token, meetingId);
        onMeetingUpdated(nextMeeting);
      } catch {
        // Keep the previous UI state and retry on the next interval.
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [meeting, meetingId, onMeetingUpdated, token]);
}
