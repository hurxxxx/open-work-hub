import { Link } from 'react-router-dom';

import { APP_BAR_ITEMS } from '@/src/constants';
import {
  getDefaultAdminPath,
  hasAnyAdminReadPermission,
} from '@/src/domains/admin/admin-permissions';
import type { AuthUser } from '@/src/domains/auth/auth-api';
import { cn } from '@/src/lib/utils';

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

      <div className="mt-auto">
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
