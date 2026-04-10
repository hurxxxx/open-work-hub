import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { AnimatePresence } from 'motion/react';

import { APP_BAR_ITEMS } from '@/src/constants';
import {
  getDefaultAdminPath,
  hasAnyAdminReadPermission,
} from '@/src/domains/admin/admin-permissions';
import { hasFeatureAccess, type AuthUser } from '@/src/domains/auth/auth-api';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { getUnreadNotificationCount } from '@/src/domains/pms/pms-api';
import { cn } from '@/src/lib/utils';
import { NotificationPanel } from './NotificationPanel';

const featureByAppId: Partial<Record<'home' | 'ai' | 'pms' | 'docs' | 'planner' | 'settings', string>> = {
  ai: 'nav.ai',
  docs: 'nav.docs',
  pms: 'nav.pms',
  planner: 'nav.planner',
  settings: 'nav.admin',
};

function getUserInitials(fullName: string): string {
  const initials = fullName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');

  return initials || 'ID';
}

export function AppBar({
  activeAppId,
  currentUser,
  onOpenAccount,
}: {
  activeAppId: string;
  currentUser: AuthUser;
  onOpenAccount: () => void;
}) {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);

  useEffect(() => {
    if (!token) {
      setUnreadCount(0);
      return;
    }

    let active = true;

    const syncUnreadCount = async () => {
      try {
        const res = await getUnreadNotificationCount(token);
        if (active) {
          setUnreadCount(res.count);
        }
      } catch {
        return;
      }
    };

    void syncUnreadCount();
    const interval = window.setInterval(() => {
      void syncUnreadCount();
    }, 30000);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [token]);

  const handleCountChange = useCallback((delta: number) => {
    setUnreadCount(prev => Math.max(0, prev + delta));
  }, []);

  const handleNavigateToIssue = useCallback((issueId: string) => {
    navigate(`/pms?issue=${encodeURIComponent(issueId)}`);
  }, [navigate]);

  const visibleItems = APP_BAR_ITEMS.filter((item) => {
    if (item.id === 'settings') {
      return (
        hasFeatureAccess(currentUser, 'nav.admin')
        || hasAnyAdminReadPermission(currentUser.system_roles)
      );
    }

    const featureCode = featureByAppId[item.id];
    return !featureCode || hasFeatureAccess(currentUser, featureCode);
  });

  return (
    <div className="w-16 h-full bg-app-bg-strong border-r border-app-border flex flex-col items-center py-4 gap-4 z-20">
      <div className="w-10 h-10 bg-app-accent rounded-lg flex items-center justify-center text-app-bg font-bold mb-4 shadow-lg shadow-app-accent/20">
        ID
      </div>

      {visibleItems.map((item) => (
        <Link
          key={item.id}
          to={item.id === 'settings' ? getDefaultAdminPath(currentUser.system_roles) : item.path}
          className={cn(
            'p-3 rounded-xl transition-all group relative',
            activeAppId === item.id
              ? 'bg-app-surface-sidebar text-app-accent shadow-inner'
              : 'text-gray-500 hover:text-gray-300 hover:bg-app-surface-hover',
          )}
        >
          <item.icon size={22} />
          <div className="app-text-micro absolute left-full ml-2 rounded bg-black px-2 py-1 text-white opacity-0 pointer-events-none whitespace-nowrap z-50 group-hover:opacity-100">
            {item.title}
          </div>
          {activeAppId === item.id ? (
            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-app-accent rounded-r-full" />
          ) : null}
        </Link>
      ))}

      <div className="mt-auto flex flex-col items-center gap-3 relative">
        <button
          aria-label="알림"
          className="relative p-2 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-app-surface-hover transition-all"
          onClick={() => setNotifOpen(prev => !prev)}
          type="button"
        >
          <Bell size={20} />
          {unreadCount > 0 && (
            <span className="app-text-micro absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 font-bold text-white">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        <AnimatePresence>
          {notifOpen && (
            <NotificationPanel
              onClose={() => setNotifOpen(false)}
              onNavigateToIssue={handleNavigateToIssue}
              onCountChange={handleCountChange}
            />
          )}
        </AnimatePresence>

        <button
          aria-label="마이페이지"
          className="app-text-body-sm flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-gradient-to-br from-app-accent to-purple-500 font-bold text-white shadow-md shadow-app-accent/20 outline-none ring-2 ring-transparent transition-all hover:ring-app-accent/40"
          onClick={onOpenAccount}
          title={`${currentUser.display_name || currentUser.full_name} · 마이페이지`}
          type="button"
        >
          {getUserInitials(currentUser.display_name || currentUser.full_name)}
        </button>
      </div>
    </div>
  );
}
