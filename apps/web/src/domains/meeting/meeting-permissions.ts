import { hasAnySystemRole, type AuthUser } from '@/src/domains/auth/auth-api';
import type { MeetingDetail, MeetingListItem } from './meeting-api';

const MEETING_ADMIN_ROLES = ['platform_admin', 'org_admin'] as const;

export function isOrganizer(
  user: AuthUser | null | undefined,
  meeting: Pick<MeetingDetail | MeetingListItem, 'organizer_id'> | null | undefined,
): boolean {
  if (!user || !meeting) return false;
  return user.id === meeting.organizer_id;
}

export function canEditMeeting(
  user: AuthUser | null | undefined,
  meeting: Pick<MeetingDetail | MeetingListItem, 'organizer_id'> | null | undefined,
): boolean {
  if (!user || !meeting) return false;
  if (hasAnySystemRole(user, MEETING_ADMIN_ROLES)) return true;
  return isOrganizer(user, meeting);
}
