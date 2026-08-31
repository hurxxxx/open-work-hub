const TERMINAL_RECONNECT_DELAYS_MS = [1_000, 2_000, 5_000] as const;
const TERMINAL_PERMANENT_CLOSE_CODES = new Set([1000, 4401, 4403, 4404]);

export function terminalReconnectDelayMs(attempt: number): number {
  const index = Math.min(
    Math.max(0, attempt),
    TERMINAL_RECONNECT_DELAYS_MS.length - 1,
  );
  return TERMINAL_RECONNECT_DELAYS_MS[index] ?? 5_000;
}

export function shouldReconnectTerminalSocket(closeCode: number): boolean {
  return !TERMINAL_PERMANENT_CLOSE_CODES.has(closeCode);
}
