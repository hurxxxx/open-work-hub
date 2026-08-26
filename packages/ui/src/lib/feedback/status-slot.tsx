import { CircleCheck, CircleX, Info, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

import { Button } from '../primitives/button';
import { uiToneClasses } from '../tone-classes';
import { cn } from '../utils/cn';

export type StatusSlotTone =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'error';
export type StatusSlotAnnouncement = 'off' | 'polite' | 'assertive';

export interface StatusSlotProps {
  message?: ReactNode | null;
  tone?: StatusSlotTone;
  announce?: StatusSlotAnnouncement;
  size?: 'compact' | 'regular';
  action?: { label: ReactNode; onClick: () => void };
  className?: string;
}

const toneClassName: Record<StatusSlotTone, string> = {
  neutral: uiToneClasses.neutral,
  info: uiToneClasses.accent,
  success: uiToneClasses.success,
  warning: uiToneClasses.warning,
  error: uiToneClasses.danger,
};

function StatusSlotIcon({ tone }: { tone: StatusSlotTone }) {
  const props = {
    'aria-hidden': true,
    className: 'shrink-0',
    size: 15,
    strokeWidth: 2.1,
  } as const;
  switch (tone) {
    case 'success':
      return <CircleCheck {...props} />;
    case 'warning':
      return <TriangleAlert {...props} />;
    case 'error':
      return <CircleX {...props} />;
    default:
      return <Info {...props} />;
  }
}

export function StatusSlot({
  action,
  announce = 'polite',
  className,
  message,
  size = 'compact',
  tone = 'neutral',
}: StatusSlotProps) {
  const populated = message !== null && message !== undefined;
  const role =
    announce === 'assertive'
      ? 'alert'
      : announce === 'polite'
        ? 'status'
        : undefined;
  return (
    <div
      aria-atomic={announce === 'off' ? undefined : true}
      aria-live={announce === 'off' ? undefined : announce}
      className={cn(
        'w-full overflow-hidden rounded-[var(--ui-radius-sm)] border px-2.5 text-[length:var(--ui-text-caption)]',
        size === 'compact' ? 'h-[var(--ui-density-comfortable)]' : 'h-14',
        populated
          ? toneClassName[tone]
          : 'pointer-events-none border-transparent bg-transparent text-transparent',
        className,
      )}
      data-state={populated ? 'populated' : 'empty'}
      role={role}
    >
      {populated ? (
        <div className="flex h-full min-w-0 items-center gap-2">
          <StatusSlotIcon tone={tone} />
          <div
            className={cn(
              'min-w-0 flex-1',
              size === 'compact'
                ? 'truncate'
                : 'max-h-full overflow-y-auto leading-snug',
            )}
          >
            {message}
          </div>
          {action ? (
            <Button
              className="shrink-0"
              onClick={action.onClick}
              size="dense"
              variant="ghost"
            >
              {action.label}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
