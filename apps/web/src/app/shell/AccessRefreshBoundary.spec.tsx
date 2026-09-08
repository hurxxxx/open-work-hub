import { act } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  AUTH_ACCESS_CHANGE_REASONS,
  AUTH_REALTIME_EVENT_TYPES,
} from '@open-work-hub/contracts/auth';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import { AccessRefreshBoundary } from './AccessRefreshBoundary';
import {
  ShellRealtimeProvider,
  type ShellRealtimeContextValue,
  type ShellRealtimeListener,
} from './shell-realtime-context';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function user(workspaces: AuthUser['workspaces'] = []): AuthUser {
  return { id: 'user-1', workspaces } as AuthUser;
}

function realtimeHarness(reconnectSeq = 0) {
  const listeners = new Map<string, Set<ShellRealtimeListener>>();
  const value: ShellRealtimeContextValue = {
    reconnectSeq,
    status: reconnectSeq > 0 ? 'live' : 'connecting',
    addEventListener: (type, listener) => {
      const registered = listeners.get(type) ?? new Set();
      registered.add(listener);
      listeners.set(type, registered);
      return () => registered.delete(listener);
    },
  };
  return {
    emit(type: string, data: unknown) {
      listeners.get(type)?.forEach((listener) => listener({ type, data }));
    },
    value,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AccessRefreshBoundary', () => {
  it('masks stale content while refreshing principal and app admission', async () => {
    const realtime = realtimeHarness();
    const pendingUser = deferred<AuthUser>();
    const calls: string[] = [];
    const refreshUser = vi.fn(async () => {
      calls.push('user');
      return pendingUser.promise;
    });
    const refreshApps = vi.fn(async () => {
      calls.push('apps');
      return null;
    });
    const refreshWorkspace = vi.fn(async () => {
      calls.push('workspace');
      return null;
    });

    render(
      <ShellRealtimeProvider value={realtime.value}>
        <AccessRefreshBoundary
          accessProjectionKey="access-1"
          refreshApps={refreshApps}
          refreshUser={refreshUser}
          refreshWorkspace={refreshWorkspace}
        >
          <p>protected-content</p>
        </AccessRefreshBoundary>
      </ShellRealtimeProvider>,
    );

    act(() => {
      realtime.emit(AUTH_REALTIME_EVENT_TYPES.accessChanged, {
        reason: AUTH_ACCESS_CHANGE_REASONS.principalAccess,
      });
    });
    expect(
      screen
        .getByText('protected-content')
        .parentElement?.getAttribute('aria-hidden'),
    ).toBe('true');
    expect(screen.getByRole('status').textContent).toContain(
      'accessRefresh.loading',
    );

    await act(async () => {
      pendingUser.resolve(
        user([
          {
            id: 'workspace-1',
            name: 'Workspace One',
            role: 'member',
            slug: 'workspace-one',
          },
        ]),
      );
      await pendingUser.promise;
    });

    await waitFor(() =>
      expect(
        screen
          .getByText('protected-content')
          .parentElement?.getAttribute('aria-hidden'),
      ).toBeNull(),
    );
    expect(calls).toEqual(['user', 'apps']);
  });

  it('skips workspace refresh after revocation and performs a trailing refresh for bursts', async () => {
    const realtime = realtimeHarness();
    const firstUser = deferred<AuthUser>();
    const refreshUser = vi
      .fn<() => Promise<AuthUser>>()
      .mockImplementationOnce(() => firstUser.promise)
      .mockResolvedValue(user());
    const refreshApps = vi.fn().mockResolvedValue(null);
    const refreshWorkspace = vi.fn().mockResolvedValue(null);

    render(
      <ShellRealtimeProvider value={realtime.value}>
        <AccessRefreshBoundary
          accessProjectionKey="access-1"
          refreshApps={refreshApps}
          refreshUser={refreshUser}
          refreshWorkspace={refreshWorkspace}
        >
          <p>protected-content</p>
        </AccessRefreshBoundary>
      </ShellRealtimeProvider>,
    );

    act(() => {
      realtime.emit(AUTH_REALTIME_EVENT_TYPES.accessChanged, {
        reason: AUTH_ACCESS_CHANGE_REASONS.principalAccess,
      });
      realtime.emit(AUTH_REALTIME_EVENT_TYPES.accessChanged, {
        reason: AUTH_ACCESS_CHANGE_REASONS.principalAccess,
      });
    });
    await act(async () => {
      firstUser.resolve(user());
      await firstUser.promise;
    });

    await waitFor(() => expect(refreshUser).toHaveBeenCalledTimes(2));
    expect(refreshApps).toHaveBeenCalledTimes(2);
    expect(refreshWorkspace).not.toHaveBeenCalled();
  });

  it('discards protected child caches when the canonical access projection changes', async () => {
    const realtime = realtimeHarness();
    const pendingApps = deferred<unknown>();
    const refreshUser = vi.fn().mockResolvedValue(user());
    const refreshApps = vi.fn(() => pendingApps.promise);
    const refreshWorkspace = vi.fn().mockResolvedValue(null);
    const renderBoundary = (accessProjectionKey: string) => (
      <ShellRealtimeProvider value={realtime.value}>
        <AccessRefreshBoundary
          accessProjectionKey={accessProjectionKey}
          refreshApps={refreshApps}
          refreshUser={refreshUser}
          refreshWorkspace={refreshWorkspace}
        >
          <input aria-label="cached event" defaultValue="empty" />
        </AccessRefreshBoundary>
      </ShellRealtimeProvider>
    );
    const { rerender } = render(renderBoundary('access-1'));
    fireEvent.change(screen.getByLabelText('cached event'), {
      target: { value: 'stale workspace event' },
    });

    act(() => {
      realtime.emit(AUTH_REALTIME_EVENT_TYPES.accessChanged, {
        reason: AUTH_ACCESS_CHANGE_REASONS.principalAccess,
      });
    });
    await waitFor(() => expect(refreshApps).toHaveBeenCalledTimes(1));
    rerender(renderBoundary('access-2'));
    expect(
      (screen.getByLabelText('cached event') as HTMLInputElement).value,
    ).toBe('empty');
    expect(
      screen
        .getByLabelText('cached event')
        .parentElement?.getAttribute('aria-hidden'),
    ).toBe('true');

    await act(async () => pendingApps.resolve(null));
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
    expect(
      (screen.getByLabelText('cached event') as HTMLInputElement).value,
    ).toBe('empty');
  });

  it('ignores malformed events and retries while keeping stale content hidden', async () => {
    const realtime = realtimeHarness();
    const refreshUser = vi
      .fn<() => Promise<AuthUser>>()
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValue(user());
    const refreshApps = vi.fn().mockResolvedValue(null);
    const refreshWorkspace = vi.fn().mockResolvedValue(null);

    render(
      <ShellRealtimeProvider value={realtime.value}>
        <AccessRefreshBoundary
          accessProjectionKey="access-1"
          refreshApps={refreshApps}
          refreshUser={refreshUser}
          refreshWorkspace={refreshWorkspace}
        >
          <p>protected-content</p>
        </AccessRefreshBoundary>
      </ShellRealtimeProvider>,
    );

    act(() => {
      realtime.emit(AUTH_REALTIME_EVENT_TYPES.accessChanged, {
        reason: 'unknown',
      });
    });
    expect(refreshUser).not.toHaveBeenCalled();
    expect(screen.getByText('protected-content')).toBeTruthy();

    act(() => {
      realtime.emit(AUTH_REALTIME_EVENT_TYPES.accessChanged, {
        reason: AUTH_ACCESS_CHANGE_REASONS.principalAccess,
      });
    });
    await screen.findByRole('alert');
    await screen.findByRole('heading', { name: 'accessRefresh.failedTitle' });
    expect(
      screen
        .getByText('protected-content')
        .parentElement?.getAttribute('aria-hidden'),
    ).toBe('true');

    const retryButton = screen.getByRole('button', {
      name: 'accessRefresh.retry',
    });
    expect(document.activeElement).toBe(retryButton);
    fireEvent.click(retryButton);
    await screen.findByText('protected-content');
    expect(refreshUser).toHaveBeenCalledTimes(2);
  });

  it('reconciles canonical access when the realtime connection authenticates', async () => {
    const initialRealtime = realtimeHarness(0);
    const liveRealtime = realtimeHarness(1);
    const pendingUser = deferred<AuthUser>();
    const refreshUser = vi.fn(() => pendingUser.promise);
    const refreshApps = vi.fn().mockResolvedValue(null);
    const refreshWorkspace = vi.fn().mockResolvedValue(null);
    const { rerender } = render(
      <ShellRealtimeProvider value={initialRealtime.value}>
        <AccessRefreshBoundary
          accessProjectionKey="access-1"
          refreshApps={refreshApps}
          refreshUser={refreshUser}
          refreshWorkspace={refreshWorkspace}
        >
          <input aria-label="draft" defaultValue="work in progress" />
        </AccessRefreshBoundary>
      </ShellRealtimeProvider>,
    );

    rerender(
      <ShellRealtimeProvider value={liveRealtime.value}>
        <AccessRefreshBoundary
          accessProjectionKey="access-1"
          refreshApps={refreshApps}
          refreshUser={refreshUser}
          refreshWorkspace={refreshWorkspace}
        >
          <input aria-label="draft" defaultValue="work in progress" />
        </AccessRefreshBoundary>
      </ShellRealtimeProvider>,
    );

    await waitFor(() => expect(refreshUser).toHaveBeenCalledTimes(1));
    const draft = screen.getByLabelText('draft') as HTMLInputElement;
    expect(draft.value).toBe('work in progress');
    expect(draft.parentElement?.getAttribute('aria-hidden')).toBe('true');

    await act(async () => {
      pendingUser.resolve(user());
      await pendingUser.promise;
    });

    expect(refreshApps).toHaveBeenCalledTimes(1);
    expect((screen.getByLabelText('draft') as HTMLInputElement).value).toBe(
      'work in progress',
    );
    expect(
      screen.getByLabelText('draft').parentElement?.getAttribute('aria-hidden'),
    ).toBeNull();
  });
});
