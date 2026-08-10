import { Home } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const homeManifest: AppModuleManifest = {
  appBarItem: { id: 'home', title: 'home', icon: Home },
  defaultActiveNavItemId: '',
  navItems: [],
  workspaceRoutePaths: ['/w/:workspaceSlug/home'],
};

