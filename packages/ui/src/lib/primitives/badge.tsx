import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes } from 'react';

import { cn } from '../utils/cn';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-[var(--ui-radius-sm)] border px-2 py-0.5 text-[0.72rem] font-semibold leading-none',
  {
    variants: {
      tone: {
        neutral:
          'border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] text-[var(--ui-color-ink-muted)]',
        accent:
          'border-[var(--ui-color-border)] bg-[var(--ui-color-accent-weak)] text-[var(--ui-color-accent)]',
        success:
          'border-transparent bg-[color-mix(in_oklab,var(--ui-color-success)_12%,white)] text-[var(--ui-color-success)]',
        warning:
          'border-transparent bg-[color-mix(in_oklab,var(--ui-color-warning)_14%,white)] text-[var(--ui-color-warning)]',
        danger:
          'border-transparent bg-[color-mix(in_oklab,var(--ui-color-danger)_14%,white)] text-[var(--ui-color-danger)]',
        inverse:
          'border-white/10 bg-white/6 text-white/76',
      },
    },
    defaultVariants: {
      tone: 'neutral',
    },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export function StatusBadge(props: BadgeProps) {
  return (
    <Badge
      tone="neutral"
      className={cn('h-[var(--ui-density-dense)] px-2.5', props.className)}
      {...props}
    />
  );
}
