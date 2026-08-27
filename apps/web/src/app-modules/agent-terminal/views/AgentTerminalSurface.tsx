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
        selectionBackground: color('--ui-color-accent', '#5b8def'),
        selectionForeground: color('--ui-color-ink-inverse', '#f4f6f8'),
        selectionInactiveBackground: color('--ui-color-accent', '#5b8def'),
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

    const dataDisposable = terminal.onData((data) => {
      if (
        replayWritesPending > 0 ||
        !ready ||
        !socket ||
        socket.readyState !== WebSocket.OPEN
      ) {
        return;
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
