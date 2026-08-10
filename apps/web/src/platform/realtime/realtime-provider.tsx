import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from 'react';

import {
  isDocsPagesRealtimeSubscriptionMessage,
  resolveRealtimeWebSocketUrl,
} from '@open-alm/contracts/realtime';

import {
  createRealtimeRuntime,
  type RealtimeListener,
  type RealtimeRuntime,
  type RealtimeStatus,
  type RealtimeSubscriptionMessage,
} from './realtime-runtime';

export type {
  RealtimeEvent,
  RealtimeListener,
  RealtimeStatus,
  RealtimeSubscriptionMessage,
} from './realtime-runtime';

type RealtimeContextValue = {
  status: RealtimeStatus;
  reconnectSeq: number;
  addEventListener: (
    type: string | '*',
    listener: RealtimeListener,
  ) => () => void;
  subscribe: (message: RealtimeSubscriptionMessage) => () => void;
};

const RealtimeContext = createContext<RealtimeContextValue | null>(null);
const HEARTBEAT_TIMEOUT_MS = 70000;
const RECONNECT_DELAY_MS = 2500;

type RealtimeConnectionState = {
  status: RealtimeStatus;
  reconnectSeq: number;
};

type RealtimeConnectionAction =
  | { type: 'connecting' }
  | { type: 'live' }
  | { type: 'offline' };

function realtimeConnectionReducer(
  state: RealtimeConnectionState,
  action: RealtimeConnectionAction,
): RealtimeConnectionState {
  if (action.type === 'connecting') {
    return state.status === 'connecting'
      ? state
      : { ...state, status: 'connecting' };
  }
  if (action.type === 'live') {
    return {
      status: 'live',
      reconnectSeq: state.reconnectSeq + 1,
    };
  }
  return state.status === 'offline' ? state : { ...state, status: 'offline' };
}

function realtimeWebSocketUrl(): string {
  return resolveRealtimeWebSocketUrl(window.location.origin);
}

export function RealtimeProvider({
  children,
  token,
}: {
  children: ReactNode;
  token: string | null;
}) {
  const [connectionState, dispatchConnection] = useReducer(
    realtimeConnectionReducer,
    { status: 'offline', reconnectSeq: 0 },
  );
  const runtime = useMemo<RealtimeRuntime | null>(() => {
    if (!token) {
      return null;
    }
    return createRealtimeRuntime({
      socketFactory: (url) => new WebSocket(url),
      url: realtimeWebSocketUrl(),
      token,
      heartbeatTimeoutMs: HEARTBEAT_TIMEOUT_MS,
      reconnectDelayMs: RECONNECT_DELAY_MS,
      timers: {
        setTimeout: (callback, delayMs) => window.setTimeout(callback, delayMs),
        clearTimeout: (timerId) => window.clearTimeout(timerId as number),
      },
      onStatusChange: (status) => dispatchConnection({ type: status }),
    });
  }, [token]);

  const addEventListener = useCallback(
    (type: string | '*', listener: RealtimeListener) => {
      return runtime?.addEventListener(type, listener) ?? (() => undefined);
    },
    [runtime],
  );

  const subscribe = useCallback(
    (message: RealtimeSubscriptionMessage) => {
      return runtime?.subscribe(message) ?? (() => undefined);
    },
    [runtime],
  );

  useEffect(() => {
    if (!runtime) {
      dispatchConnection({ type: 'offline' });
      return;
    }

    const connectTimer = window.setTimeout(() => {
      runtime.connect();
    }, 0);

    return () => {
      window.clearTimeout(connectTimer);
      runtime.dispose();
    };
  }, [runtime]);

  const value = useMemo<RealtimeContextValue>(
    () => ({
      status: connectionState.status,
      reconnectSeq: connectionState.reconnectSeq,
      addEventListener,
      subscribe,
    }),
    [
      addEventListener,
      connectionState.reconnectSeq,
      connectionState.status,
      subscribe,
    ],
  );

  return (
    <RealtimeContext.Provider value={value}>
      {children}
    </RealtimeContext.Provider>
  );
}

export function useRealtime(): RealtimeContextValue {
  const context = use(RealtimeContext);
  if (!context) {
    throw new Error('useRealtime must be used within RealtimeProvider.');
  }
  return context;
}

export function useRealtimeEvent(
  type: string | '*',
  handler: RealtimeListener,
): void {
  const { addEventListener } = useRealtime();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const removeListener = addEventListener(type, (event) => {
      handlerRef.current(event);
    });
    return removeListener;
  }, [addEventListener, type]);
}

export function useRealtimeSubscription(
  message: RealtimeSubscriptionMessage | null,
): void {
  const { subscribe } = useRealtime();
  const key = message?.key ?? null;
  const shareToken = message?.share_token ?? null;
  const topic = message?.topic ?? null;
  const type = message?.type ?? null;
  const workspaceSlug = message?.workspace_slug ?? null;

  useEffect(() => {
    const subscriptionMessage = {
      type,
      topic,
      key,
      workspace_slug: workspaceSlug,
      share_token: shareToken,
    };
    if (!isDocsPagesRealtimeSubscriptionMessage(subscriptionMessage)) {
      return undefined;
    }
    return subscribe(subscriptionMessage);
  }, [key, shareToken, topic, type, workspaceSlug, subscribe]);
}
