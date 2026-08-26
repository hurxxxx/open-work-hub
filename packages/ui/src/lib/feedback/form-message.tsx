import type { ReactNode } from 'react';

import { cn } from '../utils/cn';

export type FormMessageTone = 'info' | 'warning' | 'error';

export interface FormMessageProps {
  id: string;
  message?: ReactNode | null;
  tone?: FormMessageTone;
  variant?: 'field' | 'form';
  className?: string;
}

const toneClassName: Record<FormMessageTone, string> = {
  info: 'text-[var(--ui-color-accent)]',
  warning: 'text-[var(--ui-color-warning)]',
  error: 'text-[var(--ui-color-danger)]',
};

export function FormMessage({
  className,
  id,
  message,
  tone = 'error',
  variant = 'field',
}: FormMessageProps) {
  const populated = message !== null && message !== undefined;
  return (
    <div
      aria-atomic="true"
      aria-live={tone === 'error' ? 'assertive' : 'polite'}
      className={cn(
        'w-full overflow-hidden text-[length:var(--ui-text-caption)] leading-snug',
        variant === 'field' ? 'h-5' : 'h-12 overflow-y-auto',
        populated ? toneClassName[tone] : 'text-transparent',
        className,
      )}
      data-state={populated ? 'populated' : 'empty'}
      id={id}
      role={tone === 'error' ? 'alert' : 'status'}
    >
      {message ?? null}
    </div>
  );
}
