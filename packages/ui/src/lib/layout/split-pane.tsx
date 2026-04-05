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
        'grid grid-cols-[minmax(0,1.6fr)_minmax(320px,0.95fr)] gap-5 max-[980px]:grid-cols-1',
        className,
      )}
    >
      <div>{main}</div>
      {aside ? (
        <>
          <div className="grid content-start gap-5 max-[980px]:hidden">{aside}</div>
          <details className="hidden rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-4 shadow-[var(--ui-shadow-sm)] max-[980px]:block">
            <summary className="cursor-pointer list-none text-sm font-semibold text-[var(--ui-color-ink)]">
              {mobileAsideLabel ?? '보조 패널 보기'}
            </summary>
            <div className="mt-4 grid content-start gap-5">{aside}</div>
          </details>
        </>
      ) : null}
    </section>
  );
}
