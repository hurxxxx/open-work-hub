import type { AgentTerminalSession } from '../api/agent-terminal-api';

const ACTIVE_SESSION_STATUSES = new Set<AgentTerminalSession['status']>([
  'starting',
  'running',
]);

export function isAgentTerminalSessionActive(
  session: Pick<AgentTerminalSession, 'status'>,
): boolean {
  return ACTIVE_SESSION_STATUSES.has(session.status);
}

export function getAgentTerminalSessionCapacity(
  sessions: readonly Pick<AgentTerminalSession, 'status'>[],
  limit: number,
) {
  const active = sessions.filter(isAgentTerminalSessionActive).length;
  return {
    active,
    limit,
    limitReached: active >= limit,
  };
}
