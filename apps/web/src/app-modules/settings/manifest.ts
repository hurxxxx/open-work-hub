import { Activity, Database, Lock, Settings, User } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const settingsManifest: AppModuleManifest = {
  appBarItem: { id: 'settings', title: 'settings', icon: Settings },
  defaultActiveNavItemId: 'settings-people',
  navItems: [
    { id: 'settings-general', title: 'settings-general', icon: Settings, category: 'Admin', appId: 'settings', absolutePath: '/admin/general' },
    { id: 'settings-people', title: 'settings-people', icon: User, category: 'Admin', appId: 'settings', absolutePath: '/admin/people' },
    { id: 'settings-workspaces', title: 'settings-workspaces', icon: Database, category: 'Admin', appId: 'settings', absolutePath: '/admin/workspaces' },
    { id: 'settings-security', title: 'settings-security', icon: Lock, category: 'Security', appId: 'settings', absolutePath: '/admin/security' },
    { id: 'settings-audit', title: 'settings-audit', icon: Activity, category: 'Security', appId: 'settings', absolutePath: '/admin/audit' },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/settings'],
  globalRoutePaths: [
    '/admin',
    '/admin/general',
    '/admin/people',
    '/admin/workspaces',
    '/admin/security',
    '/admin/audit',
  ],
};
