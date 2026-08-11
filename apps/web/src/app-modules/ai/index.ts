import { aiManifest } from './manifest';
import { aiGlobalRoutes, aiToolViewRoutes, aiWorkspaceRoutes } from './routes';
import { aiShellNavResolver } from './shell-nav';
import { aiSidebarConfig } from './sidebar-config';

export { aiManifest };
export {
  aiGlobalRoutes,
  aiWorkspaceRoutes,
  aiToolViewRoutes,
  ragSearchToolElement,
} from './routes';
export { aiSidebarConfig } from './sidebar-config';
export { aiShellNavResolver } from './shell-nav';

export const aiModule = {
  globalRoutes: aiGlobalRoutes,
  manifest: aiManifest,
  shellNavResolver: aiShellNavResolver,
  sidebarConfig: aiSidebarConfig,
  toolViewRoutes: aiToolViewRoutes,
  workspaceRoutes: aiWorkspaceRoutes,
} as const;
