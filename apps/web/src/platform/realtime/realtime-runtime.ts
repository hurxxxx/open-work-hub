import {
  REALTIME_CLIENT_EVENT_TYPES,
  REALTIME_SERVER_EVENT_TYPES,
  type DocsPagesRealtimeSubscriptionMessage,
  type WhiteboardAccessRealtimeSubscriptionMessage,
} from '@open-work-hub/contracts/realtime';

export type RealtimeStatus = 'connecting' | 'live' | 'offline';

export type RealtimeEvent = {
  type: string;
  data?: unknown;
  topic?: string;
  event_id?: string;
  published_at_ms?: number;
};

export type RealtimeSubscriptionMessage =
  | DocsPagesRealtimeSubscriptionMessage
  | WhiteboardAccessRealtimeSubscriptionMessage;

export type RealtimeListener = (event: RealtimeEvent) => void;

export type RealtimeRuntimeSocket = {
  readonly readyState: number;
  send: (payload: string) => void;
  close: () => void;
  addEventListener: (
    type: 'open' | 'message' | 'close' | 'error',
    listener: EventListener,
  ) => void;
  removeEventListener: (
    type: 'open' | 'message' | 'close' | 'error',
    listener: EventListener,
  ) => void;
};

export type RealtimeRuntimeTimers = {
  setTimeout: (callback: () => void, delayMs: number) => unknown;
  clearTimeout: (timerId: unknown) => void;
};

export type RealtimeRuntime = {
  connect: () => void;
  dispose: () => void;
  addEventListener: (
    type: string | '*',
    listener: RealtimeListener,
  ) => () => void;
  subscribe: (message: RealtimeSubscriptionMessage) => () => void;
};

type ActiveRealtimeSubscription = {
  message: RealtimeSubscriptionMessage;
  refCount: number;
};

export type RealtimeRuntimeOptions = {
  socketFactory: (url: string) => RealtimeRuntimeSocket;
  url: string;
  token: string;
  heartbeatTimeoutMs: number;
  reconnectDelayMs: number;
  timers: RealtimeRuntimeTimers;
  onStatusChange: (status: RealtimeStatus) => void;
  onEvent?: (event: RealtimeEvent) => void;
};

const SOCKET_OPEN_READY_STATE = 1;
const POLICY_CLOSE_CODES = new Set([1008, 4401, 4403, 4409]);

function subscriptionKey(message: RealtimeSubscriptionMessage): string {
  return JSON.stringify([
    message.topic,
    message.key,
    message.share_token ?? null,
  ]);
}

function sendJson(
  socket: RealtimeRuntimeSocket | null,
  payload: unknown,
): void {
  if (!socket || socket.readyState !== SOCKET_OPEN_READY_STATE) {
    return;
  }
  socket.send(JSON.stringify(payload));
}

