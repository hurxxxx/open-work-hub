import { Bell } from 'lucide-react';

import { cn } from '@/src/lib/utils';

export function AppBarNotificationButton({
  badgeClassName,
  className,
  iconSize = 20,
  label,
  onClick,
  unreadCount,
}: {
  badgeClassName?: string;
  className?: string;
  iconSize?: number;
  label: string;
  onClick: () => void;
  unreadCount: number;
}) {
  return (
    <button
      aria-label={label}
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
