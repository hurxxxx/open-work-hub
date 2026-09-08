import { describe, expect, it } from 'vitest';

import type { MeetingDetail, MeetingUser } from '../../api/meeting-api';
import {
  buildCreateMeetingPayload,
  buildUpdateMeetingPayload,
  buildUserLookup,
  createInitialMeetingEditState,
  createInitialMeetingState,
  filterCreateCandidateUsers,
  filterEditCandidateUsers,
  formatFileSize,
  getVisibleCreateAttendees,
  getVisibleEditAttendees,
  isEndAfterStart,
  mapAvailabilityUsers,
  projectMeetingCreateForm,
  projectMeetingEditForm,
  rangeToInputs,
  removeAttendeeFromForm,
  summarizeFileUploadResults,
} from './meeting-form-model';

function user(id: string, fullName = `User ${id}`): MeetingUser {
  return {
    id,
    email: `${id}@example.test`,
    full_name: fullName,
  } as MeetingUser;
}

function meeting(overrides: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    id: 'meeting-1',
    title: 'Planning',
    agenda: 'Roadmap',
    start_at: '2026-05-30T01:00:00',
    end_at: '2026-05-30T02:00:00',
    organizer_id: 'organizer',
    attendees: [
      {
        user_id: 'organizer',
        role: 'required',
        email: 'organizer@example.test',
        full_name: 'Organizer',
      },
      {
        user_id: 'guest',
        role: 'optional',
        email: 'guest@example.test',
        full_name: 'Guest',
      },
    ],
    task_links: [],
    doc_links: [],
    file_attachments: [],
    recordings: [],
    whiteboard_link: null,
    active_recording_lock: null,
    ...overrides,
  } as MeetingDetail;
}

function fileLike(name: string, size: number, lastModified: number) {
  return { name, size, lastModified } as File;
}

