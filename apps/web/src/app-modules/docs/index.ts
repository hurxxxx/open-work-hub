import { docsManifest } from './manifest';
import { docsGlobalRoutes, docsWorkspaceRoutes } from './routes';
import { docsSidebarConfig } from './sidebar-config';

export { docsManifest };
export {
  docsGlobalRoutes,
  docsToolElement,
  docsWorkspaceRoutes,
} from './routes';
export { docsSidebarConfig } from './sidebar-config';

export const docsModule = {
  globalRoutes: docsGlobalRoutes,
  manifest: docsManifest,
  sidebarConfig: docsSidebarConfig,
  workspaceRoutes: docsWorkspaceRoutes,
} as const;
