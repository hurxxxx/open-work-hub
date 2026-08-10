import { useMemo, useState } from 'react';
import {
  Briefcase,
  Calendar,
  ChevronDown,
  FileText,
  type LucideIcon,
  Wrench,
} from 'lucide-react';

import type { ToolCallBuffer } from '../../api/agent-events';
import {
  projectToolCallCard,
  type ToolCallIconKind,
} from './tool-call-card-model';

export interface ToolCallCardProps {
  call: ToolCallBuffer;
}

export function ToolCallCard({ call }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const model = projectToolCallCard(call);
  const Icon = useMemo(() => resolveToolIcon(model.iconKind), [model.iconKind]);

  return (
    <section className="border-b border-app-border bg-app-surface px-5 py-3">
      <button
        className="flex w-full items-start gap-3 text-left"
        onClick={() => setExpanded((current) => !current)}
        type="button"
      >
        <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink">
          <Icon size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="app-text-control-sm font-mono text-app-ink">
              {model.toolName}
            </span>
            <StatusPill
              className={model.statusClassName}
              status={model.status}
            />
            {model.durationLabel !== null ? (
              <span className="app-text-micro text-app-ink/55">
                {model.durationLabel}
              </span>
            ) : null}
          </div>
          <div className="mt-1 truncate font-mono text-xs text-app-ink/55">
            {model.argsPreview}
          </div>
        </div>
        <ChevronDown
          className={`mt-1 shrink-0 text-app-ink/55 transition-transform ${expanded ? 'rotate-180' : ''}`}
          size={16}
        />
      </button>

      {model.showRunningProgress ? (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-app-bg">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-app-accent/70" />
        </div>
      ) : null}

      {expanded ? (
        <div className="mt-3 space-y-3">
          <pre className="overflow-x-auto rounded-md border border-app-border bg-app-bg px-3 py-2 text-xs leading-relaxed text-app-ink">
            {model.argsBuffer}
          </pre>
          {model.resultPreview ? (
            <pre className="overflow-x-auto rounded-md border border-app-border bg-app-bg px-3 py-2 text-xs leading-relaxed text-app-ink">
              {model.resultPreview}
            </pre>
          ) : null}
          {model.resultError ? (
            <div className="rounded-md border border-app-danger-border bg-app-danger-bg px-3 py-2 text-xs text-app-danger-text">
              {model.resultError}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function StatusPill({
  className,
  status,
}: {
  className: string;
  status: ToolCallBuffer['status'];
}) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[12px] font-medium uppercase tracking-wide ${className}`}
    >
      {status}
    </span>
  );
}

function resolveToolIcon(iconKind: ToolCallIconKind): LucideIcon {
  const icons: Record<ToolCallIconKind, LucideIcon> = {
    briefcase: Briefcase,
    calendar: Calendar,
    'file-text': FileText,
    wrench: Wrench,
  };
  return icons[iconKind];
}
