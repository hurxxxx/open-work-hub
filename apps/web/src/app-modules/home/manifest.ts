import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { Home } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const homeManifest: AppModuleManifest = {
  appBarItem: { id: 'home', title: 'home', icon: Home },
  contract: {
    owner: 'platform-shell',
    permissions: [],
    apiDomain: null,
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/web/src/app/shell/app-registry.spec.ts'],
  },
  defaultActiveNavItemId: '',
  navItems: [],
  appRoutePaths: [getAppRoutePattern('home.root')],
};
