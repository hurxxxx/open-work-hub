import type { HTMLAttributes, ReactNode } from 'react';

import { uiToneClasses } from '../tone-classes';
import { cn } from '../utils/cn';

type NoticeTone = 'info' | 'success' | 'warning' | 'danger';

const toneClasses: Record<NoticeTone, string> = {
  info: uiToneClasses.neutral,
  success: uiToneClasses.success,
  warning: uiToneClasses.warning,
  danger: uiToneClasses.danger,
};

export interface InlineNoticeProps
  extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: ReactNode;
  children: ReactNode;
  tone?: NoticeTone;
}

export function InlineNotice({
  title,
  children,
  tone = 'info',
  className,
  ...props
}: InlineNoticeProps) {
  return (
    <div
      {...props}
      className={cn(
        'grid gap-1 rounded-[var(--ui-radius-md)] border px-3 py-2 text-[length:var(--ui-text-body)]',
        toneClasses[tone],
        className,
      )}
    >
      {title ? <strong>{title}</strong> : null}
      <div>{children}</div>
    </div>
  );
}
