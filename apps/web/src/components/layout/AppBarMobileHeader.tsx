import { ChevronDown, Menu, Search } from 'lucide-react';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { getInitials } from './app-bar-model';
import { AppBarNotificationButton } from './AppBarNotificationButton';

export function AppBarMobileHeader({
  activeAppTitle,
  canOpenMobileAppMenu,
  canOpenWorkspaceSearch,
  currentUser,
  labels,
  onOpenAccount,
  onOpenMobileAppMenu,
  onOpenMobileNavigation,
  onOpenWorkspaceSearch,
  onToggleNotifications,
  notificationsEnabled,
  unreadCount,
}: {
  activeAppTitle: string;
  canOpenMobileAppMenu?: boolean;
  canOpenWorkspaceSearch: boolean;
  currentUser: AuthUser;
  labels: {
    accountTitle: string;
    mobileMenuTitle: string;
    mobileNavigationOpen: string;
    notificationsTitle: string;
    searchOpen: string;
    searchTitle: string;
  };
  onOpenAccount: () => void;
  onOpenMobileAppMenu?: () => void;
  onOpenMobileNavigation: () => void;
  onOpenWorkspaceSearch: () => void;
  onToggleNotifications: () => void;
  notificationsEnabled: boolean;
  unreadCount: number;
}) {
  const mobileTitle = (
    <div className="app-text-body-sm truncate font-semibold text-white">
      <span>{activeAppTitle}</span>
      {canOpenMobileAppMenu ? (
        <ChevronDown
          size={13}
          className="ml-1 inline-block align-[-2px] text-white/70"
        />
      ) : null}
    </div>
  );

  return (
    <div className="flex h-14 shrink-0 items-center gap-2 border-b border-white/10 bg-app-bg-strong px-3 text-white lg:hidden">
      <button
        aria-label={labels.mobileNavigationOpen}
        className="flex size-10 items-center justify-center rounded-xl border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-surface-hover"
        onClick={onOpenMobileNavigation}
        type="button"
      >
        <Menu size={20} />
      </button>

      {canOpenMobileAppMenu ? (
        <button
          aria-label={labels.mobileMenuTitle}
          className="min-w-0 flex-1 rounded-lg px-1.5 py-1 text-left transition-colors hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-app-accent/35"
          onClick={onOpenMobileAppMenu}
          type="button"
        >
          {mobileTitle}
        </button>
      ) : (
        <div className="min-w-0 flex-1 px-1.5 py-1">{mobileTitle}</div>
      )}

      {canOpenWorkspaceSearch ? (
        <button
          aria-label={labels.searchOpen}
          className="flex size-10 items-center justify-center rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
          onClick={onOpenWorkspaceSearch}
          title={labels.searchTitle}
          type="button"
        >
          <Search size={19} />
        </button>
      ) : null}

      {notificationsEnabled ? (
        <AppBarNotificationButton
          badgeClassName="right-1.5 top-1.5"
          className="flex size-10 items-center justify-center text-white/70 hover:bg-white/10 hover:text-white"
          iconSize={19}
          label={labels.notificationsTitle}
          onClick={onToggleNotifications}
          unreadCount={unreadCount}
        />
      ) : null}

      <button
        aria-label={labels.accountTitle}
        className="app-text-body-sm flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-app-accent font-bold text-app-accent-fg shadow-sm outline-none ring-2 ring-transparent transition-all hover:ring-app-accent/40"
        onClick={onOpenAccount}
        title={`${currentUser.display_name || currentUser.full_name} · ${labels.accountTitle}`}
        type="button"
      >
        {getInitials(currentUser.display_name || currentUser.full_name, 'ID')}
      </button>
    </div>
  );
}
