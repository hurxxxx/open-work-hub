import type { ReactNode } from 'react';

import { cn } from '../utils/cn';

type NoticeTone = 'info' | 'success' | 'warning' | 'danger';

const toneClasses: Record<NoticeTone, string> = {
  info: 'border-[var(--ui-color-border)] bg-ui-surface-subtle text-[var(--ui-color-ink-muted)]',
  success:
    'border-transparent bg-[color-mix(in_oklab,var(--ui-color-success)_12%,white)] text-[var(--ui-color-success)]',
  warning:
    'border-transparent bg-[color-mix(in_oklab,var(--ui-color-warning)_14%,white)] text-[var(--ui-color-warning)]',
  danger:
    'border-transparent bg-[color-mix(in_oklab,var(--ui-color-danger)_14%,white)] text-[var(--ui-color-danger)]',
};

export interface InlineNoticeProps {
  title?: ReactNode;
  children: ReactNode;
  tone?: NoticeTone;
  className?: string;
}

export function InlineNotice({
  title,
  children,
  tone = 'info',
  className,
}: InlineNoticeProps) {
  return (
    <div
      className={cn(
        'grid gap-1 rounded-[var(--ui-radius-md)] border px-3 py-2 text-sm',
        toneClasses[tone],
        className,
      )}
    >
      {title ? <strong>{title}</strong> : null}
      <div>{children}</div>
    </div>
  );
}
