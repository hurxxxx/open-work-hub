import type { InputHTMLAttributes, ReactNode } from 'react';

import { cn } from '../utils/cn';
import { Input } from './input';

export interface SearchFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  shortcut?: string;
  endAdornment?: ReactNode;
}

export function SearchField({
  className,
  shortcut,
  endAdornment,
  ...props
}: SearchFieldProps) {
  return (
    <div
      className={cn(
        'flex min-h-[var(--ui-density-comfortable)] w-full min-w-0 items-center gap-2 rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-white px-3',
        className,
      )}
    >
      <Input
        className="h-auto min-w-0 border-0 bg-transparent px-0 shadow-none focus:ring-0"
        type="search"
        {...props}
      />
      {endAdornment}
      {shortcut ? (
        <span className="shrink-0 text-xs font-medium text-[var(--ui-color-ink-subtle)] max-[720px]:hidden">
          {shortcut}
        </span>
      ) : null}
    </div>
  );
}
