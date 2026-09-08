import { describe, expect, it } from 'vitest';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import {
  canAttachToMeeting,
  canEditMeeting,
  canInviteAttendees,
  canRemoveAttachment,
} from './meeting-permissions';
const meeting = {
  organizer_id: 'organizer',
  attendees: [{ user_id: 'attendee' }],
};
const user = (id: string, system_roles: string[] = []) =>
  ({ id, system_roles }) as AuthUser;
describe('meeting business roles', () => {
  it('keeps metadata changes organizer-only even for a platform administrator', () => {
    expect(canEditMeeting(user('organizer'), meeting)).toBe(true);
    expect(canEditMeeting(user('attendee'), meeting)).toBe(false);
    expect(
      canEditMeeting(user('administrator', ['platform_admin']), meeting),
    ).toBe(false);
  });
  it('permits attachment and invitation for explicit participants only', () => {
    for (const check of [canAttachToMeeting, canInviteAttendees]) {
      expect(check(user('organizer'), meeting)).toBe(true);
      expect(check(user('attendee'), meeting)).toBe(true);
      expect(check(user('administrator', ['platform_admin']), meeting)).toBe(
        false,
      );
      expect(check(null, meeting)).toBe(false);
    }
  });
  it('does not give administrators attachment deletion rights', () => {
    const attachment = { added_by_id: 'attendee' };
    expect(canRemoveAttachment(user('attendee'), meeting, attachment)).toBe(
      true,
    );
    expect(canRemoveAttachment(user('organizer'), meeting, attachment)).toBe(
      true,
    );
    expect(
      canRemoveAttachment(
        user('administrator', ['platform_admin']),
        meeting,
        attachment,
      ),
    ).toBe(false);
  });
});
