import { Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/src/lib/utils';

type PmsCenteredStateBlockTone = 'danger' | 'muted';

const toneClassName: Record<PmsCenteredStateBlockTone, string> = {
  danger: 'text-[var(--ui-color-danger)]',
  muted: 'text-app-ink/45',
};

export function PmsCenteredStateBlock({
  children,
  className,
  minHeightClassName,
  tone = 'muted',
}: {
  children: ReactNode;
  className?: string;
  minHeightClassName?: string;
  tone?: PmsCenteredStateBlockTone;
}) {
  return (
    <div
      className={cn(
        'app-text-body flex items-center justify-center text-center',
        minHeightClassName ?? 'min-h-64 py-16',
        toneClassName[tone],
        className,
      )}
    >
      {children}
    </div>
  );
}

export function PmsCenteredLoadingState({
  minHeightClassName,
}: {
  minHeightClassName?: string;
}) {
  return (
    <PmsCenteredStateBlock minHeightClassName={minHeightClassName}>
      <Loader2 size={24} className="animate-spin text-app-accent" />
    </PmsCenteredStateBlock>
  );
}
