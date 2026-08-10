import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes } from 'react';

import { uiToneClasses } from '../tone-classes';
import { cn } from '../utils/cn';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-[var(--ui-radius-sm)] border px-2 py-0.5 text-[length:var(--ui-text-caption)] font-semibold leading-none',
  {
    variants: {
      tone: {
        neutral: uiToneClasses.neutral,
        accent: uiToneClasses.accent,
        success: uiToneClasses.success,
        warning: uiToneClasses.warning,
        danger: uiToneClasses.danger,
        inverse: uiToneClasses.inverse,
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
