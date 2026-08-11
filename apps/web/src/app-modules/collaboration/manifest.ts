import { Users } from 'lucide-react';

import type {
  AppModuleManifest,
  NavItem,
} from '@/src/app/shell/navigation-types';
import { bentoManifest } from '@/src/app-modules/bento/manifest';
import { diagramsManifest } from '@/src/app-modules/diagrams/manifest';
import { docsManifest } from '@/src/app-modules/docs/manifest';
import { filesManifest } from '@/src/app-modules/files/manifest';
import { meetingManifest } from '@/src/app-modules/meeting/manifest';
import { pmsManifest } from '@/src/app-modules/pms/manifest';
import { recordingManifest } from '@/src/app-modules/recording/manifest';
import { videoChatManifest } from '@/src/app-modules/video-chat/manifest';
import { whiteboardManifest } from '@/src/app-modules/whiteboard/manifest';

const COLLABORATION_APP_ID = 'collaboration' as const;

const COLLABORATION_FEATURE_MANIFESTS = [
  pmsManifest,
  docsManifest,
  filesManifest,
  meetingManifest,
  whiteboardManifest,
  diagramsManifest,
  bentoManifest,
  recordingManifest,
  videoChatManifest,
] as const;

const COLLABORATION_GLOBAL_ROUTE_MANIFESTS = [
  docsManifest,
  whiteboardManifest,
] as const;

function buildRootNavItem(manifest: AppModuleManifest): NavItem {
  return {
    id: manifest.appBarItem.id,
    title: manifest.appBarItem.title,
    icon: manifest.appBarItem.icon,
    category: 'collaboration-apps',
    appId: COLLABORATION_APP_ID,
    linkAppId: manifest.appBarItem.id as NavItem['linkAppId'],
  };
}

function rewriteNavItem(item: NavItem, manifest: AppModuleManifest): NavItem {
  return {
    ...item,
    appId: COLLABORATION_APP_ID,
    linkAppId: manifest.appBarItem.id as NavItem['linkAppId'],
  };
}

function rewriteWorkspaceRoutePath(
  routePath: string,
  _featureAppId: string,
): string {
  return routePath;
}

export const collaborationNavItems: NavItem[] =
  COLLABORATION_FEATURE_MANIFESTS.flatMap((manifest) => {
    const navItems = manifest.navItems.map((item) =>
      rewriteNavItem(item, manifest),
    );
    return navItems.length > 0 ? navItems : [buildRootNavItem(manifest)];
  });

export const collaborationWorkspaceRoutePaths =
  COLLABORATION_FEATURE_MANIFESTS.flatMap((manifest) =>
    manifest.workspaceRoutePaths.map((routePath) =>
      rewriteWorkspaceRoutePath(routePath, manifest.appBarItem.id),
    ),
  );

const collaborationGlobalRoutePaths =
  COLLABORATION_GLOBAL_ROUTE_MANIFESTS.flatMap(
    (manifest) => manifest.globalRoutePaths ?? [],
  );
const collaborationWorkspaceApiPrefixes =
  COLLABORATION_FEATURE_MANIFESTS.flatMap(
    (manifest) => manifest.contract.workspaceApiPrefixes ?? [],
  );
const collaborationWorkspaceApiPublicPrefixes =
  COLLABORATION_FEATURE_MANIFESTS.flatMap(
    (manifest) => manifest.contract.workspaceApiPublicPrefixes ?? [],
  );
const collaborationWorkspaceApiPublicQueryBypasses =
  COLLABORATION_FEATURE_MANIFESTS.flatMap(
    (manifest) => manifest.contract.workspaceApiPublicQueryBypasses ?? [],
  );

export const collaborationManifest: AppModuleManifest = {
  appBarItem: {
    id: 'collaboration',
    title: 'collaboration',
    icon: Users,
  },
  contract: {
    owner: 'collaboration-app',
    permissions: [],
    apiDomain: null,
    workspaceApiPrefixes: collaborationWorkspaceApiPrefixes,
    workspaceApiPublicPrefixes: collaborationWorkspaceApiPublicPrefixes,
    workspaceApiPublicQueryBypasses:
      collaborationWorkspaceApiPublicQueryBypasses,
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/pms/views/pms-view-route.spec.ts',
      'apps/web/src/app-modules/docs/views/docs-view-model.spec.ts',
      'apps/api/tests/test_pms_issues.py',
    ],
  },
  defaultActiveNavItemId: '',
  navItems: [...collaborationNavItems],
  workspaceRoutePaths: [...collaborationWorkspaceRoutePaths],
  globalRoutePaths: collaborationGlobalRoutePaths,
};
