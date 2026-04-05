import { cva, type VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes } from 'react';
import { forwardRef } from 'react';

import { cn } from '../utils/cn';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--ui-radius-md)] border text-sm font-semibold transition-colors duration-[var(--ui-motion-fast)] disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      variant: {
        primary:
          'border-[var(--ui-color-accent)] bg-[var(--ui-color-accent)] text-white hover:bg-[#16242e]',
        secondary:
          'border-[var(--ui-color-border-strong)] bg-[var(--ui-color-surface-raised)] text-[var(--ui-color-ink)] hover:bg-[var(--ui-color-surface-subtle)]',
        ghost:
          'border-transparent bg-transparent text-[var(--ui-color-ink)] hover:bg-[var(--ui-color-surface-subtle)]',
        subtle:
          'border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] text-[var(--ui-color-ink-muted)] hover:bg-[var(--ui-color-accent-weak)]',
      },
      size: {
        dense: 'h-[var(--ui-density-dense)] px-3',
        comfortable: 'h-[var(--ui-density-comfortable)] px-4',
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
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, fullWidth, type = 'button', ...props }, ref) => {
    return (
      <button
        ref={ref}
        type={type}
        className={cn(buttonVariants({ variant, size, fullWidth }), className)}
        {...props}
      />
    );
  },
);

Button.displayName = 'Button';

export function IconButton(props: Omit<ButtonProps, 'size'>) {
  return <Button size="icon" {...props} />;
}
