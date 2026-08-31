import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { useEffect, useRef } from 'react';

import {
  agentTerminalWebSocketUrl,
  base64ToBytes,
  bytesToBase64,
} from '../api/agent-terminal-api';
import {
  shouldReconnectTerminalSocket,
  terminalReconnectDelayMs,
} from './terminal-reconnect-policy';

type TerminalConnectionState = 'connecting' | 'connected' | 'ended' | 'offline';

const TERMINAL_SCROLL_BATCH_MS = 32;
const MAX_TERMINAL_SCROLL_LINES = 100;

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

export function AgentTerminalSurface({
  ariaLabel,
  onConnectionStateChange,
  onError,
  onExit,
  sessionId,
  token,
}: {
  ariaLabel: string;
  onConnectionStateChange: (state: TerminalConnectionState) => void;
  onError: () => void;
  onExit: () => void;
  sessionId: string;
  token: string;
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

    let disposed = false;
    let errorReported = false;
    let reconnectAttempt = 0;
    let reconnectTimer: number | null = null;
    let handshakeTimer: number | null = null;
    let scrollBatchTimer: number | null = null;
    let pendingScrollLines = 0;
    let tmuxScrollActive = false;
    let replayWritesPending = 0;
    let ready = false;
    let ended = false;
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
    const resizeObserver = new ResizeObserver(() => fit());
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
        JSON.stringify({
          type: 'scroll',
          lines: pendingScrollLines,
        }),
      );
      pendingScrollLines = 0;
      tmuxScrollActive = true;
    };
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
      if (tmuxScrollActive) {
        socket.send(JSON.stringify({ type: 'scroll_end' }));
        tmuxScrollActive = false;
      }
      socket.send(
        JSON.stringify({
          type: 'input',
          data: bytesToBase64(new TextEncoder().encode(data)),
        }),
      );
    });

    const clearHandshakeTimer = () => {
      if (handshakeTimer === null) return;
      window.clearTimeout(handshakeTimer);
      handshakeTimer = null;
    };
    const scheduleReconnect = () => {
      if (disposed || ended || reconnectTimer !== null) return;
      const delay = terminalReconnectDelayMs(reconnectAttempt);
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };

    function connect() {
      if (disposed || ended) return;
      const nextSocket = new WebSocket(agentTerminalWebSocketUrl(sessionId));
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
        if (socket !== nextSocket) return;
        nextSocket.send(JSON.stringify({ type: 'auth', token }));
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
          ready = message.active === true;
          reconnectAttempt = 0;
          errorReported = false;
          onConnectionStateChange(message.active ? 'connected' : 'ended');
          fit();
          terminal.focus();
        } else if (
          message.type === 'replay' &&
          typeof message.data === 'string'
        ) {
          replayWritesPending += 1;
          terminal.write(base64ToBytes(message.data), () => {
            replayWritesPending = Math.max(0, replayWritesPending - 1);
          });
        } else if (
          message.type === 'output' &&
          typeof message.data === 'string'
        ) {
          terminal.write(base64ToBytes(message.data));
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
        clearHandshakeTimer();
        if (disposed || ended) return;
        onConnectionStateChange('offline');
        reportError();
        if (!shouldReconnectTerminalSocket(event.code)) return;
        scheduleReconnect();
      });
      nextSocket.addEventListener('error', () => {
        if (socket === nextSocket) reportError();
      });
    }

    connect();

    const initialFit = window.requestAnimationFrame(fit);
    return () => {
      disposed = true;
      window.cancelAnimationFrame(initialFit);
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (scrollBatchTimer !== null) window.clearTimeout(scrollBatchTimer);
      clearHandshakeTimer();
      resizeObserver.disconnect();
      dataDisposable.dispose();
      socket?.close(1000);
      terminal.dispose();
    };
  }, [onConnectionStateChange, onError, onExit, sessionId, token]);

  return (
    <div
      aria-label={ariaLabel}
      className="h-full min-h-0 w-full bg-[var(--ui-color-surface-inverse)] p-2"
      ref={containerRef}
      role="application"
    />
  );
}
