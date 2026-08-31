import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import {
  type AppsBootstrapResponse,
  type WorkspaceBootstrapResponse,
  useAppsBootstrap,
  useWorkspaceBootstrap,
} from './workspaces-api';

vi.mock('@/src/platform/api/client', () => ({
  apiFetchJsonWithMappedError: vi.fn(),
}));

function workspaceBootstrap(slug: string): WorkspaceBootstrapResponse {
  return {
    workspace: {
      id: `workspace-${slug}`,
      slug,
      name: slug,
      role: 'member',
    },
    apps: [],
    nav: [],
  };
}

function appsBootstrap(userId: string): AppsBootstrapResponse {
  return {
    apps: [],
    global_route_app_ids: [],
    app_bar_categories: [],
    personal_tool_app_ids: [],
    principal: {
      kind: 'user',
      scope: 'personal',
      workspace_id: null,
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

describe('scoped bootstrap hooks', () => {
  beforeEach(() => {
    vi.mocked(apiFetchJsonWithMappedError).mockReset();
  });

  it('masks workspace A synchronously while workspace B is loading', async () => {
    const pendingB = deferred<WorkspaceBootstrapResponse>();
    vi.mocked(apiFetchJsonWithMappedError).mockImplementation((url) => {
      if (String(url).includes('/workspaces/a/')) {
        return Promise.resolve(workspaceBootstrap('a'));
      }
      return pendingB.promise;
    });
    const { result, rerender } = renderHook(
      ({ slug }) => useWorkspaceBootstrap('token', 'user-1', slug),
      { initialProps: { slug: 'a' } },
    );

    await waitFor(() => expect(result.current.data?.workspace.slug).toBe('a'));
    rerender({ slug: 'b' });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(true);

    await act(async () => pendingB.resolve(workspaceBootstrap('b')));
    await waitFor(() => expect(result.current.data?.workspace.slug).toBe('b'));
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
    const reload = deferred<WorkspaceBootstrapResponse>();
    vi.mocked(apiFetchJsonWithMappedError)
      .mockResolvedValueOnce(workspaceBootstrap('a'))
      .mockImplementationOnce(() => reload.promise);
    const { result } = renderHook(() =>
      useWorkspaceBootstrap('token', 'user-1', 'a'),
    );

    await waitFor(() => expect(result.current.data?.workspace.slug).toBe('a'));
    act(() => result.current.reload());

    await waitFor(() => expect(result.current.loading).toBe(true));
    expect(result.current.data?.workspace.slug).toBe('a');

    await act(async () => reload.resolve(workspaceBootstrap('a')));
    await waitFor(() => expect(result.current.loading).toBe(false));
  });
});
