import { createContext, use, useEffect, useRef, type ReactNode } from 'react';

export type ShellRealtimeStatus = 'offline' | 'connecting' | 'live';

export type ShellRealtimeEvent = {
  data?: unknown;
  type: string;
};

export type ShellRealtimeListener = (event: ShellRealtimeEvent) => void;

export type ShellRealtimeContextValue = {
  addEventListener: (
    type: string | '*',
    listener: ShellRealtimeListener,
  ) => () => void;
  reconnectSeq: number;
  status: ShellRealtimeStatus;
};

const NOOP_SHELL_REALTIME: ShellRealtimeContextValue = {
  addEventListener: () => () => undefined,
  reconnectSeq: 0,
  status: 'offline',
};

const ShellRealtimeContext =
  createContext<ShellRealtimeContextValue>(NOOP_SHELL_REALTIME);

export function ShellRealtimeProvider({
  children,
  value,
}: {
  children: ReactNode;
  value: ShellRealtimeContextValue;
}) {
  return (
    <ShellRealtimeContext.Provider value={value}>
      {children}
    </ShellRealtimeContext.Provider>
  );
}

export function useShellRealtime(): ShellRealtimeContextValue {
  return use(ShellRealtimeContext);
}

export function useShellRealtimeEvent(
  type: string | '*',
  handler: ShellRealtimeListener,
): void {
  const { addEventListener } = useShellRealtime();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    return addEventListener(type, (event) => {
      handlerRef.current(event);
    });
  }, [addEventListener, type]);
}
