import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createInitialPickerState,
  pickerReducer,
  type PickerAction,
} from './picker-model';
import {
  useResourcePickerLoad,
  useResourcePickerSession,
} from './resource-picker-session';

type Item = {
  id: string;
  title: string;
};

type Deferred<T> = {
  promise: Promise<T>;
  reject: (reason?: unknown) => void;
  resolve: (value: T) => void;
};

const initialState = createInitialPickerState<Item>();

const sessionActions = {
  query: (value: string): PickerAction<Item> => ({ type: 'query', value }),
  reset: (): PickerAction<Item> => ({ type: 'reset' }),
  submit: (item: Item): PickerAction<Item> => ({
    type: 'submit',
    itemId: item.id,
  }),
  submitFailed: (message: string): PickerAction<Item> => ({
    type: 'submit-failed',
    message,
  }),
  submitFinished: (): PickerAction<Item> => ({ type: 'submit-finished' }),
};

const loadActions = {
  failed: (message: string): PickerAction<Item> => ({
    type: 'failed',
    message,
  }),
  load: (): PickerAction<Item> => ({ type: 'load' }),
  loaded: (items: Item[]): PickerAction<Item> => ({ type: 'loaded', items }),
};

function item(id: string): Item {
  return { id, title: `Item ${id}` };
}

function deferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => undefined;
  let reject: (reason?: unknown) => void = () => undefined;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, reject, resolve };
}

function useTestSession(
  args: {
    onClose?: () => void;
    onPick?: (item: Item) => Promise<void | boolean> | void | boolean;
    resetOnClose?: boolean;
  } = {},
) {
  return useResourcePickerSession<Item, PickerAction<Item>>({
    actions: sessionActions,
    getPickFailedMessage: (error) =>
      error instanceof Error ? error.message : 'Pick failed',
    initialState,
    onClose: args.onClose ?? (() => undefined),
    onPick: args.onPick ?? (() => undefined),
    reducer: pickerReducer,
    resetOnClose: args.resetOnClose,
  });
}

function useTestSessionWithLoad(args: {
  deferLoad?: boolean;
  delayMs?: number;
  enabled: boolean;
  loadItems: () => Promise<readonly Item[]>;
}) {
  const session = useTestSession();
  useResourcePickerLoad<Item, PickerAction<Item>>({
    actions: loadActions,
    deferLoad: args.deferLoad,
    delayMs: args.delayMs,
    dispatch: session.dispatch,
    enabled: args.enabled,
    getLoadFailedMessage: (error) =>
      error instanceof Error ? error.message : 'Load failed',
    loadItems: args.loadItems,
  });
  return session.state;
}

