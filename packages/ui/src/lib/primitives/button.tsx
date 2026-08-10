import { cva, type VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes, Ref } from 'react';

import { cn } from '../utils/cn';

const buttonVariants = cva(
  'ui-primitive-control inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--ui-radius-sm)] border text-[length:var(--ui-text-caption)] font-semibold transition-colors duration-[var(--ui-motion-fast)] disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      variant: {
        primary:
          'border-[var(--ui-color-accent)] bg-ui-accent text-[var(--ui-color-accent-fg)] hover:bg-ui-accent-hover',
        secondary:
          'border-[var(--ui-color-border)] bg-ui-surface-raised text-[var(--ui-color-ink)] hover:bg-ui-surface-subtle',
        ghost:
          'border-transparent bg-transparent text-[var(--ui-color-ink)] hover:bg-ui-surface-subtle',
        subtle:
          'border-[var(--ui-color-border)] bg-ui-surface-subtle text-[var(--ui-color-ink-muted)] hover:bg-ui-accent-weak',
      },
      size: {
        dense: 'h-[var(--ui-density-dense)] px-2.5',
        comfortable: 'h-[var(--ui-density-comfortable)] px-3.5',
        icon: 'size-[var(--ui-density-dense)] p-0',
      },
      fullWidth: {
        true: 'w-full',
      },
    },
    defaultVariants: {
      variant: 'secondary',
      size: 'dense',
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  ref?: Ref<HTMLButtonElement>;
}

export function Button({ className, variant, size, fullWidth, type = 'button', ref, ...props }: ButtonProps) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size, fullWidth }), className)}
      {...props}
    />
  );
}

export function IconButton(props: Omit<ButtonProps, 'size'>) {
  return <Button size="icon" {...props} />;
}
