import { Briefcase } from 'lucide-react';

import type { AppModuleManifest, NavItem } from '@/src/app/shell/navigation-types';
import type { CompiledFeatureShellRegistration } from '@/src/app/shell/feature-module-registry';
import { businessFeatureShellRegistrations } from './feature-modules';

const BUSINESS_APP_ID = 'business' as const;

function buildFeatureShellNavItem(
  registration: CompiledFeatureShellRegistration,
): NavItem {
  return {
    ...registration.navItem,
    appId: BUSINESS_APP_ID,
    linkAppId: registration.appId,
  };
}

const businessFeatureShellNavItems = businessFeatureShellRegistrations.map(
  buildFeatureShellNavItem,
);

export const businessNavItems: NavItem[] = [
  ...businessFeatureShellNavItems,
];

export const businessWorkspaceRoutePaths =
  businessFeatureShellRegistrations.flatMap((registration) => [
    registration.toolRoute.path,
    ...registration.workspaceRoutes.map((route) => route.path),
  ]);

export const businessManifest: AppModuleManifest = {
  appBarItem: { id: 'business', title: 'business', icon: Briefcase },
  contract: {
    owner: 'business-app',
    permissions: [],
    apiDomain: null,
    workspaceApiPrefixes: [],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/api/tests/test_ai.py',
      'apps/api/tests/test_retrieval.py',
    ],
  },
  defaultActiveNavItemId: '',
  navItems: [...businessNavItems],
  workspaceRoutePaths: [...businessWorkspaceRoutePaths],
};
