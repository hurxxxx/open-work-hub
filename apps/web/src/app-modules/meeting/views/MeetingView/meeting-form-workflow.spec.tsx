import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MeetingDetail, MeetingUser } from '../../api/meeting-api';
import {
  useMeetingCreateFormWorkflow,
  useMeetingEditFormWorkflow,
  type MeetingFormApiAdapter,
} from './meeting-form-workflow';

const authState = vi.hoisted(() => ({
  token: 'token-1' as string | null,
  user: {
    id: 'current-user',
    time_zone: 'Asia/Seoul',
  } as { id: string; time_zone: string } | null,
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => authState,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string; message?: string }) =>
      options?.name ? `${key}:${options.name}:${options.message ?? ''}` : key,
  }),
}));

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

function api(
  overrides: Partial<MeetingFormApiAdapter> = {},
): MeetingFormApiAdapter {
  return {
    createMeeting: vi.fn().mockResolvedValue(meeting({ id: 'created-1' })),
    updateMeeting: vi
      .fn()
      .mockResolvedValue(meeting({ id: 'meeting-1', title: 'Updated' })),
    uploadMeetingFile: vi.fn().mockResolvedValue(meeting({ id: 'created-1' })),
    listMeetingUsers: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
}

function renderCreateWorkflow(
  options: {
    api?: MeetingFormApiAdapter;
    onCreated?: (meetingId: string) => void;
  } = {},
) {
  const onCreated = options.onCreated ?? vi.fn();
  const initialRange = {
    start: new Date(2026, 4, 30, 9, 0),
    end: new Date(2026, 4, 30, 10, 0),
    allDay: false,
  };
  const rendered = renderHook(() =>
    useMeetingCreateFormWorkflow({
      isOpen: true,
      onCreated,
      initialRange,
      api: options.api ?? api(),
    }),
  );
  return { ...rendered, onCreated };
}

describe('meeting form workflow', () => {
  beforeEach(() => {
    authState.token = 'token-1';
    authState.user = { id: 'current-user', time_zone: 'Asia/Seoul' };
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('initializes create state and runs focused debounced user search', async () => {
    const searchApi = api({
      listMeetingUsers: vi.fn().mockResolvedValue([user('candidate')]),
    });
    const { result } = renderCreateWorkflow({ api: searchApi });

    expect(result.current.state.attendees).toEqual([
      { user_id: 'current-user', role: 'required' },
    ]);

    act(() => {
      result.current.actions.patch({
        userQuery: '  ada  ',
        userQueryFocused: true,
      });
    });

    expect(result.current.state.usersLoading).toBe(true);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 130));
    });

    expect(searchApi.listMeetingUsers).toHaveBeenCalledWith('token-1', {
      q: 'ada',
      limit: 30,
    });
    await waitFor(() => {
      expect(result.current.state.users).toEqual([user('candidate')]);
    });
  });

  it('submits create payloads with trimmed fields and picked work ids', async () => {
    const createApi = api();
    const { onCreated, result } = renderCreateWorkflow({ api: createApi });

    act(() => {
      result.current.actions.patch({
        title: '  Planning  ',
        agenda: '  Agenda  ',
        pickedTasks: [{ id: 'task-1', title: 'Task', reference: 'T-1' }],
        pickedDocs: [{ id: 'doc-1', title: 'Doc' }],
      });
    });
    await act(async () => {
      await result.current.actions.submit();
    });

    expect(createApi.createMeeting).toHaveBeenCalledWith(
      'token-1',
      expect.objectContaining({
        title: 'Planning',
        agenda: 'Agenda',
        attendees: [{ user_id: 'current-user', role: 'required' }],
        task_ids: ['task-1'],
        doc_ids: ['doc-1'],
      }),
    );
    expect(onCreated).toHaveBeenCalledWith('created-1');
  });

  it('keeps create modal state open on partial file upload failures', async () => {
    const successful = new File(['ok'], 'ok.txt', { type: 'text/plain' });
    const failed = new File(['bad'], 'bad.txt', { type: 'text/plain' });
    const createApi = api({
      uploadMeetingFile: vi.fn((_token, _meetingId, file: File) =>
        file.name === 'bad.txt'
          ? Promise.reject(new Error('virus scan failed'))
          : Promise.resolve(meeting({ id: 'created-1' })),
      ),
    });
    const { onCreated, result } = renderCreateWorkflow({ api: createApi });

    act(() => {
      result.current.actions.patch({
        title: 'Planning',
        pickedFiles: [successful, failed],
      });
    });
    await act(async () => {
      await result.current.actions.submit();
    });

    expect(onCreated).not.toHaveBeenCalled();
    expect(result.current.state.createdMeetingId).toBe('created-1');
    expect(result.current.state.error).toBe('meeting.create.partialFailed');
    expect(result.current.state.partialFailures).toEqual([
      'meeting.create.fileFailure:bad.txt:virus scan failed',
    ]);
    expect(result.current.state.pickedFiles).toEqual([failed]);
    expect(result.current.state.submitting).toBe(false);
  });

  it('validates edit dates and preserves current agenda whitespace on update', async () => {
    const editApi = api();
    const onSaved = vi.fn();
    const currentMeeting = meeting();
    const { result } = renderHook(() =>
      useMeetingEditFormWorkflow({
        isOpen: true,
        meeting: currentMeeting,
        onSaved,
        api: editApi,
      }),
    );

    act(() => {
      result.current.actions.patch({
        endAt: '2026-05-30T00:00',
      });
    });
    await act(async () => {
      await result.current.actions.submit();
    });

    expect(editApi.updateMeeting).not.toHaveBeenCalled();
    expect(result.current.state.error).toBe('meeting.form.endAfterStart');

    act(() => {
      result.current.actions.patch({
        title: '  Updated title  ',
        agenda: '  Keep spacing  ',
        endAt: '2026-05-30T11:00',
      });
    });
    await act(async () => {
      await result.current.actions.submit();
    });

    expect(editApi.updateMeeting).toHaveBeenCalledWith(
      'token-1',
      'meeting-1',
      expect.objectContaining({
        title: 'Updated title',
        agenda: '  Keep spacing  ',
      }),
    );
    expect(onSaved).toHaveBeenCalled();
  });
});
