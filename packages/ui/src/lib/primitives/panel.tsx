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
        'rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-5 shadow-[var(--ui-shadow-sm)] max-[720px]:p-4',
        className,
      )}
      {...props}
    >
      {hasHeader ? (
        <header className="mb-4 flex items-start justify-between gap-3 max-[720px]:flex-col">
          <div className="grid gap-1.5">
            {eyebrow ? (
              <p className="m-0 text-xs font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                {eyebrow}
              </p>
            ) : null}
            {title ? (
              <h2 className="m-0 text-[1.25rem] font-semibold tracking-[-0.02em] text-[var(--ui-color-ink)] max-[720px]:text-[1.1rem]">
                {title}
              </h2>
            ) : null}
            {description ? (
              <p className="m-0 max-w-[68ch] text-sm text-[var(--ui-color-ink-muted)]">
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
