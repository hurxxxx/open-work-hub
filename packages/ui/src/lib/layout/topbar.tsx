import type { ReactNode } from 'react';

export interface TopbarProps {
  breadcrumb?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export function Topbar({
  breadcrumb,
  title,
  description,
  actions,
}: TopbarProps) {
  return (
    <header className="grid grid-cols-[minmax(0,1.4fr)_auto] gap-4 rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-6 shadow-[var(--ui-shadow-sm)] max-[980px]:grid-cols-1">
      <div className="grid gap-2">
        {breadcrumb ? (
          <p className="m-0 text-[0.82rem] text-[var(--ui-color-ink-subtle)]">
            {breadcrumb}
          </p>
        ) : null}
        <h1 className="m-0 text-[clamp(1.5rem,2.5vw,2.1rem)] font-semibold tracking-[-0.025em] text-[var(--ui-color-ink)]">
          {title}
        </h1>
        {description ? (
          <p className="m-0 max-w-[68ch] text-sm text-[var(--ui-color-ink-muted)]">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center justify-end gap-2">{actions}</div> : null}
    </header>
  );
}
