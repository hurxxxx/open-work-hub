import { docsManifest } from './manifest';
import { docsAppRoutes, docsGlobalRoutes } from './routes';
import { docsSidebarConfig } from './sidebar-config';

export { docsAppRoutes, docsGlobalRoutes, docsToolElement } from './routes';
export { docsSidebarConfig } from './sidebar-config';
export { docsManifest };

export const docsModule = {
  globalRoutes: docsGlobalRoutes,
  manifest: docsManifest,
  sidebarConfig: docsSidebarConfig,
  appRoutes: docsAppRoutes,
} as const;
