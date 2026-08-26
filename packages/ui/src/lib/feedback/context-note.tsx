import { Info, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

import { uiToneClasses } from '../tone-classes';
import { cn } from '../utils/cn';

export type ContextNoteTone = 'neutral' | 'info' | 'warning';

export interface ContextNoteProps {
  children: ReactNode;
  title?: ReactNode;
  tone?: ContextNoteTone;
  className?: string;
}

const toneClassName: Record<ContextNoteTone, string> = {
  neutral: uiToneClasses.neutral,
  info: uiToneClasses.accent,
  warning: uiToneClasses.warning,
};

export function ContextNote({
  children,
  className,
  title,
  tone = 'neutral',
}: ContextNoteProps) {
  const Icon = tone === 'warning' ? TriangleAlert : Info;
  return (
    <div
      className={cn(
        'flex items-start gap-2.5 rounded-[var(--ui-radius-sm)] border px-3 py-2 text-[length:var(--ui-text-body-sm)] leading-snug',
        toneClassName[tone],
        className,
      )}
    >
      <Icon aria-hidden="true" className="mt-0.5 shrink-0" size={16} />
      <div className="min-w-0">
        {title ? <strong className="mb-0.5 block">{title}</strong> : null}
        <div>{children}</div>
      </div>
    </div>
  );
}
