import type { ReactNode } from 'react';

import { cn } from '../utils/cn';

export interface SplitPaneProps {
  main: ReactNode;
  aside?: ReactNode;
  className?: string;
}

export function SplitPane({ main, aside, className }: SplitPaneProps) {
  return (
    <section
      className={cn(
        'grid grid-cols-[minmax(0,1.6fr)_minmax(320px,0.95fr)] gap-5 max-[980px]:grid-cols-1',
        className,
      )}
    >
      <div>{main}</div>
      {aside ? <div className="grid content-start gap-5">{aside}</div> : null}
    </section>
  );
}