describe('meeting form model', () => {
  it('builds create defaults from the next rounded hour and includes the current user', () => {
    const state = createInitialMeetingState(
      null,
      'user-1',
      new Date(2026, 4, 30, 10, 37),
    );

    expect(state.startAt).toBe('2026-05-30T11:00');
    expect(state.endAt).toBe('2026-05-30T12:00');
    expect(state.attendees).toEqual([{ user_id: 'user-1', role: 'required' }]);
    expect(state.partialFailures).toEqual([]);
  });

  it('converts all-day slot selections to a one-hour 09:00 meeting', () => {
    expect(
      rangeToInputs({
        start: new Date(2026, 4, 30, 0, 0),
        end: new Date(2026, 4, 31, 0, 0),
        allDay: true,
      }),
    ).toEqual({
      start: '2026-05-30T09:00',
      end: '2026-05-30T10:00',
    });
  });

  it('initializes edit state from meeting details and known attendee users', () => {
    const state = createInitialMeetingEditState(meeting());

    expect(state.title).toBe('Planning');
    expect(state.agenda).toBe('Roadmap');
    expect(state.attendees).toEqual([
      { user_id: 'organizer', role: 'required' },
      { user_id: 'guest', role: 'optional' },
    ]);
    expect(state.knownUsers).toEqual([
      {
        id: 'organizer',
        email: 'organizer@example.test',
        full_name: 'Organizer',
      },
      { id: 'guest', email: 'guest@example.test', full_name: 'Guest' },
    ]);
  });

  it('filters search candidates and hides auto-included users for create and organizer edit', () => {
    const candidates = [
      user('current'),
      user('selected'),
      user('other'),
      user('organizer'),
    ];
    const attendees = [
      { user_id: 'current', role: 'required' },
      { user_id: 'selected', role: 'required' },
    ] as const;

    expect(
      filterCreateCandidateUsers(candidates, [...attendees], 'current').map(
        (item) => item.id,
      ),
    ).toEqual(['other', 'organizer']);
    expect(
      getVisibleCreateAttendees([...attendees], 'current').map(
        (item) => item.user_id,
      ),
    ).toEqual(['selected']);

    expect(
      filterEditCandidateUsers(
        candidates,
        [{ user_id: 'selected', role: 'required' }],
        'organizer',
        'organizer',
      ).map((item) => item.id),
    ).toEqual(['current', 'other']);
    expect(
      getVisibleEditAttendees(
        [
          { user_id: 'organizer', role: 'required' },
          { user_id: 'guest', role: 'optional' },
        ],
        'organizer',
        'organizer',
      ).map((item) => item.user_id),
    ).toEqual(['guest']);
  });

  it('maps availability users from known or searched users and falls back to ids', () => {
    const lookup = buildUserLookup([user('known', 'Known')], [user('search')]);

    expect(
      mapAvailabilityUsers(
        [
          { user_id: 'known', role: 'required' },
          { user_id: 'missing', role: 'optional' },
        ],
        lookup,
      ),
    ).toEqual([
      { id: 'known', email: 'known@example.test', full_name: 'Known' },
      { id: 'missing', email: '', full_name: 'missing' },
    ]);
  });

  it('projects create form candidate, visibility, attachment, and submit state', () => {
    const state = {
      ...createInitialMeetingState(
        null,
        'current',
        new Date(2026, 4, 30, 10, 0),
      ),
      title: '  Planning  ',
      attendees: [
        { user_id: 'current', role: 'required' as const },
        { user_id: 'selected', role: 'required' as const },
      ],
      pickedAttendeeUsers: [user('selected', 'Selected User')],
      users: [user('current'), user('selected'), user('candidate')],
      pickedTasks: [{ id: 'task-1', title: 'Task', reference: 'T-1' }],
      pickedDocs: [{ id: 'doc-1', title: 'Doc' }],
    };

    const projection = projectMeetingCreateForm(state, 'current');

    expect(projection.canSubmit).toBe(true);
    expect(projection.filteredUsers.map((item) => item.id)).toEqual([
      'candidate',
    ]);
    expect(projection.visibleAttendees.map((item) => item.user_id)).toEqual([
      'selected',
    ]);
    expect(projection.availabilityUsers).toEqual([
      {
        id: 'selected',
        email: 'selected@example.test',
        full_name: 'User selected',
      },
    ]);
    expect(projection.pickedTaskIds).toEqual(['task-1']);
    expect(projection.pickedDocIds).toEqual(['doc-1']);
  });

  it('projects edit form organizer locks, candidates, and submit state', () => {
    const state = {
      ...createInitialMeetingEditState(meeting()),
      title: '  ',
      users: [user('organizer'), user('guest'), user('candidate')],
    };

    const projection = projectMeetingEditForm(state, 'organizer', 'organizer');

    expect(projection.canSubmit).toBe(false);
    expect(projection.lockedOrganizerIds.has('organizer')).toBe(true);
    expect(projection.filteredUsers.map((item) => item.id)).toEqual([
      'candidate',
    ]);
    expect(projection.visibleAttendees.map((item) => item.user_id)).toEqual([
      'guest',
    ]);
    expect(projection.availabilityUsers.map((item) => item.id)).toEqual([
      'guest',
    ]);
  });

  it('builds create and update payloads with existing trimming behavior', () => {
    const createState = createInitialMeetingState(
      {
        start: new Date(2026, 4, 30, 10, 0),
        end: new Date(2026, 4, 30, 11, 0),
        allDay: false,
      },
      'user-1',
    );

    expect(
      buildCreateMeetingPayload({
        ...createState,
        title: '  Create title  ',
        agenda: '  Create agenda  ',
        pickedTasks: [{ id: 'task-1', title: 'Task', reference: 'T-1' }],
        pickedDocs: [{ id: 'doc-1', title: 'Doc' }],
      }),
    ).toMatchObject({
      title: 'Create title',
      agenda: 'Create agenda',
      attendees: [{ user_id: 'user-1', role: 'required' }],
      task_ids: ['task-1'],
      doc_ids: ['doc-1'],
    });

    expect(
      buildUpdateMeetingPayload({
        ...createInitialMeetingEditState(meeting()),
        title: '  Update title  ',
        agenda: '  Update agenda  ',
      }),
    ).toMatchObject({
      title: 'Update title',
      agenda: '  Update agenda  ',
    });
  });

  it('keeps locked attendees and summarizes partial file upload failures', () => {
    const attendees = [
      { user_id: 'organizer', role: 'required' },
      { user_id: 'guest', role: 'optional' },
    ] as const;
    const first = fileLike('first.txt', 10, 1);
    const second = fileLike('second.txt', 20, 2);

    expect(
      removeAttendeeFromForm(
        [...attendees],
        'organizer',
        new Set(['organizer']),
      ),
    ).toEqual(attendees);
    expect(
      removeAttendeeFromForm([...attendees], 'guest', new Set(['organizer'])),
    ).toEqual([{ user_id: 'organizer', role: 'required' }]);
    expect(
      summarizeFileUploadResults(
        [first, second],
        [
          { file: first, failure: null },
          { file: second, failure: 'second failed' },
        ],
      ),
    ).toEqual({
      failures: ['second failed'],
      remainingFiles: [second],
    });
  });

  it('formats file sizes and validates increasing datetime ranges', () => {
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(1536)).toBe('1.5 KB');
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MB');
    expect(isEndAfterStart('2026-05-30T10:00', '2026-05-30T10:01')).toBe(true);
    expect(isEndAfterStart('2026-05-30T10:00', '2026-05-30T10:00')).toBe(false);
  });
});
