import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import { type AppsBootstrapResponse, useAppsBootstrap } from './apps-api';

vi.mock('@/src/platform/api/client', () => ({
  apiFetchJsonWithMappedError: vi.fn(),
}));

function appsBootstrap(userId: string): AppsBootstrapResponse {
  return {
    apps: [],
    global_route_app_ids: [],
    app_bar_categories: [],
    personal_tool_app_ids: [],
    principal: {
      kind: 'user',
      scope: 'personal',
      source: 'test',
      user_id: userId,
    },
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

describe('company app bootstrap', () => {
  beforeEach(() => {
    vi.mocked(apiFetchJsonWithMappedError).mockReset();
  });

  it('masks principal A synchronously while principal B is loading', async () => {
    const pendingB = deferred<AppsBootstrapResponse>();
    vi.mocked(apiFetchJsonWithMappedError).mockImplementation((url) => {
      if (vi.mocked(apiFetchJsonWithMappedError).mock.calls.length === 1) {
        return Promise.resolve(appsBootstrap('a'));
      }
      return pendingB.promise;
    });
    const { result, rerender } = renderHook(
      ({ slug }) => useAppsBootstrap('token', slug),
      { initialProps: { slug: 'a' } },
    );

    await waitFor(() =>
      expect(result.current.data?.principal.user_id).toBe('a'),
    );
    rerender({ slug: 'b' });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(true);

    await act(async () => pendingB.resolve(appsBootstrap('b')));
    await waitFor(() =>
      expect(result.current.data?.principal.user_id).toBe('b'),
    );
  });

  it('masks the previous principal and clears state when identity is missing', async () => {
    const pendingY = deferred<AppsBootstrapResponse>();
    vi.mocked(apiFetchJsonWithMappedError)
      .mockResolvedValueOnce(appsBootstrap('user-x'))
      .mockImplementationOnce(() => pendingY.promise);
    const { result, rerender } = renderHook(
      ({ principalId }: { principalId: string | null }) =>
        useAppsBootstrap('token', principalId),
      { initialProps: { principalId: 'user-x' } },
    );

    await waitFor(() =>
      expect(result.current.data?.principal.user_id).toBe('user-x'),
    );
    rerender({ principalId: 'user-y' });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);

    rerender({ principalId: null });
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('retains same-scope data during an explicit reload', async () => {
    const reload = deferred<AppsBootstrapResponse>();
    vi.mocked(apiFetchJsonWithMappedError)
      .mockResolvedValueOnce(appsBootstrap('a'))
      .mockImplementationOnce(() => reload.promise);
    const { result } = renderHook(() => useAppsBootstrap('token', 'a'));

    await waitFor(() =>
      expect(result.current.data?.principal.user_id).toBe('a'),
    );
    act(() => result.current.reload());

    await waitFor(() => expect(result.current.loading).toBe(true));
    expect(result.current.data?.principal.user_id).toBe('a');

    await act(async () => reload.resolve(appsBootstrap('a')));
    await waitFor(() => expect(result.current.loading).toBe(false));
  });
});
