import { describe, expect, it } from 'vitest';

import {
  getAgentTerminalSessionCapacity,
  isAgentTerminalSessionActive,
} from './agent-terminal-session-capacity';

describe('agent terminal session capacity', () => {
  it('counts only starting and running sessions against the limit', () => {
    const capacity = getAgentTerminalSessionCapacity(
      [
        { status: 'starting' },
        { status: 'running' },
        { status: 'failed' },
        { status: 'terminated' },
      ],
      4,
    );

    expect(capacity).toEqual({
      active: 2,
      limit: 4,
      limitReached: false,
    });
  });

  it('marks capacity reached at the configured active-session limit', () => {
    const capacity = getAgentTerminalSessionCapacity(
      Array.from({ length: 4 }, () => ({ status: 'running' as const })),
      4,
    );

    expect(capacity.limitReached).toBe(true);
    expect(isAgentTerminalSessionActive({ status: 'exited' })).toBe(false);
  });
});
