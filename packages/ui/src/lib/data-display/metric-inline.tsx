import type { ReactNode } from 'react';

export interface MetricInlineProps {
  label: ReactNode;
  value: ReactNode;
}

export function MetricInline({ label, value }: MetricInlineProps) {
  return (
    <div className="grid gap-0.5">
      <span className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
        {label}
      </span>
      <strong className="text-[0.86rem] text-[var(--ui-color-ink)]">{value}</strong>
    </div>
  );
}
