import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  type Dispatch,
  type Reducer,
} from 'react';

import type { PickerState } from './picker-model';

export type ResourcePickerSessionActions<TItem, TAction> = {
  query: (value: string) => TAction;
  submit: (item: TItem) => TAction;
  submitFailed: (message: string) => TAction;
  submitFinished: () => TAction;
  reset?: () => TAction;
};

export type ResourcePickerLoadActions<TItem, TAction> = {
  load: () => TAction;
  loaded: (items: TItem[]) => TAction;
  failed: (message: string) => TAction;
};

export type ResourcePickerSessionOptions<
  TItem,
  TAction,
  TState extends PickerState<TItem> = PickerState<TItem>,
> = {
  actions: ResourcePickerSessionActions<TItem, TAction>;
  getPickFailedMessage: (error: unknown) => string;
  initialState: TState;
  onClose: () => void;
  onPick: (item: TItem) => Promise<void> | void;
  reducer: Reducer<TState, TAction>;
  resetOnClose?: boolean;
};

export type ResourcePickerSession<
  TItem,
  TAction,
  TState extends PickerState<TItem> = PickerState<TItem>,
> = {
  dispatch: Dispatch<TAction>;
  handleClose: () => void;
  handlePick: (item: TItem) => Promise<void>;
  setQuery: (value: string) => void;
  state: TState;
};

export type ResourcePickerLoadOptions<TItem, TAction> = {
  actions: ResourcePickerLoadActions<TItem, TAction>;
  deferLoad?: boolean;
  delayMs?: number;
  dispatch: Dispatch<TAction>;
  enabled: boolean;
  getLoadFailedMessage: (error: unknown) => string;
  loadItems: () => Promise<readonly TItem[]>;
};

export function useResourcePickerSession<
  TItem,
  TAction,
  TState extends PickerState<TItem> = PickerState<TItem>,
>({
  actions,
  getPickFailedMessage,
  initialState,
  onClose,
  onPick,
  reducer,
  resetOnClose = true,
}: ResourcePickerSessionOptions<TItem, TAction, TState>): ResourcePickerSession<
  TItem,
  TAction,
  TState
> {
  const [state, dispatch] = useReducer(reducer, initialState);
  const handlersRef = useRef({
    actions,
    getPickFailedMessage,
    onClose,
    onPick,
    resetOnClose,
  });

  handlersRef.current = {
    actions,
    getPickFailedMessage,
    onClose,
    onPick,
    resetOnClose,
  };

  const handleClose = useCallback(() => {
    const {
      actions: currentActions,
      onClose: close,
      resetOnClose: shouldReset,
    } = handlersRef.current;
    if (shouldReset && currentActions.reset) {
      dispatch(currentActions.reset());
    }
    close();
  }, []);

  const setQuery = useCallback((value: string) => {
    dispatch(handlersRef.current.actions.query(value));
  }, []);

  const handlePick = useCallback(
    async (item: TItem) => {
      const {
        actions: currentActions,
        getPickFailedMessage: getFailureMessage,
        onPick: pick,
      } = handlersRef.current;

      dispatch(currentActions.submit(item));
      try {
        await pick(item);
        handleClose();
      } catch (error) {
        dispatch(currentActions.submitFailed(getFailureMessage(error)));
      } finally {
        dispatch(currentActions.submitFinished());
      }
    },
    [handleClose],
  );

  return {
    dispatch,
    handleClose,
    handlePick,
    setQuery,
    state,
  };
}

export function useResourcePickerLoad<TItem, TAction>({
  actions,
  deferLoad = false,
  delayMs = 0,
  dispatch,
  enabled,
  getLoadFailedMessage,
  loadItems,
}: ResourcePickerLoadOptions<TItem, TAction>): void {
  const handlersRef = useRef({
    actions,
    getLoadFailedMessage,
  });

  handlersRef.current = {
    actions,
    getLoadFailedMessage,
  };

  useEffect(() => {
    if (!enabled) return undefined;

    let cancelled = false;
    let timer: number | null = null;

    dispatch(handlersRef.current.actions.load());

    const runLoad = () => {
      loadItems()
        .then((items) => {
          if (cancelled) return;
          dispatch(handlersRef.current.actions.loaded(Array.from(items)));
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          dispatch(
            handlersRef.current.actions.failed(
              handlersRef.current.getLoadFailedMessage(error),
            ),
          );
        });
    };

    if (delayMs > 0 || deferLoad) {
      timer = window.setTimeout(runLoad, delayMs);
    } else {
      runLoad();
    }

    return () => {
      cancelled = true;
      if (timer !== null) {
        window.clearTimeout(timer);
      }
    };
  }, [deferLoad, delayMs, dispatch, enabled, loadItems]);
}
