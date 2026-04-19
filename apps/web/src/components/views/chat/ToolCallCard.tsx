import { useMemo, useState } from 'react';
import {
  Briefcase,
  Calendar,
  ChevronDown,
  FileText,
  Wrench,
} from 'lucide-react';

import type { ToolCallBuffer } from '@/src/domains/ai/agent-events';

export interface ToolCallCardProps {
  call: ToolCallBuffer;
}

export function ToolCallCard({ call }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const Icon = useMemo(() => resolveToolIcon(call.name), [call.name]);
  const argsPreview = call.args_preview ?? previewText(call.argsBuffer || '{}', 80);
  const durationMs =
    call.completedAtMs !== null
      ? Math.max(0, call.completedAtMs - call.startedAtMs)
      : null;

  return (
    <section className="border-b border-app-border bg-app-surface px-5 py-3">
      <button
        className="flex w-full items-start gap-3 text-left"
        onClick={() => setExpanded((current) => !current)}
        type="button"
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink">
          <Icon size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="app-text-control-sm font-mono text-app-ink">
              {call.name}
            </span>
            <StatusPill status={call.status} />
            {durationMs !== null ? (
              <span className="app-text-micro text-gray-500">{durationMs}ms</span>
            ) : null}
          </div>
          <div className="mt-1 truncate font-mono text-xs text-gray-500">
            {argsPreview}
          </div>
        </div>
        <ChevronDown
          className={`mt-1 shrink-0 text-gray-500 transition-transform ${expanded ? 'rotate-180' : ''}`}
          size={16}
        />
      </button>

      {call.status === 'running' ? (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-app-bg">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-app-accent/70" />
        </div>
      ) : null}

      {expanded ? (
        <div className="mt-3 space-y-3">
          <pre className="overflow-x-auto rounded-md border border-app-border bg-app-bg px-3 py-2 text-xs leading-relaxed text-app-ink">
            {call.argsBuffer || '{}'}
          </pre>
          {call.result?.preview ? (
            <pre className="overflow-x-auto rounded-md border border-app-border bg-app-bg px-3 py-2 text-xs leading-relaxed text-app-ink">
              {call.result.preview}
            </pre>
          ) : null}
          {call.result?.error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {call.result.error}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function StatusPill({ status }: { status: ToolCallBuffer['status'] }) {
  const label =
    status === 'running' ? 'running' : status === 'ok' ? 'ok' : 'error';
  const className =
    status === 'running'
      ? 'border-amber-200 bg-amber-50 text-amber-700'
      : status === 'ok'
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
        : 'border-red-200 bg-red-50 text-red-700';

  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${className}`}
    >
      {label}
    </span>
  );
}

function resolveToolIcon(toolName: string) {
  const domain = toolName.split('.')[0];
  if (domain === 'pms') {
    return Briefcase;
  }
  if (domain === 'meeting' || domain === 'planner') {
    return Calendar;
  }
  if (domain === 'docs') {
    return FileText;
  }
  return Wrench;
}

function previewText(text: string, limit: number) {
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit - 1)}…`;
}