describe('resource-picker-session', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('publishes query changes and resets before closing by default', () => {
    const onClose = vi.fn();
    const { result } = renderHook(() => useTestSession({ onClose }));

    act(() => {
      result.current.setQuery('launch');
    });
    expect(result.current.state.query).toBe('launch');

    act(() => {
      result.current.handleClose();
    });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(result.current.state.query).toBe('');
  });

  it('runs the submit lifecycle and closes after a successful pick', async () => {
    const onClose = vi.fn();
    const onPick = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const { result } = renderHook(() => useTestSession({ onClose, onPick }));

    await act(async () => {
      await result.current.handlePick(item('one'));
    });

    expect(onPick).toHaveBeenCalledWith(item('one'));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(result.current.state.submittingId).toBeNull();
    expect(result.current.state.error).toBeNull();
  });

  it('keeps the selection and query when publication confirmation is cancelled', async () => {
    const onClose = vi.fn();
    const onPick = vi.fn().mockResolvedValue(false);
    const { result } = renderHook(() => useTestSession({ onClose, onPick }));
    act(() => result.current.setQuery('draft'));
    await act(async () => {
      await result.current.handlePick(item('one'));
    });
    expect(onClose).not.toHaveBeenCalled();
    expect(result.current.state.query).toBe('draft');
    expect(result.current.state.submittingId).toBeNull();
    expect(result.current.state.error).toBeNull();
  });

  it('keeps the picker open and records submit failures', async () => {
    const onClose = vi.fn();
    const onPick = vi
      .fn<() => Promise<void>>()
      .mockRejectedValue(new Error('Attach failed'));
    const { result } = renderHook(() => useTestSession({ onClose, onPick }));

    await act(async () => {
      await result.current.handlePick(item('one'));
    });

    expect(onClose).not.toHaveBeenCalled();
    expect(result.current.state.error).toBe('Attach failed');
    expect(result.current.state.submittingId).toBeNull();
  });

  it('loads items immediately and suppresses stale load results', async () => {
    const olderLoad = deferred<readonly Item[]>();
    const newerLoad = deferred<readonly Item[]>();
    const olderLoader = vi
      .fn<() => Promise<readonly Item[]>>()
      .mockReturnValue(olderLoad.promise);
    const newerLoader = vi
      .fn<() => Promise<readonly Item[]>>()
      .mockReturnValue(newerLoad.promise);
    const { result, rerender } = renderHook(
      ({ loadItems }) =>
        useTestSessionWithLoad({
          enabled: true,
          loadItems,
        }),
      { initialProps: { loadItems: olderLoader } },
    );

    await waitFor(() => expect(olderLoader).toHaveBeenCalledTimes(1));
    expect(result.current.loading).toBe(true);

    rerender({ loadItems: newerLoader });
    await waitFor(() => expect(newerLoader).toHaveBeenCalledTimes(1));

    await act(async () => {
      olderLoad.resolve([item('old')]);
    });
    expect(result.current.items).toEqual([]);

    await act(async () => {
      newerLoad.resolve([item('new')]);
    });
    expect(result.current.items).toEqual([item('new')]);
    expect(result.current.loading).toBe(false);
  });

  it.each(['resolve', 'reject'] as const)(
    'ignores a late %s after closing and starting another selection',
    async (completion) => {
      const older = deferred<void | boolean>();
      const newer = deferred<void | boolean>();
      const onClose = vi.fn();
      const onPick = vi
        .fn()
        .mockReturnValueOnce(older.promise)
        .mockReturnValueOnce(newer.promise);
      const { result } = renderHook(() => useTestSession({ onClose, onPick }));
      let olderPick: Promise<void>;
      let newerPick: Promise<void>;
      act(() => {
        olderPick = result.current.handlePick(item('old'));
      });
      act(() => result.current.handleClose());
      act(() => {
        result.current.setQuery('new query');
        newerPick = result.current.handlePick(item('new'));
      });
      await act(async () => {
        if (completion === 'resolve') older.resolve(undefined);
        else older.reject(new Error('Old failure'));
        await olderPick;
      });
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(result.current.state).toMatchObject({
        query: 'new query',
        submittingId: 'new',
        error: null,
      });
      await act(async () => {
        newer.resolve(false);
        await newerPick;
      });
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(result.current.state).toMatchObject({
        query: 'new query',
        submittingId: null,
        error: null,
      });
    },
  );

  it('does not close a later picker after its own session unmounts', async () => {
    const pending = deferred<void>();
    const onClose = vi.fn();
    const { result, unmount } = renderHook(() =>
      useTestSession({ onClose, onPick: () => pending.promise }),
    );
    let pick: Promise<void>;
    act(() => {
      pick = result.current.handlePick(item('old'));
    });
    unmount();
    await act(async () => {
      pending.resolve();
      await pick;
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('honors deferred load delays', async () => {
    vi.useFakeTimers();
    const loadItems = vi
      .fn<() => Promise<readonly Item[]>>()
      .mockResolvedValue([item('one')]);
    const { result } = renderHook(() =>
      useTestSessionWithLoad({
        deferLoad: true,
        delayMs: 25,
        enabled: true,
        loadItems,
      }),
    );

    expect(result.current.loading).toBe(true);
    expect(loadItems).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(24);
    });
    expect(loadItems).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(loadItems).toHaveBeenCalledTimes(1);
    expect(result.current.items).toEqual([item('one')]);
  });
});
