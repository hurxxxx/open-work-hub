import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '../utils/cn';

export interface ToolbarProps extends HTMLAttributes<HTMLDivElement> {
  leading?: ReactNode;
  trailing?: ReactNode;
}

export function Toolbar({
  className,
  leading,
  trailing,
  children,
  ...props
}: ToolbarProps) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-3',
        className,
      )}
      {...props}
    >
      <div className="flex flex-wrap items-center gap-2">{leading ?? children}</div>
      {trailing ? (
        <div className="flex flex-wrap items-center justify-end gap-2">{trailing}</div>
      ) : null}
    </div>
  );
}
