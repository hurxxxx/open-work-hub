import type { ToolCallBuffer } from '@/src/domains/ai/agent-events';

export interface ToolCallCardProps {
  call: ToolCallBuffer;
}

/**
 * Placeholder for Phase 3 tool-call rendering. Props shape is fixed so the
 * envelope → hook → UI wiring is frozen; only the render body needs to be
 * filled in once the server starts emitting ``tool_call_*`` events.
 */
export function ToolCallCard(_: ToolCallCardProps) {
  return null;
}
