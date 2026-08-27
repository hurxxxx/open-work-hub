import { describe, expect, it } from 'vitest';

import {
  shouldReconnectTerminalSocket,
  terminalReconnectDelayMs,
} from './terminal-reconnect-policy';

describe('AgentTerminalSurface reconnect policy', () => {
  it('backs off transient WebSocket reconnects at a bounded interval', () => {
    expect([0, 1, 2, 8].map(terminalReconnectDelayMs)).toEqual([
      1_000, 2_000, 5_000, 5_000,
    ]);
  });

  it('retries service interruptions but not intentional or authorization closes', () => {
    expect(shouldReconnectTerminalSocket(1001)).toBe(true);
    expect(shouldReconnectTerminalSocket(1012)).toBe(true);
    expect(shouldReconnectTerminalSocket(1006)).toBe(true);
    expect(shouldReconnectTerminalSocket(1000)).toBe(false);
    expect(shouldReconnectTerminalSocket(4401)).toBe(false);
    expect(shouldReconnectTerminalSocket(4403)).toBe(false);
    expect(shouldReconnectTerminalSocket(4404)).toBe(false);
  });
});
