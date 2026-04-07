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
        'rounded-xl border border-clickup-border bg-clickup-card p-4 shadow-sm text-clickup-text',
        className,
      )}
      {...props}
    >
      {hasHeader ? (
        <header className="mb-4 flex items-start justify-between gap-3 border-b border-clickup-border pb-3 max-[720px]:flex-col">
          <div className="grid gap-1.5">
            {eyebrow ? (
              <p className="m-0 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                {eyebrow}
              </p>
            ) : null}
            {title ? (
              <h2 className="m-0 text-lg font-semibold tracking-tight text-clickup-text max-[720px]:text-base">
                {title}
              </h2>
            ) : null}
            {description ? (
              <p className="m-0 max-w-[72ch] text-sm leading-relaxed text-gray-500 dark:text-gray-400">
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
