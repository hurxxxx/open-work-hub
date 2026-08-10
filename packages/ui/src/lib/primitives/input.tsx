import type { InputHTMLAttributes, Ref } from 'react';

import { cn } from '../utils/cn';

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  ref?: Ref<HTMLInputElement>;
};

export function Input({ className, ref, ...props }: InputProps) {
  return (
    <input
      ref={ref}
      className={cn(
        'ui-primitive-field h-[var(--ui-density-comfortable)] w-full rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-ui-surface-raised px-3 text-[length:var(--ui-text-body-sm)] text-[var(--ui-color-ink)] outline-none transition-colors duration-[var(--ui-motion-fast)] placeholder:text-[var(--ui-color-ink-subtle)] focus:border-[var(--ui-color-accent)] focus:ring-2 focus:ring-[var(--ui-color-accent-weak)]',
        className,
      )}
      {...props}
    />
  );
}
