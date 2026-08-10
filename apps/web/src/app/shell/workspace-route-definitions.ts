import { createElement } from 'react';

import { docsManifest } from '@/src/app-modules/docs';
import {
  adminRedirectRoutes,
  adminSectionRoutes,
  settingsManifest,
  workspaceSettingsRoute,
} from '@/src/app-modules/settings';
import { whiteboardManifest } from '@/src/app-modules/whiteboard';
import {
  APP_GLOBAL_ROUTES,
  APP_WORKSPACE_ROUTES,
  assertAppModuleStaticRouteContract,
} from './app-registry';
import { AdminLandingRedirect } from './redirects';

export const workspaceRouteDefinitions = [...APP_WORKSPACE_ROUTES];

export const staticDocsGlobalRoutes = APP_GLOBAL_ROUTES.filter(
  (route) => route.bootstrapAppId === docsManifest.appBarItem.id,
);
export const staticWhiteboardGlobalRoutes = APP_GLOBAL_ROUTES.filter(
  (route) => route.bootstrapAppId === whiteboardManifest.appBarItem.id,
);
export const staticAppGlobalRoutes = [...APP_GLOBAL_ROUTES];
export const staticWorkspaceSettingsRoute = workspaceSettingsRoute;
export const staticAdminLandingRoute = {
  path: '/admin',
  element: createElement(AdminLandingRedirect),
};
export const staticAdminRedirectRoutes = adminRedirectRoutes;
export const staticAdminSectionRoutes = adminSectionRoutes;
export const staticSettingsGlobalRoutes = [
  staticAdminLandingRoute,
  ...staticAdminRedirectRoutes,
  ...staticAdminSectionRoutes,
];

assertAppModuleStaticRouteContract(settingsManifest.appBarItem.id, {
  workspaceRoutes: [staticWorkspaceSettingsRoute],
  globalRoutes: staticSettingsGlobalRoutes,
});
