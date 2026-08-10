import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '../utils/cn';

export interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  eyebrow?: ReactNode;
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  status?: ReactNode;
  children: ReactNode;
}

export function Panel({
  className,
  eyebrow,
  title,
  description,
  actions,
  status,
  children,
  ...props
}: PanelProps) {
  const hasHeader = eyebrow || title || description || actions || status;

  return (
    <section
      className={cn(
        'rounded-xl border border-[var(--ui-color-border)] bg-ui-surface-raised p-4 shadow-[var(--ui-shadow-sm)] text-[var(--ui-color-ink)]',
        className,
      )}
      {...props}
    >
      {hasHeader ? (
        <header className="mb-4 flex items-start justify-between gap-3 border-b border-[var(--ui-color-border)] pb-3 max-[720px]:flex-col">
          <div className="grid gap-1.5">
            {eyebrow ? (
              <p className="m-0 text-[length:var(--ui-text-overline)] font-semibold uppercase tracking-wider text-[var(--ui-color-ink-subtle)]">
                {eyebrow}
              </p>
            ) : null}
            {title ? (
              <h2 className="m-0 text-[length:var(--ui-text-h3)] font-semibold tracking-tight text-[var(--ui-color-ink)]">
                {title}
              </h2>
            ) : null}
            {description ? (
              <p className="m-0 max-w-[72ch] text-[length:var(--ui-text-body)] leading-relaxed text-[var(--ui-color-ink-muted)]">
                {description}
              </p>
            ) : null}
          </div>
          {actions || status ? (
            <div className="flex flex-wrap items-center justify-end gap-2 max-[720px]:w-full max-[720px]:justify-start">
              {actions}
              {status}
            </div>
          ) : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}
