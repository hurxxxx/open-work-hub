import { Briefcase } from 'lucide-react';

import type {
  AppModuleManifest,
  NavItem,
} from '@/src/app/shell/navigation-types';
import type { CompiledFeatureShellRegistration } from '@/src/app/shell/feature-module-registry';
import { learningManifest } from '@/src/app-modules/learning/manifest';
import { businessFeatureShellRegistrations } from './feature-modules';

const BUSINESS_APP_ID = 'business' as const;

const BUSINESS_FEATURE_MANIFESTS = [
  learningManifest,
] as const;

function rewriteNavItem(item: NavItem, manifest: AppModuleManifest): NavItem {
  return {
    ...item,
    appId: BUSINESS_APP_ID,
    linkAppId: manifest.appBarItem.id as NavItem['linkAppId'],
  };
}

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
  ...BUSINESS_FEATURE_MANIFESTS.flatMap((manifest) =>
    manifest.navItems.map((item) => rewriteNavItem(item, manifest)),
  ),
  ...businessFeatureShellNavItems,
];

export const businessWorkspaceRoutePaths = BUSINESS_FEATURE_MANIFESTS.flatMap(
  (manifest) => manifest.workspaceRoutePaths,
).concat(
  businessFeatureShellRegistrations.flatMap((registration) => [
    registration.toolRoute.path,
    ...registration.workspaceRoutes.map((route) => route.path),
  ]),
);

const businessWorkspaceApiPrefixes = BUSINESS_FEATURE_MANIFESTS.flatMap(
  (manifest) => manifest.contract.workspaceApiPrefixes ?? [],
);

export const businessManifest: AppModuleManifest = {
  appBarItem: { id: 'business', title: 'business', icon: Briefcase },
  contract: {
    owner: 'business-app',
    permissions: [],
    apiDomain: null,
    workspaceApiPrefixes: businessWorkspaceApiPrefixes,
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
