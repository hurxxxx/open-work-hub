import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { useEffect, useRef } from 'react';

export type TerminalConnectionState =
  | 'connecting'
  | 'connected'
  | 'ended'
  | 'offline';

const TERMINAL_SCROLL_BATCH_MS = 32;
const MAX_TERMINAL_SCROLL_LINES = 100;

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return window.btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = window.atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function wheelScrollLines(event: WheelEvent, rows: number): number {
  let lines: number;
  if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) {
    lines = event.deltaY;
  } else if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
    lines = event.deltaY * rows;
  } else {
    lines = event.deltaY / 32;
  }
  if (!Number.isFinite(lines) || lines === 0) return 0;
  const rounded = Math.sign(lines) * Math.max(1, Math.round(Math.abs(lines)));
  return Math.max(
    -MAX_TERMINAL_SCROLL_LINES,
    Math.min(MAX_TERMINAL_SCROLL_LINES, rounded),
  );
}

function defaultShouldReconnect(code: number): boolean {
  return ![1000, 4401, 4403, 4404, 4409].includes(code);
}

function defaultReconnectDelay(attempt: number): number {
  return Math.min(30_000, 500 * 2 ** Math.min(attempt, 6));
}

export function WebSocketTerminalSurface({
  ariaLabel,
  onConnectionStateChange,
  onError,
  onExit,
  reconnectDelayMs = defaultReconnectDelay,
  remoteScroll = false,
  shouldReconnect = defaultShouldReconnect,
  token,
  webSocketUrl,
}: {
  ariaLabel: string;
  onConnectionStateChange: (state: TerminalConnectionState) => void;
  onError: () => void;
  onExit: () => void;
  reconnectDelayMs?: (attempt: number) => number;
  remoteScroll?: boolean;
  shouldReconnect?: (code: number) => boolean;
  token: string;
  webSocketUrl: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const computed = window.getComputedStyle(container);
    const color = (name: string, fallback: string) =>
      computed.getPropertyValue(name).trim() || fallback;
    const terminal = new Terminal({
      allowProposedApi: false,
      convertEol: false,
      cursorBlink: true,
      cursorInactiveStyle: 'outline',
      cursorStyle: 'block',
      fontFamily:
        '"JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace',
      fontSize: 13,
      lineHeight: 1.3,
      scrollback: 5000,
      theme: {
        background: color('--ui-color-surface-inverse', '#101318'),
        foreground: color('--ui-color-ink-inverse', '#f4f6f8'),
        cursor: color('--ui-color-ink-inverse', '#f4f6f8'),
        cursorAccent: color('--ui-color-surface-inverse', '#101318'),
        selectionBackground: '#1d4ed8',
        selectionForeground: '#ffffff',
        selectionInactiveBackground: '#1e40af',
      },
    });
    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(container);
    terminal.attachCustomKeyEventHandler((event) => {
      const copyShortcut =
        event.type === 'keydown' &&
        event.key.toLowerCase() === 'c' &&
        (event.metaKey || event.ctrlKey) &&
        terminal.hasSelection();
      if (!copyShortcut) return true;
      void navigator.clipboard
        ?.writeText(terminal.getSelection())
        .catch(() => undefined);
      return false;
    });

    let disposed = false;
    let errorReported = false;
    let reconnectAttempt = 0;
    let reconnectTimer: number | null = null;
    let handshakeTimer: number | null = null;
    let heartbeatTimer: number | null = null;
    let scrollBatchTimer: number | null = null;
    let pendingScrollLines = 0;
    let remoteScrollActive = false;
    let replayWritesPending = 0;
    let ready = false;
    let ended = false;
    let connectedOnce = false;
    let lastPongAt = Date.now();
    let socket: WebSocket | null = null;
    onConnectionStateChange('connecting');

    const reportError = () => {
      if (errorReported || disposed) return;
      errorReported = true;
      onError();
    };
    const sendResize = () => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(
        JSON.stringify({
          type: 'resize',
          cols: terminal.cols,
          rows: terminal.rows,
        }),
      );
    };
    const fit = () => {
      if (
        disposed ||
        container.clientWidth === 0 ||
        container.clientHeight === 0
      ) {
        return;
      }
      fitAddon.fit();
      if (ready) sendResize();
    };
    const resizeObserver = new ResizeObserver(fit);
    resizeObserver.observe(container);

    const flushScroll = () => {
      scrollBatchTimer = null;
      if (
        pendingScrollLines === 0 ||
        !ready ||
        !socket ||
        socket.readyState !== WebSocket.OPEN
      ) {
        pendingScrollLines = 0;
        return;
      }
      socket.send(
        JSON.stringify({ type: 'scroll', lines: pendingScrollLines }),
      );
      pendingScrollLines = 0;
      remoteScrollActive = true;
    };
    if (remoteScroll) {
      terminal.attachCustomWheelEventHandler((event) => {
        event.preventDefault();
        pendingScrollLines = Math.max(
          -MAX_TERMINAL_SCROLL_LINES,
          Math.min(
            MAX_TERMINAL_SCROLL_LINES,
            pendingScrollLines + wheelScrollLines(event, terminal.rows),
          ),
        );
        if (pendingScrollLines !== 0 && scrollBatchTimer === null) {
          scrollBatchTimer = window.setTimeout(
            flushScroll,
            TERMINAL_SCROLL_BATCH_MS,
          );
        }
        return false;
      });
    }

    const dataDisposable = terminal.onData((data) => {
      if (
        replayWritesPending > 0 ||
        !ready ||
        !socket ||
        socket.readyState !== WebSocket.OPEN
      ) {
        return;
      }
      if (scrollBatchTimer !== null) {
        window.clearTimeout(scrollBatchTimer);
        scrollBatchTimer = null;
        pendingScrollLines = 0;
      }
      if (remoteScrollActive) {
        socket.send(JSON.stringify({ type: 'scroll_end' }));
        remoteScrollActive = false;
      }
      const bytes = new TextEncoder().encode(data);
      for (let offset = 0; offset < bytes.length; offset += 64 * 1024) {
        socket.send(
          JSON.stringify({
            type: 'input',
            data: bytesToBase64(bytes.subarray(offset, offset + 64 * 1024)),
          }),
        );
      }
    });

    const clearHandshakeTimer = () => {
      if (handshakeTimer === null) return;
      window.clearTimeout(handshakeTimer);
      handshakeTimer = null;
    };
    const clearHeartbeatTimer = () => {
      if (heartbeatTimer === null) return;
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    };
    const startHeartbeat = (target: WebSocket) => {
      clearHeartbeatTimer();
      lastPongAt = Date.now();
      heartbeatTimer = window.setInterval(() => {
        if (
          socket !== target ||
          target.readyState !== WebSocket.OPEN ||
          !ready
        ) {
          return;
        }
        if (Date.now() - lastPongAt > 75_000) {
          target.close(4001, 'terminal heartbeat timeout');
          return;
        }
        target.send(JSON.stringify({ type: 'ping' }));
      }, 25_000);
    };
    const scheduleReconnect = () => {
      if (disposed || ended || reconnectTimer !== null) return;
      if (document.visibilityState === 'hidden') return;
      const delay = reconnectDelayMs(reconnectAttempt);
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };

    function connect() {
      if (disposed || ended) return;
      const nextSocket = new WebSocket(webSocketUrl);
      socket = nextSocket;
      onConnectionStateChange('connecting');
      handshakeTimer = window.setTimeout(() => {
        if (socket !== nextSocket || ready || disposed || ended) return;
        socket = null;
        onConnectionStateChange('offline');
        reportError();
        nextSocket.close(4000, 'terminal handshake timeout');
        scheduleReconnect();
      }, 10_000);

      nextSocket.addEventListener('open', () => {
        if (socket === nextSocket) {
          nextSocket.send(JSON.stringify({ type: 'auth', token }));
        }
      });
      nextSocket.addEventListener('message', (event) => {
        if (socket !== nextSocket) return;
        let message: { type?: string; data?: string; active?: boolean };
        try {
          message = JSON.parse(String(event.data));
        } catch {
          reportError();
          return;
        }
        if (message.type === 'ready') {
          clearHandshakeTimer();
          if (connectedOnce) {
            terminal.reset();
          }
          connectedOnce = true;
          ready = message.active === true;
          reconnectAttempt = 0;
          errorReported = false;
          onConnectionStateChange(message.active ? 'connected' : 'ended');
          if (ready) startHeartbeat(nextSocket);
          fit();
          terminal.focus();
        } else if (
          message.type === 'replay' &&
          typeof message.data === 'string'
        ) {
          try {
            replayWritesPending += 1;
            terminal.write(base64ToBytes(message.data), () => {
              replayWritesPending = Math.max(0, replayWritesPending - 1);
            });
          } catch {
            replayWritesPending = Math.max(0, replayWritesPending - 1);
            reportError();
            nextSocket.close(4400, 'invalid terminal replay');
          }
        } else if (
          message.type === 'output' &&
          typeof message.data === 'string'
        ) {
          try {
            terminal.write(base64ToBytes(message.data));
          } catch {
            reportError();
            nextSocket.close(4400, 'invalid terminal output');
          }
        } else if (message.type === 'pong') {
          lastPongAt = Date.now();
        } else if (message.type === 'exit') {
          ready = false;
          ended = true;
          onConnectionStateChange('ended');
          onExit();
        } else if (message.type === 'error') {
          reportError();
        }
      });
      nextSocket.addEventListener('close', (event) => {
        if (socket !== nextSocket) return;
        socket = null;
        ready = false;
        clearHeartbeatTimer();
        clearHandshakeTimer();
        if (disposed || ended) return;
        onConnectionStateChange('offline');
        reportError();
        if (shouldReconnect(event.code)) scheduleReconnect();
      });
      nextSocket.addEventListener('error', () => {
        if (socket === nextSocket) reportError();
      });
    }

    const handleVisibilityChange = () => {
      if (
        document.visibilityState === 'visible' &&
        !disposed &&
        !ended &&
        (!socket || socket.readyState === WebSocket.CLOSED)
      ) {
        reconnectAttempt = Math.min(reconnectAttempt, 3);
        connect();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    connect();
    const initialFit = window.requestAnimationFrame(fit);
    return () => {
      disposed = true;
      window.cancelAnimationFrame(initialFit);
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (scrollBatchTimer !== null) window.clearTimeout(scrollBatchTimer);
      clearHandshakeTimer();
      clearHeartbeatTimer();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      resizeObserver.disconnect();
      dataDisposable.dispose();
      socket?.close(1000);
      terminal.dispose();
    };
  }, [
    onConnectionStateChange,
    onError,
    onExit,
    reconnectDelayMs,
    remoteScroll,
    shouldReconnect,
    token,
    webSocketUrl,
  ]);

  return (
    <div
      aria-label={ariaLabel}
      className="h-full min-h-0 w-full bg-[var(--ui-color-surface-inverse)] p-2"
      ref={containerRef}
      role="application"
    />
  );
}
