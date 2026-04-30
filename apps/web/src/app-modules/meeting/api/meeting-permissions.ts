import type { AuthUser } from '@/src/platform/auth/auth-api';
import type { MeetingDetail, MeetingListItem } from './meeting-api';

export function isOrganizer(
  user: AuthUser | null | undefined,
  meeting: Pick<MeetingDetail | MeetingListItem, 'organizer_id'> | null | undefined,
): boolean {
  if (!user || !meeting) return false;
  return user.id === meeting.organizer_id;
}

export function isParticipant(
  user: AuthUser | null | undefined,
  meeting: Pick<MeetingDetail, 'organizer_id' | 'attendees'> | null | undefined,
): boolean {
  if (!user || !meeting) return false;
  if (user.id === meeting.organizer_id) return true;
  return meeting.attendees.some((attendee) => attendee.user_id === user.id);
}

/**
 * Can the caller edit meeting metadata (title, time, agenda, attendees,
 * delete the meeting itself)? Organizer + admins only.
 */
export function canEditMeeting(
  user: AuthUser | null | undefined,
  meeting: Pick<MeetingDetail | MeetingListItem, 'organizer_id'> | null | undefined,
): boolean {
  if (!user || !meeting) return false;
  return isOrganizer(user, meeting);
}

/**
 * Can the caller add attachments (tasks/docs/files) to the meeting?
 * Organizer + attendees + admins. The intent is that participants can
 * upload prep material before the meeting starts.
 */
export function canAttachToMeeting(
  user: AuthUser | null | undefined,
  meeting: Pick<MeetingDetail, 'organizer_id' | 'attendees'> | null | undefined,
): boolean {
  if (!user || !meeting) return false;
  return isParticipant(user, meeting);
}

/**
 * Can the caller invite additional attendees to the meeting?
 * Any current participant — organizer or existing attendee. Backed by
 * POST /meetings/{id}/attendees which is participant-permissioned.
 *
 * Removing or replacing attendees is still organizer-only — that goes
 * through the full edit modal + PATCH /meetings/{id}.
 */
export function canInviteAttendees(
  user: AuthUser | null | undefined,
  meeting: Pick<MeetingDetail, 'organizer_id' | 'attendees'> | null | undefined,
): boolean {
  if (!user || !meeting) return false;
  return isParticipant(user, meeting);
}

/**
 * Can the caller remove a specific attachment? Organizer, admins, or the
 * user who originally added it. Attendees cannot remove each other's
 * attachments.
 */
export function canRemoveAttachment(
  user: AuthUser | null | undefined,
  meeting: Pick<MeetingDetail, 'organizer_id'> | null | undefined,
  attachment: { added_by_id: string } | null | undefined,
): boolean {
  if (!user || !meeting || !attachment) return false;
  if (user.id === meeting.organizer_id) return true;
  return attachment.added_by_id === user.id;
}
