import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getEligibleWorkspaces } from '@/src/platform/workspaces/workspaces-api';
import { useEligibleWorkspaceSearch } from './useEligibleWorkspaceSearch';

vi.mock('@/src/platform/workspaces/workspaces-api', () => ({
  getEligibleWorkspaces: vi.fn(),
}));

const administrator = {
  id: 'workspace-administrator',
  name: 'Administrator',
  slug: 'administrator',
};

const general = {
  id: 'workspace-general',
  name: 'General',
  slug: 'general',
};

async function flushRequests(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('useEligibleWorkspaceSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(getEligibleWorkspaces).mockImplementation(
      async (_token, appId, options) => {
        const items = options.query ? [general] : [administrator, general];
        return {
          app_id: appId,
          items,
          page: 1,
          page_size: 25,
          total: items.length,
        };
      },
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('clears a filtered result when the owning workspace context changes', async () => {
    const { result, rerender } = renderHook(
      ({ resetKey }) => {
        const options = {
          appId: 'docs',
          resetKey,
          token: 'token-1',
        };
        return useEligibleWorkspaceSearch(options);
      },
      { initialProps: { resetKey: 'administrator' } },
    );

    await flushRequests();
    expect(result.current.items).toEqual([administrator, general]);

    act(() => result.current.setQuery('General'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(result.current.query).toBe('General');
    expect(result.current.items).toEqual([general]);

    rerender({ resetKey: 'general' });
    await flushRequests();

    expect(result.current.query).toBe('');
    expect(result.current.items).toEqual([administrator, general]);
    expect(vi.mocked(getEligibleWorkspaces).mock.lastCall?.[2].query).toBe('');
  });
});
