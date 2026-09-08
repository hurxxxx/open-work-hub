import { createAuthUser } from '../../../../tests/fixtures/company';
import type { MeetingDetail } from './meeting-api';
import { describe, expect, it } from 'vitest';
import {
  canAttachToMeeting,
  canEditMeeting,
  canInviteAttendees,
  canRemoveAttachment,
} from './meeting-permissions';
const meeting: Pick<MeetingDetail, 'organizer_id' | 'attendees'> = {
  organizer_id: 'organizer',
  attendees: [
    {
      id: 'attendee-record-1',
      user_id: 'attendee',
      email: 'attendee@example.test',
      full_name: 'Attendee',
      role: 'required',
      response: 'accepted',
    },
  ],
};
const user = (id: string, system_roles: string[] = []) =>
  createAuthUser({ id, system_roles });
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
