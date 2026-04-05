import type { ReactNode } from 'react';

export interface MetricInlineProps {
  label: ReactNode;
  value: ReactNode;
}

export function MetricInline({ label, value }: MetricInlineProps) {
  return (
    <div className="grid gap-1">
      <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
        {label}
      </span>
      <strong className="text-sm text-[var(--ui-color-ink)]">{value}</strong>
    </div>
  );
}
