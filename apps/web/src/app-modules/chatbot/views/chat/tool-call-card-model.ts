import type { ToolCallBuffer } from '../../api/agent-events';

export type ToolCallIconKind =
  | 'briefcase'
  | 'calendar'
  | 'file-text'
  | 'wrench';

export interface ToolCallCardModel {
  argsBuffer: string;
  argsPreview: string;
  durationLabel: string | null;
  iconKind: ToolCallIconKind;
  resultError: string | null;
  resultPreview: string | null;
  showRunningProgress: boolean;
  status: ToolCallBuffer['status'];
  statusClassName: string;
  toolName: string;
}

export const TOOL_CALL_ARGS_PREVIEW_LIMIT = 80;

export function projectToolCallCard(call: ToolCallBuffer): ToolCallCardModel {
  const toolName = normalizeToolName(call.name);
  const argsBuffer = normalizeArgsBuffer(call.argsBuffer);

  return {
    argsBuffer,
    argsPreview:
      call.args_preview ??
      previewText(argsBuffer, TOOL_CALL_ARGS_PREVIEW_LIMIT),
    durationLabel: formatToolCallDuration(call),
    iconKind: iconKindForToolName(toolName),
    resultError: call.result?.error ?? null,
    resultPreview: call.result?.preview ?? null,
    showRunningProgress: call.status === 'running',
    status: call.status,
    statusClassName: statusClassName(call.status),
    toolName,
  };
}

export function normalizeToolName(toolName: unknown): string {
  return typeof toolName === 'string' && toolName ? toolName : 'tool';
}

export function normalizeArgsBuffer(argsBuffer: unknown): string {
  return typeof argsBuffer === 'string' && argsBuffer ? argsBuffer : '{}';
}

export function previewText(text: string, limit: number): string {
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit - 1)}\u2026`;
}

export function formatToolCallDuration(
  call: Pick<ToolCallBuffer, 'completedAtMs' | 'startedAtMs'>,
): string | null {
  if (call.completedAtMs === null) {
    return null;
  }
  return `${Math.max(0, call.completedAtMs - call.startedAtMs)}ms`;
}

export function iconKindForToolName(toolName: string): ToolCallIconKind {
  const domain = toolName.split('.')[0];
  if (domain === 'pms') {
    return 'briefcase';
  }
  if (domain === 'meeting' || domain === 'planner') {
    return 'calendar';
  }
  if (domain === 'docs') {
    return 'file-text';
  }
  return 'wrench';
}

export function statusClassName(status: ToolCallBuffer['status']): string {
  if (status === 'running') {
    return 'border-app-warning-border bg-app-warning-bg text-app-warning-text';
  }
  if (status === 'ok') {
    return 'border-app-success-border bg-app-success-bg text-app-success-text';
  }
  if (status === 'rejected' || status === 'unknown') {
    return 'border-app-border bg-app-bg text-app-ink/60';
  }
  return 'border-app-danger-border bg-app-danger-bg text-app-danger-text';
}
