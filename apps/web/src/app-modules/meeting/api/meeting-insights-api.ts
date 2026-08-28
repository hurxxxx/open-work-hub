import { invokeAiTool } from '@/src/platform/ai/ai-api';

import type { MeetingAvailabilityResponse } from './meeting-api';

export type MeetingInsightType = 'action' | 'decision' | 'followup_schedule';
export type MeetingInsightStatus =
  | 'draft'
  | 'accepted'
  | 'rejected'
  | 'superseded';

export interface MeetingInsightSourceSpan {
  start_ms: number | null;
  end_ms: number | null;
  quote: string | null;
}

/**
 * Raw ``MeetingInsight`` row as returned by the backend read tools. The
 * actual suggestion data lives in ``payload`` — shape depends on
 * ``insight_type``. Callers should branch on ``insight_type`` before
 * touching payload keys (see ``openMeetingInsightInChat`` for the
 * canonical pattern).
 */
export interface MeetingInsightItem {
  id: string;
  meeting_id: string;
  recording_id: string | null;
  workspace_id: string;
  insight_type: MeetingInsightType;
  payload: Record<string, unknown>;
  confidence: number | null;
  source_span: MeetingInsightSourceSpan | null;
  status: MeetingInsightStatus;
  accepted_as_kind: string | null;
  accepted_as_id: string | null;
  created_by_run_id: string | null;
  created_at: string;
}

export interface MeetingInsightListResult {
  items: MeetingInsightItem[];
}

export interface MeetingFollowupResult {
  items: MeetingInsightItem[];
  attendee_user_ids: string[];
  availability: MeetingAvailabilityResponse | null;
}

interface RefreshOptions {
  refresh?: boolean;
}

export function extractActions(
  token: string,
  meetingId: string,
  options: RefreshOptions = {},
): Promise<MeetingInsightListResult> {
  return invokeAiTool<MeetingInsightListResult>(
    'meeting.extract_actions',
    { meeting_id: meetingId, refresh: options.refresh ?? false },
    token,
  );
}

export function extractDecisions(
  token: string,
  meetingId: string,
  options: RefreshOptions = {},
): Promise<MeetingInsightListResult> {
  return invokeAiTool<MeetingInsightListResult>(
    'meeting.extract_decisions',
    { meeting_id: meetingId, refresh: options.refresh ?? false },
    token,
  );
}

export function draftFollowupSchedule(
  token: string,
  meetingId: string,
  options: RefreshOptions & { attendeeUserIds?: string[] } = {},
): Promise<MeetingFollowupResult> {
  const args: Record<string, unknown> = {
    meeting_id: meetingId,
    refresh: options.refresh ?? false,
  };
  if (options.attendeeUserIds !== undefined) {
    args.attendee_user_ids = options.attendeeUserIds;
  }
  return invokeAiTool<MeetingFollowupResult>(
    'meeting.draft_followup_schedule',
    args,
    token,
  );
}
