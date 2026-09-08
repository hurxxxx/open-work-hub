import { Bell } from 'lucide-react';
import type { MouseEventHandler } from 'react';

import { cn } from '@/src/lib/utils';
import { NOTIFICATION_PANEL_ID } from './useNotificationPanelFocus';

export function AppBarNotificationButton({
  badgeClassName,
  className,
  iconSize = 20,
  label,
  onClick,
  open,
  unreadCount,
}: {
  badgeClassName?: string;
  className?: string;
  iconSize?: number;
  label: string;
  onClick: MouseEventHandler<HTMLButtonElement>;
  open: boolean;
  unreadCount: number;
}) {
  return (
    <button
      aria-label={label}
      aria-controls={NOTIFICATION_PANEL_ID}
      aria-expanded={open}
      className={cn('relative rounded-xl transition-all', className)}
      onClick={onClick}
      title={label}
      type="button"
    >
      <Bell size={iconSize} />
      {unreadCount > 0 ? (
        <span
          className={cn(
            'app-text-micro absolute flex size-4 items-center justify-center rounded-full bg-app-danger font-bold text-white',
            badgeClassName ?? '-right-0.5 -top-0.5',
          )}
        >
          {unreadCount > 9 ? '9+' : unreadCount}
        </span>
      ) : null}
    </button>
  );
}
