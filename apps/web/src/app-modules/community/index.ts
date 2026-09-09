import { communityManifest } from './manifest';
import { communityGlobalRoutes } from './routes';
import { communitySidebarConfig } from './sidebar';

export { communityGlobalRoutes, communityManifest, communitySidebarConfig };

export const communityModule = {
  globalRoutes: communityGlobalRoutes,
  manifest: communityManifest,
  sidebarConfig: communitySidebarConfig,
  appRoutes: [],
} as const;
