import { createElement } from 'react';

import { docsManifest } from '@/src/app-modules/docs';
import {
  adminRedirectRoutes,
  adminSectionRoutes,
  settingsManifest,
} from '@/src/app-modules/settings';
import { whiteboardManifest } from '@/src/app-modules/whiteboard';
import {
  APP_GLOBAL_ROUTES,
  APP_ROUTES,
  assertAppModuleStaticRouteContract,
} from './app-registry';
import { AdminLandingRedirect } from './redirects';

export const appRouteDefinitions = [...APP_ROUTES];

export const staticDocsGlobalRoutes = APP_GLOBAL_ROUTES.filter(
  (route) => route.appId === docsManifest.appBarItem.id,
);
export const staticWhiteboardGlobalRoutes = APP_GLOBAL_ROUTES.filter(
  (route) => route.appId === whiteboardManifest.appBarItem.id,
);
export const staticAppGlobalRoutes = [...APP_GLOBAL_ROUTES];
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
  appRoutes: [],
  globalRoutes: staticSettingsGlobalRoutes,
});
