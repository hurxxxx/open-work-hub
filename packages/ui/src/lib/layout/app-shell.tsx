import type { ReactNode } from 'react';

import { cn } from '../utils/cn';

export interface AppShellProps {
  sidebar: ReactNode;
  header?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function AppShell({ sidebar, header, children, className }: AppShellProps) {
  return (
    <div
      className={cn(
        'grid h-screen grid-cols-[264px_minmax(0,1fr)] bg-[var(--ui-color-bg)] max-[980px]:h-auto max-[980px]:grid-cols-1',
        className,
      )}
    >
      {sidebar}
      <main className="ui-scrollbar grid min-h-0 gap-5 overflow-y-auto p-6 max-[980px]:overflow-visible max-[980px]:p-4">
        {header}
        {children}
      </main>
    </div>
  );
}
