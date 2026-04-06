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
        'rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-3 max-[720px]:p-2.5',
        className,
      )}
      {...props}
    >
      {hasHeader ? (
        <header className="mb-2 flex items-start justify-between gap-3 border-b border-[var(--ui-color-border)] pb-2 max-[720px]:flex-col">
          <div className="grid gap-1">
            {eyebrow ? (
              <p className="m-0 text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                {eyebrow}
              </p>
            ) : null}
            {title ? (
              <h2 className="m-0 text-[0.96rem] font-semibold tracking-[-0.015em] text-[var(--ui-color-ink)] max-[720px]:text-[0.92rem]">
                {title}
              </h2>
            ) : null}
            {description ? (
              <p className="m-0 max-w-[72ch] text-[0.8rem] leading-5 text-[var(--ui-color-ink-muted)]">
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
