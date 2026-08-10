import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MeetingUser } from '../../api/meeting-api';
import { useMeetingUserSearch } from './useMeetingUserSearch';

const meetingApi = vi.hoisted(() => ({
  listMeetingUsers: vi.fn(),
}));

vi.mock('../../api/meeting-api', () => ({
  listMeetingUsers: meetingApi.listMeetingUsers,
}));

describe('useMeetingUserSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    meetingApi.listMeetingUsers.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('idles immediately for focused blank queries without calling the API', () => {
    const handlers = handlersForSearch();

    renderHook(() =>
      useMeetingUserSearch({
        ...handlers,
        focused: true,
        isOpen: true,
        query: '   ',
        token: 'token-1',
        workspaceSlug: 'workspace',
      }),
    );

    expect(handlers.onIdle).toHaveBeenCalledTimes(1);
    expect(handlers.onStarted).not.toHaveBeenCalled();
    expect(meetingApi.listMeetingUsers).not.toHaveBeenCalled();
  });

  it('debounces non-empty focused queries and publishes loaded users', async () => {
    const loaded = [user('user-1')];
    meetingApi.listMeetingUsers.mockResolvedValue(loaded);
    const handlers = handlersForSearch();

    renderHook(() =>
      useMeetingUserSearch({
        ...handlers,
        focused: true,
        isOpen: true,
        query: '  ada  ',
        token: 'token-1',
        workspaceSlug: 'workspace',
      }),
    );

    expect(handlers.onStarted).toHaveBeenCalledTimes(1);
    expect(meetingApi.listMeetingUsers).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(100);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(meetingApi.listMeetingUsers).toHaveBeenCalledWith('token-1', 'workspace', {
      q: 'ada',
      limit: 30,
    });
    expect(handlers.onLoaded).toHaveBeenCalledWith(loaded);
  });

  it('clears results through the failure handler when the API fails', async () => {
    meetingApi.listMeetingUsers.mockRejectedValue(new Error('failed'));
    const handlers = handlersForSearch();

    renderHook(() =>
      useMeetingUserSearch({
        ...handlers,
        focused: true,
        isOpen: true,
        query: 'ada',
        token: 'token-1',
        workspaceSlug: 'workspace',
      }),
    );

    await act(async () => {
      vi.advanceTimersByTime(100);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(handlers.onFailed).toHaveBeenCalledTimes(1);
  });

  it('cancels an old debounce when the query changes', async () => {
    meetingApi.listMeetingUsers.mockResolvedValue([]);
    const handlers = handlersForSearch();

    const { rerender } = renderHook(
      ({ query }) =>
        useMeetingUserSearch({
          ...handlers,
          focused: true,
          isOpen: true,
          query,
          token: 'token-1',
          workspaceSlug: 'workspace',
        }),
      { initialProps: { query: 'ada' } },
    );

    rerender({ query: 'grace' });
    await act(async () => {
      vi.advanceTimersByTime(100);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(meetingApi.listMeetingUsers).toHaveBeenCalledTimes(1);
    expect(meetingApi.listMeetingUsers).toHaveBeenCalledWith('token-1', 'workspace', {
      q: 'grace',
      limit: 30,
    });
  });
});

function user(id: string): MeetingUser {
  return {
    id,
    email: `${id}@example.test`,
    full_name: `User ${id}`,
  };
}

function handlersForSearch() {
  return {
    onIdle: vi.fn(),
    onFailed: vi.fn(),
    onLoaded: vi.fn(),
    onStarted: vi.fn(),
  };
}
