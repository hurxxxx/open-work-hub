import type { ReactNode } from 'react';

import { cn } from '../utils/cn';

export interface SplitPaneProps {
  main: ReactNode;
  aside?: ReactNode;
  className?: string;
  mobileAsideLabel?: ReactNode;
}

export function SplitPane({
  main,
  aside,
  className,
  mobileAsideLabel,
}: SplitPaneProps) {
  return (
    <section
      className={cn(
        'grid grid-cols-[minmax(0,1.9fr)_280px] gap-3 max-[1080px]:grid-cols-1',
        className,
      )}
    >
      <div>{main}</div>
      {aside ? (
        <>
          <div className="grid content-start gap-3 max-[1080px]:hidden">{aside}</div>
          <details className="hidden rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-ui-surface p-3.5 max-[1080px]:block">
            <summary className="cursor-pointer list-none text-[0.86rem] font-semibold text-[var(--ui-color-ink)]">
              {mobileAsideLabel}
            </summary>
            <div className="mt-3 grid content-start gap-4">{aside}</div>
          </details>
        </>
      ) : null}
    </section>
  );
}
