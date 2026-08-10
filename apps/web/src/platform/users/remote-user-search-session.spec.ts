import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  type RemoteUserSearchLoader,
  useRemoteUserSearchSession,
} from './remote-user-search-session';

type TestUser = {
  id: string;
};

type Deferred<T> = {
  promise: Promise<T>;
  reject: (reason?: unknown) => void;
  resolve: (value: T) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => undefined;
  let reject: (reason?: unknown) => void = () => undefined;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, reject, resolve };
}

async function advanceSearchDebounce(ms = 250): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function user(id: string): TestUser {
  return { id };
}

describe('useRemoteUserSearchSession', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('idles focused blank queries without calling the loader', () => {
    const searchUsers = vi.fn<RemoteUserSearchLoader<TestUser>>();
    const onIdle = vi.fn();
    const { result } = renderHook(() =>
      useRemoteUserSearchSession({
        onIdle,
        query: '   ',
        searchUsers,
        token: 'token-1',
      }),
    );

    expect(result.current.status).toBe('idle');
    expect(result.current.loading).toBe(false);
    expect(result.current.results).toEqual([]);
    expect(onIdle).toHaveBeenCalledTimes(1);
    expect(searchUsers).not.toHaveBeenCalled();
  });

  it('debounces trimmed remote searches and publishes loaded results', async () => {
    const loaded = [user('ada')];
    const searchUsers = vi.fn<RemoteUserSearchLoader<TestUser>>()
      .mockResolvedValue(loaded);
    const onStarted = vi.fn();
    const onLoaded = vi.fn();
    const { result } = renderHook(() =>
      useRemoteUserSearchSession({
        onLoaded,
        onStarted,
        query: '  ada  ',
        searchUsers,
        token: 'token-1',
      }),
    );

    expect(result.current.status).toBe('searching');
    expect(result.current.loading).toBe(true);
    expect(onStarted).toHaveBeenCalledTimes(1);
    expect(searchUsers).not.toHaveBeenCalled();

    await advanceSearchDebounce(249);

    expect(searchUsers).not.toHaveBeenCalled();

    await advanceSearchDebounce(1);

    expect(searchUsers).toHaveBeenCalledTimes(1);
    expect(searchUsers.mock.calls[0]?.[0]).toMatchObject({
      query: 'ada',
      token: 'token-1',
    });
    expect(result.current.status).toBe('loaded');
    expect(result.current.loading).toBe(false);
    expect(result.current.results).toEqual(loaded);
    expect(onLoaded).toHaveBeenCalledWith(loaded);
  });

  it('clears results and records failure state when the loader rejects', async () => {
    const error = new Error('failed');
    const searchUsers = vi.fn<RemoteUserSearchLoader<TestUser>>()
      .mockResolvedValueOnce([user('loaded')])
      .mockRejectedValueOnce(error);
    const onFailed = vi.fn();
    const { result, rerender } = renderHook(
      ({ query }) =>
        useRemoteUserSearchSession({
          onFailed,
          query,
          searchUsers,
          token: 'token-1',
        }),
      { initialProps: { query: 'loaded' } },
    );

    await advanceSearchDebounce();

    expect(result.current.results).toEqual([user('loaded')]);

    rerender({ query: 'fail' });
    await advanceSearchDebounce();

    expect(result.current.status).toBe('failed');
    expect(result.current.failed).toBe(true);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe(error);
    expect(result.current.results).toEqual([]);
    expect(onFailed).toHaveBeenCalledWith(error);
  });

  it('aborts and suppresses stale search results when the query changes', async () => {
    const olderSearch = deferred<readonly TestUser[]>();
    const newerSearch = deferred<readonly TestUser[]>();
    const searchUsers = vi.fn<RemoteUserSearchLoader<TestUser>>()
      .mockReturnValueOnce(olderSearch.promise)
      .mockReturnValueOnce(newerSearch.promise);
    const onLoaded = vi.fn();
    const { result, rerender } = renderHook(
      ({ query }) =>
        useRemoteUserSearchSession({
          debounceMs: 10,
          onLoaded,
          query,
          searchUsers,
          token: 'token-1',
        }),
      { initialProps: { query: 'old' } },
    );

    await advanceSearchDebounce(10);

    const olderSignal = searchUsers.mock.calls[0]?.[0].signal;

    rerender({ query: 'new' });
    await advanceSearchDebounce(10);

    expect(olderSignal?.aborted).toBe(true);

    await act(async () => {
      olderSearch.resolve([user('old')]);
    });

    expect(result.current.results).toEqual([]);
    expect(onLoaded).not.toHaveBeenCalledWith([user('old')]);

    await act(async () => {
      newerSearch.resolve([user('new')]);
    });

    expect(result.current.results).toEqual([user('new')]);
    expect(onLoaded).toHaveBeenCalledWith([user('new')]);
  });

  it('clears state without notifying blank-query idle when token or enabled gates close', async () => {
    const searchUsers = vi.fn<RemoteUserSearchLoader<TestUser>>()
      .mockResolvedValue([user('loaded')]);
    const onIdle = vi.fn();
    const { result, rerender } = renderHook(
      ({ enabled, token }) =>
        useRemoteUserSearchSession({
          enabled,
          onIdle,
          query: 'ada',
          searchUsers,
          token,
        }),
      { initialProps: { enabled: true, token: 'token-1' as string | null } },
    );

    await advanceSearchDebounce();

    expect(result.current.results).toEqual([user('loaded')]);

    rerender({ enabled: false, token: 'token-1' });

    expect(result.current.status).toBe('idle');
    expect(result.current.results).toEqual([]);
    expect(onIdle).not.toHaveBeenCalled();

    rerender({ enabled: true, token: null });

    expect(result.current.status).toBe('idle');
    expect(searchUsers).toHaveBeenCalledTimes(1);
  });

  it('reset clears local state and invalidates in-flight searches', async () => {
    const pendingSearch = deferred<readonly TestUser[]>();
    const searchUsers = vi.fn<RemoteUserSearchLoader<TestUser>>()
      .mockReturnValue(pendingSearch.promise);
    const { result } = renderHook(() =>
      useRemoteUserSearchSession({
        debounceMs: 10,
        query: 'ada',
        searchUsers,
        token: 'token-1',
      }),
    );

    await advanceSearchDebounce(10);

    act(() => {
      result.current.reset();
    });

    await act(async () => {
      pendingSearch.resolve([user('ada')]);
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.results).toEqual([]);
    expect(result.current.loading).toBe(false);
  });
});