export function createRealtimeRuntime({
  socketFactory,
  url,
  token,
  heartbeatTimeoutMs,
  reconnectDelayMs,
  timers,
  onStatusChange,
  onEvent,
}: RealtimeRuntimeOptions): RealtimeRuntime {
  let active = false;
  let live = false;
  let socket: RealtimeRuntimeSocket | null = null;
  let retryTimerId: unknown = null;
  let heartbeatTimerId: unknown = null;
  const listenerCleanups = new Set<() => void>();
  const listeners = new Map<string | '*', Set<RealtimeListener>>();
  const subscriptions = new Map<string, ActiveRealtimeSubscription>();

  const clearRetry = () => {
    if (retryTimerId !== null) {
      timers.clearTimeout(retryTimerId);
      retryTimerId = null;
    }
  };

  const clearHeartbeat = () => {
    if (heartbeatTimerId !== null) {
      timers.clearTimeout(heartbeatTimerId);
      heartbeatTimerId = null;
    }
  };

  const dispatchEvent = (event: RealtimeEvent) => {
    onEvent?.(event);
    const exactListeners = listeners.get(event.type);
    exactListeners?.forEach((listener) => listener(event));
    const wildcardListeners = listeners.get('*');
    wildcardListeners?.forEach((listener) => listener(event));
  };

  const scheduleReconnect = () => {
    if (!active || retryTimerId !== null) {
      return;
    }
    retryTimerId = timers.setTimeout(() => {
      retryTimerId = null;
      connect();
    }, reconnectDelayMs);
  };

  const resetHeartbeat = (currentSocket: RealtimeRuntimeSocket) => {
    clearHeartbeat();
    heartbeatTimerId = timers.setTimeout(() => {
      if (socket === currentSocket) {
        currentSocket.close();
      }
    }, heartbeatTimeoutMs);
  };

  const cleanupSocketListeners = () => {
    listenerCleanups.forEach((cleanup) => cleanup());
    listenerCleanups.clear();
  };

  function connect() {
    if (!active) {
      active = true;
    }

    clearRetry();
    cleanupSocketListeners();
    live = false;
    onStatusChange('connecting');

    const currentSocket = socketFactory(url);
    socket = currentSocket;

    const handleOpen: EventListener = () => {
      sendJson(currentSocket, {
        type: REALTIME_CLIENT_EVENT_TYPES.auth,
        token,
      });
      resetHeartbeat(currentSocket);
    };

    const handleMessage: EventListener = (event) => {
      if (!active || socket !== currentSocket) {
        return;
      }
      resetHeartbeat(currentSocket);

      let payload: RealtimeEvent;
      try {
        payload = JSON.parse((event as MessageEvent).data) as RealtimeEvent;
      } catch {
        return;
      }

      if (!payload || typeof payload.type !== 'string') {
        return;
      }

      if (payload.type === REALTIME_SERVER_EVENT_TYPES.authOk) {
        live = true;
        onStatusChange('live');
        subscriptions.forEach((subscription) => {
          sendJson(currentSocket, subscription.message);
        });
        dispatchEvent(payload);
        return;
      }

      if (payload.type === REALTIME_SERVER_EVENT_TYPES.keepalive) {
        return;
      }

      dispatchEvent(payload);
    };

    const handleClose: EventListener = (event) => {
      const closeEvent = event as CloseEvent;
      cleanupSocketListeners();
      if (!active || socket !== currentSocket) {
        return;
      }
      clearHeartbeat();
      live = false;
      onStatusChange('offline');
      if (POLICY_CLOSE_CODES.has(closeEvent.code)) {
        return;
      }
      scheduleReconnect();
    };

    const handleError: EventListener = () => {
      if (socket === currentSocket) {
        currentSocket.close();
      }
    };

    currentSocket.addEventListener('open', handleOpen);
    currentSocket.addEventListener('message', handleMessage);
    currentSocket.addEventListener('close', handleClose);
    currentSocket.addEventListener('error', handleError);
    listenerCleanups.add(() => {
      currentSocket.removeEventListener('open', handleOpen);
      currentSocket.removeEventListener('message', handleMessage);
      currentSocket.removeEventListener('close', handleClose);
      currentSocket.removeEventListener('error', handleError);
    });
  }

  return {
    connect,
    dispose: () => {
      active = false;
      live = false;
      clearRetry();
      clearHeartbeat();
      cleanupSocketListeners();
      socket?.close();
      socket = null;
    },
    addEventListener: (type, listener) => {
      const typeListeners = listeners.get(type) ?? new Set<RealtimeListener>();
      typeListeners.add(listener);
      listeners.set(type, typeListeners);
      return () => {
        typeListeners.delete(listener);
        if (typeListeners.size === 0) {
          listeners.delete(type);
        }
      };
    },
    subscribe: (message) => {
      const key = subscriptionKey(message);
      const existing = subscriptions.get(key);
      if (existing) {
        existing.refCount += 1;
        existing.message = message;
      } else {
        subscriptions.set(key, { message, refCount: 1 });
      }

      if (live && !existing) {
        sendJson(socket, message);
      }

      return () => {
        const current = subscriptions.get(key);
        if (!current) {
          return;
        }
        current.refCount -= 1;
        if (current.refCount > 0) {
          return;
        }
        subscriptions.delete(key);
        if (live) {
          sendJson(socket, {
            type: REALTIME_CLIENT_EVENT_TYPES.unsubscribe,
            topic: message.topic,
            key: message.key,
            share_token: message.share_token ?? null,
          });
        }
      };
    },
  };
}
