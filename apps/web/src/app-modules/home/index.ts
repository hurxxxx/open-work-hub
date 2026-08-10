import { homeManifest } from './manifest';
import { homeWorkspaceRoutes } from './routes';

export { homeManifest, homeWorkspaceRoutes };

export const homeModule = {
  manifest: homeManifest,
  workspaceRoutes: homeWorkspaceRoutes,
} as const;
