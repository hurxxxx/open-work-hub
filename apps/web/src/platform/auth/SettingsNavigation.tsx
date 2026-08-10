import { Bell, Monitor, Newspaper, Palette, Shield, User } from 'lucide-react';

import { cn } from '@/src/lib/utils';
import type {
  SettingsSection,
  SettingsTranslator,
} from './settings-page-model';

export function SettingsNavigation({
  activeSection,
  onSectionChange,
  t,
}: {
  activeSection: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
  t: SettingsTranslator;
}) {
  const navItems = [
    { id: 'profile' as const, label: t('auth:settings.profile'), icon: User },
    {
      id: 'appearance' as const,
      label: t('auth:settings.appearance'),
      icon: Palette,
    },
    {
      id: 'security' as const,
      label: t('auth:settings.security'),
      icon: Shield,
    },
    {
      id: 'notifications' as const,
      label: t('auth:settings.notifications'),
      icon: Bell,
    },
    {
      id: 'releaseNotes' as const,
      label: t('auth:settings.releaseNotes'),
      icon: Newspaper,
    },
    {
      id: 'openWorkHubDesktop' as const,
      label: t('auth:settings.openWorkHubDesktop'),
      icon: Monitor,
    },
  ];

  return (
    <nav className="space-y-1">
      {navItems.map((item) => (
        <button
          key={item.id}
          onClick={() => onSectionChange(item.id)}
          type="button"
          className={cn(
            'app-text-control flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left transition-colors',
            activeSection === item.id
              ? 'bg-app-surface-hover font-medium text-app-ink'
              : 'text-app-ink/55 hover:bg-app-surface-hover/50 hover:text-app-ink',
          )}
        >
          <item.icon size={15} />
          {item.label}
        </button>
      ))}
    </nav>
  );
}
