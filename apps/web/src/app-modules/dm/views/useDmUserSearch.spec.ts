import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DmUser } from '../api/dm-api';
import { type DmUserSearchLoader, useDmUserSearch } from './useDmUserSearch';

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

function user(overrides: Partial<DmUser> = {}): DmUser {
  return {
    id: 'u1',
    email: 'user@example.test',
    full_name: 'User One',
    display_name: null,
    ...overrides,
  };
}

async function advanceSearchDebounce(ms = 250): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe('useDmUserSearch', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('debounces trimmed user searches and can reset results', async () => {
    vi.useFakeTimers();
    const resultUser = user();
    const searchUsers = vi.fn<DmUserSearchLoader>(async () => [resultUser]);
    const { result } = renderHook(() =>
      useDmUserSearch({
        query: '  user  ',
        searchUsers,
        token: 'token-1',
      }),
    );

    await advanceSearchDebounce(249);

    expect(searchUsers).not.toHaveBeenCalled();

    await advanceSearchDebounce(1);

    expect(searchUsers).toHaveBeenCalledWith('token-1', 'user');
    expect(result.current.results).toEqual([resultUser]);
    expect(result.current.searching).toBe(false);

    act(() => {
      result.current.reset();
    });

    expect(result.current.results).toEqual([]);
    expect(result.current.searching).toBe(false);
  });

  it('filters excluded user ids after loading results', async () => {
    vi.useFakeTimers();
    const firstUser = user({ id: 'u1' });
    const secondUser = user({ id: 'u2', email: 'second@example.test' });
    const searchUsers = vi.fn<DmUserSearchLoader>(async () => [
      firstUser,
      secondUser,
    ]);
    const { result } = renderHook(() =>
      useDmUserSearch({
        excludeUserIds: new Set(['u1']),
        query: 'team',
        searchUsers,
        token: 'token-1',
      }),
    );

    await advanceSearchDebounce();

    expect(result.current.results).toEqual([secondUser]);
  });

  it('can include the current user in the global search', async () => {
    vi.useFakeTimers();
    const resultUser = user();
    const searchUsers = vi.fn<DmUserSearchLoader>(async () => [resultUser]);
    renderHook(() =>
      useDmUserSearch({
        query: 'team',
        searchUsers,
        token: 'token-1',
        includeCurrent: true,
      }),
    );

    await advanceSearchDebounce();

    expect(searchUsers).toHaveBeenCalledWith('token-1', 'team', {
      includeCurrent: true,
    });
  });

  it('ignores results from a cancelled stale search', async () => {
    vi.useFakeTimers();
    const olderSearch = deferred<DmUser[]>();
    const newerSearch = deferred<DmUser[]>();
    const searchUsers = vi
      .fn<DmUserSearchLoader>()
      .mockReturnValueOnce(olderSearch.promise)
      .mockReturnValueOnce(newerSearch.promise);
    const { result, rerender } = renderHook(
      ({ query }) =>
        useDmUserSearch({
          debounceMs: 10,
          query,
          searchUsers,
          token: 'token-1',
        }),
      { initialProps: { query: 'old' } },
    );

    await advanceSearchDebounce(10);
    rerender({ query: 'new' });
    await advanceSearchDebounce(10);
    await act(async () => {
      olderSearch.resolve([user({ id: 'old' })]);
    });

    expect(result.current.results).toEqual([]);

    const latestUser = user({ id: 'new' });
    await act(async () => {
      newerSearch.resolve([latestUser]);
    });

    expect(result.current.results).toEqual([latestUser]);
    expect(result.current.searching).toBe(false);
  });

  it('clears results and stops searching on load failure', async () => {
    vi.useFakeTimers();
    const resultUser = user();
    const searchUsers = vi
      .fn<DmUserSearchLoader>()
      .mockResolvedValueOnce([resultUser])
      .mockRejectedValueOnce(new Error('search failed'));
    const { result, rerender } = renderHook(
      ({ query }) =>
        useDmUserSearch({
          query,
          searchUsers,
          token: 'token-1',
        }),
      { initialProps: { query: 'ok' } },
    );

    await advanceSearchDebounce();

    expect(result.current.results).toEqual([resultUser]);

    rerender({ query: 'fail' });
    await advanceSearchDebounce();

    expect(result.current.results).toEqual([]);
    expect(result.current.searching).toBe(false);
  });
});
