import type { InputHTMLAttributes } from 'react';
import { forwardRef } from 'react';

import { cn } from '../utils/cn';

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          'h-[var(--ui-density-comfortable)] w-full rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border-strong)] bg-white px-4 text-sm text-[var(--ui-color-ink)] outline-none transition-colors duration-[var(--ui-motion-fast)] placeholder:text-[var(--ui-color-ink-subtle)] focus:border-[var(--ui-color-accent)] focus:ring-2 focus:ring-[var(--ui-color-accent-weak)]',
          className,
        )}
        {...props}
      />
    );
  },
);

Input.displayName = 'Input';
