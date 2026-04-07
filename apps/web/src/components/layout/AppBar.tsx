import { Link } from 'react-router-dom';
import { DropdownMenu } from '@aidoo/ui';

import { APP_BAR_ITEMS } from '@/src/constants';
import type { ThemePreference } from '@/src/domains/auth/auth-api';
import type { AuthUser } from '@/src/domains/auth/auth-api';
import { cn } from '@/src/lib/utils';

const featureByAppId: Partial<Record<'home' | 'ai' | 'pms' | 'docs' | 'planner', string>> = {
  ai: 'nav.ai',
  docs: 'nav.docs',
  pms: 'nav.pms',
  planner: 'nav.planner',
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
  currentThemePreference,
  onLogout,
  onOpenAccount,
  onOpenSecurity,
  onOpenAdmin,
  onThemePreferenceChange,
}: {
  activeAppId: string;
  currentUser: AuthUser;
  currentThemePreference: ThemePreference;
  onLogout: () => Promise<void>;
  onOpenAccount: () => void;
  onOpenSecurity: () => void;
  onOpenAdmin?: () => void;
  onThemePreferenceChange: (value: ThemePreference) => void;
}) {
  const visibleItems = APP_BAR_ITEMS.filter((item) => {
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
          to={item.path}
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
        <DropdownMenu
          items={[
            {
              id: 'profile-summary',
              label: (
                <div className="grid gap-0.5 py-1">
                  <strong className="text-[0.95rem] text-[var(--ui-color-ink)]">
                    {currentUser.display_name}
                  </strong>
                  <span className="text-[0.78rem] text-[var(--ui-color-ink-muted)]">
                    {currentUser.email}
                  </span>
                  <span className="text-[0.72rem] uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                    {currentUser.primary_org_unit?.name ?? '조직 미지정'}
                  </span>
                </div>
              ),
              disabled: true,
            },
            {
              id: 'account',
              label: '내 계정',
              onSelect: onOpenAccount,
              separatorBefore: true,
            },
            {
              id: 'security',
              label: '보안 설정',
              onSelect: onOpenSecurity,
            },
            {
              id: 'theme-system',
              label: `${currentThemePreference === 'system' ? '✓ ' : ''}테마: 시스템`,
              onSelect: () => onThemePreferenceChange('system'),
              separatorBefore: true,
            },
            {
              id: 'theme-light',
              label: `${currentThemePreference === 'light' ? '✓ ' : ''}테마: 라이트`,
              onSelect: () => onThemePreferenceChange('light'),
            },
            {
              id: 'theme-dark',
              label: `${currentThemePreference === 'dark' ? '✓ ' : ''}테마: 다크`,
              onSelect: () => onThemePreferenceChange('dark'),
            },
            ...(onOpenAdmin
              ? [
                  {
                    id: 'admin',
                    label: '관리 콘솔',
                    onSelect: onOpenAdmin,
                    separatorBefore: true,
                  },
                ]
              : []),
            {
              id: 'logout',
              label: '로그아웃',
              onSelect: () => {
                void onLogout();
              },
              separatorBefore: true,
              tone: 'danger',
            },
          ]}
          trigger={(
            <button
              aria-label="사용자 메뉴"
              className="w-10 h-10 bg-orange-500 rounded-full flex items-center justify-center text-white text-[0.95rem] font-semibold cursor-pointer border-2 border-white/60 shadow-lg shadow-orange-500/25"
              type="button"
            >
              {getUserInitials(currentUser.display_name || currentUser.full_name)}
            </button>
          )}
        />
      </div>
    </div>
  );
}
