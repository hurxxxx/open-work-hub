import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiRequestError } from '@/src/platform/api/client';

import { useLegacyIssueGridPreference } from './useLegacyIssueGridPreference';

const apiMocks = vi.hoisted(() => ({
  deletePreference: vi.fn(),
  fetchPreference: vi.fn(),
  updatePreference: vi.fn(),
}));

vi.mock('../api/legacy-issue-dataset-api', () => ({
  deleteLegacyIssueGridPreference: (...args: unknown[]) =>
    apiMocks.deletePreference(...args),
  fetchLegacyIssueGridPreference: (...args: unknown[]) =>
    apiMocks.fetchPreference(...args),
  updateLegacyIssueGridPreference: (...args: unknown[]) =>
    apiMocks.updatePreference(...args),
}));

describe('legacy issue grid preference workflow', () => {
  beforeEach(() => {
    apiMocks.deletePreference.mockReset().mockResolvedValue(undefined);
    apiMocks.fetchPreference
      .mockReset()
      .mockResolvedValue({ preference: null, revision: 0 });
    apiMocks.updatePreference.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads the account preference and coalesces debounced changes', async () => {
    const { result } = renderHook(() =>
      useLegacyIssueGridPreference({
        gridKey: 'aircon',
        gridKind: 'dataset',
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.status).toBe('idle'));
    expect(result.current.preference).toBeNull();

    apiMocks.updatePreference.mockImplementation(async ({ payload }) => ({
      ...payload,
      created_at: '2026-07-31T00:00:00Z',
      grid_key: 'aircon',
      grid_kind: 'dataset',
      revision: 1,
      updated_at: '2026-07-31T00:00:00Z',
    }));
    vi.useFakeTimers();
    act(() => {
      result.current.updatePreference({
        column_order: ['a', 'b'],
        frozen_column_count: 0,
        hidden_column_keys: [],
      });
      result.current.updatePreference({
        column_order: ['b', 'a'],
        frozen_column_count: 1,
        hidden_column_keys: ['a'],
      });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(apiMocks.updatePreference).toHaveBeenCalledTimes(1);
    expect(apiMocks.updatePreference).toHaveBeenCalledWith(
      expect.objectContaining({
        expectedRevision: 0,
        payload: {
          column_order: ['b', 'a'],
          frozen_column_count: 1,
          hidden_column_keys: ['a'],
        },
      }),
    );
    expect(result.current.status).toBe('idle');
  });

  it('queues reset after an in-flight save so the deleted override cannot be recreated', async () => {
    let resolveSave: ((value: unknown) => void) | null = null;
    apiMocks.updatePreference.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSave = resolve;
        }),
    );
    const { result } = renderHook(() =>
      useLegacyIssueGridPreference({
        gridKey: 'aircon',
        gridKind: 'vehicle-module-checklist',
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.status).toBe('idle'));

    vi.useFakeTimers();
    act(() => {
      result.current.updatePreference({
        column_order: ['b', 'a'],
        frozen_column_count: 1,
        hidden_column_keys: [],
      });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    expect(apiMocks.updatePreference).toHaveBeenCalledTimes(1);

    act(() => result.current.resetPreference());
    expect(apiMocks.deletePreference).not.toHaveBeenCalled();

    await act(async () => {
      resolveSave?.({
        column_order: ['b', 'a'],
        created_at: '2026-07-31T00:00:00Z',
        frozen_column_count: 1,
        grid_key: 'aircon',
        grid_kind: 'vehicle-module-checklist',
        hidden_column_keys: [],
        revision: 1,
        updated_at: '2026-07-31T00:00:00Z',
      });
      await Promise.resolve();
    });

    expect(apiMocks.deletePreference).toHaveBeenCalledTimes(1);
    expect(apiMocks.deletePreference).toHaveBeenCalledWith(
      expect.objectContaining({ expectedRevision: 1 }),
    );
    expect(result.current.preference).toBeNull();
  });

  it('rejects a late debounced save after another tab reset the preference', async () => {
    const onSaveError = vi.fn();
    apiMocks.fetchPreference
      .mockResolvedValueOnce({ preference: null, revision: 0 })
      .mockResolvedValueOnce({ preference: null, revision: 1 });
    apiMocks.updatePreference.mockRejectedValue(
      new ApiRequestError(
        409,
        'Grid preference changed elsewhere.',
        { code: 'legacy_issues.grid_preference_revision_conflict' },
      ),
    );
    const { result } = renderHook(() =>
      useLegacyIssueGridPreference({
        gridKey: 'aircon',
        gridKind: 'dataset',
        onSaveError,
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.status).toBe('idle'));

    vi.useFakeTimers();
    act(() => {
      result.current.updatePreference({
        column_order: ['b', 'a'],
        frozen_column_count: 1,
        hidden_column_keys: ['a'],
      });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
      await Promise.resolve();
    });
    vi.useRealTimers();

    await waitFor(() => expect(result.current.status).toBe('idle'));
    expect(apiMocks.updatePreference).toHaveBeenCalledWith(
      expect.objectContaining({ expectedRevision: 0 }),
    );
    expect(apiMocks.fetchPreference).toHaveBeenCalledTimes(2);
    expect(result.current.preference).toBeNull();
    expect(onSaveError).not.toHaveBeenCalled();
  });

  it('refreshes the revision and retries an explicit reset after a conflict', async () => {
    apiMocks.fetchPreference
      .mockResolvedValueOnce({
        preference: {
          column_order: ['a'],
          created_at: '2026-07-31T00:00:00Z',
          frozen_column_count: 0,
          grid_key: 'aircon',
          grid_kind: 'dataset',
          hidden_column_keys: [],
          revision: 4,
          updated_at: '2026-07-31T00:00:00Z',
        },
        revision: 4,
      })
      .mockResolvedValueOnce({
        preference: {
          column_order: ['b', 'a'],
          created_at: '2026-07-31T00:00:00Z',
          frozen_column_count: 1,
          grid_key: 'aircon',
          grid_kind: 'dataset',
          hidden_column_keys: ['a'],
          revision: 5,
          updated_at: '2026-07-31T00:00:00Z',
        },
        revision: 5,
      });
    apiMocks.deletePreference
      .mockRejectedValueOnce(
        new ApiRequestError(409, 'Grid preference changed elsewhere.'),
      )
      .mockResolvedValueOnce(undefined);
    const { result } = renderHook(() =>
      useLegacyIssueGridPreference({
        gridKey: 'aircon',
        gridKind: 'dataset',
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.status).toBe('idle'));

    act(() => result.current.resetPreference());

    await waitFor(() =>
      expect(apiMocks.deletePreference).toHaveBeenCalledTimes(2),
    );
    expect(apiMocks.deletePreference.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ expectedRevision: 4 }),
    );
    expect(apiMocks.deletePreference.mock.calls[1]?.[0]).toEqual(
      expect.objectContaining({ expectedRevision: 5 }),
    );
    await waitFor(() => expect(result.current.status).toBe('idle'));
    expect(result.current.preference).toBeNull();
  });
});
