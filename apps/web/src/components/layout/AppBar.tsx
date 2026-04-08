import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { AnimatePresence } from 'motion/react';

import { APP_BAR_ITEMS } from '@/src/constants';
import {
  getDefaultAdminPath,
  hasAnyAdminReadPermission,
} from '@/src/domains/admin/admin-permissions';
import type { AuthUser } from '@/src/domains/auth/auth-api';
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
        currentUser.visible_features.includes('nav.admin')
        || hasAnyAdminReadPermission(currentUser.permissions)
      );
    }

    const featureCode = featureByAppId[item.id];
    return !featureCode || currentUser.visible_features.includes(featureCode);
  });

  return (
    <div className="w-16 h-full bg-clickup-dark border-r border-clickup-border flex flex-col items-center py-4 gap-4 z-20">
      <div className="w-10 h-10 bg-clickup-purple rounded-lg flex items-center justify-center text-white font-bold mb-4 shadow-lg shadow-clickup-purple/20">
        ID
      </div>

      {visibleItems.map((item) => (
        <Link
          key={item.id}
          to={item.id === 'settings' ? getDefaultAdminPath(currentUser.permissions) : item.path}
          className={cn(
            'p-3 rounded-xl transition-all group relative',
            activeAppId === item.id
              ? 'bg-clickup-sidebar text-clickup-purple shadow-inner'
              : 'text-gray-500 hover:text-gray-300 hover:bg-clickup-hover',
          )}
        >
          <item.icon size={22} />
          <div className="absolute left-full ml-2 px-2 py-1 bg-black text-white text-[10px] rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
            {item.title}
          </div>
          {activeAppId === item.id ? (
            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-clickup-purple rounded-r-full" />
          ) : null}
        </Link>
      ))}

      <div className="mt-auto flex flex-col items-center gap-3 relative">
        <button
          aria-label="알림"
          className="relative p-2 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-clickup-hover transition-all"
          onClick={() => setNotifOpen(prev => !prev)}
          type="button"
        >
          <Bell size={20} />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
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
          className="w-10 h-10 bg-gradient-to-br from-clickup-purple to-purple-500 rounded-full flex items-center justify-center text-white text-[13px] font-bold cursor-pointer shadow-md shadow-clickup-purple/20 ring-2 ring-transparent hover:ring-clickup-purple/40 transition-all outline-none"
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
