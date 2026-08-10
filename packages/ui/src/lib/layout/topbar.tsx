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
    <header className="sticky top-0 z-20 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-b border-[var(--ui-color-border)] bg-ui-bg/97 py-1 backdrop-blur max-[980px]:grid-cols-1">
      <div className="grid gap-0 self-center">
        {breadcrumb ? (
          <p className="m-0 text-[length:var(--ui-text-overline)] font-medium uppercase tracking-[0.05em] text-[var(--ui-color-ink-subtle)] max-[720px]:hidden">
            {breadcrumb}
          </p>
        ) : null}
        <h1 className="m-0 text-[length:var(--ui-text-h3)] font-semibold tracking-[-0.02em] text-[var(--ui-color-ink)]">
          {title}
        </h1>
        {description ? (
          <p className="m-0 max-w-[64ch] text-[length:var(--ui-text-caption)] text-[var(--ui-color-ink-muted)] max-[820px]:hidden">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center justify-end gap-1.5 max-[980px]:justify-start max-[720px]:w-full">
          {actions}
        </div>
      ) : null}
    </header>
  );
}
