import { describe, expect, it, vi } from 'vitest';

import type { MeetingDetail, MeetingUser } from '../../api/meeting-api';
import {
  createInitialMeetingEditState,
  createInitialMeetingState,
} from './meeting-form-model';
import {
  submitMeetingCreateForm,
  submitMeetingEditForm,
  type MeetingFormSubmissionMessages,
  type MeetingFormSubmissionPorts,
} from './meeting-form-submission';

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
    agenda: '  Existing agenda  ',
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

function ports(
  overrides: Partial<MeetingFormSubmissionPorts> = {},
): MeetingFormSubmissionPorts {
  return {
    createMeeting: vi.fn().mockResolvedValue(meeting({ id: 'created-1' })),
    updateMeeting: vi
      .fn()
      .mockResolvedValue(meeting({ id: 'meeting-1', title: 'Updated' })),
    uploadMeetingFile: vi.fn().mockResolvedValue(meeting({ id: 'created-1' })),
    ...overrides,
  };
}

const messages: MeetingFormSubmissionMessages = {
  endAfterStart: 'End must be after start.',
  createFailed: 'Create failed.',
  editFailed: 'Edit failed.',
  partialUploadFailed: 'Some files failed.',
  fileFailureDefault: 'Upload failed.',
  fileFailure: ({ name, message }) => `${name}: ${message}`,
};

describe('meeting form submission', () => {
  it('returns validation failure without calling ports when dates are invalid', async () => {
    const fakePorts = ports();
    const state = {
      ...createInitialMeetingState(
        null,
        'current-user',
        new Date(2026, 4, 30, 8, 0),
      ),
      title: 'Planning',
      startAt: '2026-05-30T10:00',
      endAt: '2026-05-30T09:00',
    };

    const result = await submitMeetingCreateForm({
      token: 'token-1',
      state,
      ports: fakePorts,
      messages,
    });

    expect(result).toEqual({
      status: 'validation_failed',
      error: 'End must be after start.',
    });
    expect(fakePorts.createMeeting).not.toHaveBeenCalled();
    expect(fakePorts.uploadMeetingFile).not.toHaveBeenCalled();
  });

  it('trims create payload and returns the created result', async () => {
    const fakePorts = ports();
    const state = {
      ...createInitialMeetingState(
        null,
        'current-user',
        new Date(2026, 4, 30, 8, 0),
      ),
      title: '  Planning  ',
      agenda: '  Agenda  ',
      attendees: [{ user_id: 'current-user', role: 'required' as const }],
      pickedAttendeeUsers: [user('current-user')],
      pickedTasks: [{ id: 'task-1', title: 'Task', reference: 'T-1' }],
      pickedDocs: [{ id: 'doc-1', title: 'Doc' }],
      startAt: '2026-05-30T09:00',
      endAt: '2026-05-30T10:00',
    };

    const result = await submitMeetingCreateForm({
      token: 'token-1',
      state,
      ports: fakePorts,
      messages,
    });

    expect(fakePorts.createMeeting).toHaveBeenCalledWith(
      'token-1',
      expect.objectContaining({
        title: 'Planning',
        agenda: 'Agenda',
        attendees: [{ user_id: 'current-user', role: 'required' }],
        task_ids: ['task-1'],
        doc_ids: ['doc-1'],
      }),
    );
    expect(result).toEqual({
      status: 'created',
      meeting: expect.objectContaining({ id: 'created-1' }),
    });
  });

  it('returns created meeting id, remaining files, and failures after partial upload failure', async () => {
    const successful = new File(['ok'], 'ok.txt', { type: 'text/plain' });
    const failed = new File(['bad'], 'bad.txt', { type: 'text/plain' });
    const fakePorts = ports({
      uploadMeetingFile: vi.fn((_token, _meetingId, file: File) =>
        file.name === 'bad.txt'
          ? Promise.reject(new Error('virus scan failed'))
          : Promise.resolve(meeting({ id: 'created-1' })),
      ),
    });
    const state = {
      ...createInitialMeetingState(
        null,
        'current-user',
        new Date(2026, 4, 30, 8, 0),
      ),
      title: 'Planning',
      startAt: '2026-05-30T09:00',
      endAt: '2026-05-30T10:00',
      pickedFiles: [successful, failed],
    };

    const result = await submitMeetingCreateForm({
      token: 'token-1',
      state,
      ports: fakePorts,
      messages,
    });

    expect(result).toEqual({
      status: 'partial_upload_failed',
      createdMeetingId: 'created-1',
      error: 'Some files failed.',
      failures: ['bad.txt: virus scan failed'],
      remainingFiles: [failed],
    });
  });

  it('preserves edit agenda whitespace while trimming title', async () => {
    const fakePorts = ports();
    const state = {
      ...createInitialMeetingEditState(meeting()),
      title: '  Updated title  ',
      agenda: '  Keep spacing  ',
      startAt: '2026-05-30T09:00',
      endAt: '2026-05-30T10:00',
    };

    const result = await submitMeetingEditForm({
      token: 'token-1',
      meetingId: 'meeting-1',
      state,
      ports: fakePorts,
      messages,
    });

    expect(fakePorts.updateMeeting).toHaveBeenCalledWith(
      'token-1',
      'meeting-1',
      expect.objectContaining({
        title: 'Updated title',
        agenda: '  Keep spacing  ',
      }),
    );
    expect(result).toEqual({
      status: 'saved',
      meeting: expect.objectContaining({ id: 'meeting-1' }),
    });
  });

  it('uses fallback messages for unknown thrown values', async () => {
    const createPorts = ports({
      createMeeting: vi.fn().mockRejectedValue('network down'),
    });
    const uploadPorts = ports({
      uploadMeetingFile: vi.fn().mockRejectedValue({ reason: 'blocked' }),
    });
    const editPorts = ports({
      updateMeeting: vi.fn().mockRejectedValue(null),
    });
    const createState = {
      ...createInitialMeetingState(
        null,
        'current-user',
        new Date(2026, 4, 30, 8, 0),
      ),
      title: 'Planning',
      startAt: '2026-05-30T09:00',
      endAt: '2026-05-30T10:00',
    };
    const uploadState = {
      ...createState,
      pickedFiles: [new File(['bad'], 'bad.txt', { type: 'text/plain' })],
    };
    const editState = {
      ...createInitialMeetingEditState(meeting()),
      title: 'Planning',
      startAt: '2026-05-30T09:00',
      endAt: '2026-05-30T10:00',
    };

    await expect(
      submitMeetingCreateForm({
        token: 'token-1',
        state: createState,
        ports: createPorts,
        messages,
      }),
    ).resolves.toEqual({ status: 'failed', error: 'Create failed.' });
    await expect(
      submitMeetingCreateForm({
        token: 'token-1',
        state: uploadState,
        ports: uploadPorts,
        messages,
      }),
    ).resolves.toEqual({
      status: 'partial_upload_failed',
      createdMeetingId: 'created-1',
      error: 'Some files failed.',
      failures: ['bad.txt: Upload failed.'],
      remainingFiles: uploadState.pickedFiles,
    });
    await expect(
      submitMeetingEditForm({
        token: 'token-1',
        meetingId: 'meeting-1',
        state: editState,
        ports: editPorts,
        messages,
      }),
    ).resolves.toEqual({ status: 'failed', error: 'Edit failed.' });
  });
});
