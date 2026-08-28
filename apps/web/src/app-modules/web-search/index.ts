import { webSearchManifest } from './manifest';
import { webSearchWorkspaceRoutes } from './routes';

export { webSearchManifest, webSearchWorkspaceRoutes };

export const webSearchModule = {
  manifest: webSearchManifest,
  workspaceRoutes: webSearchWorkspaceRoutes,
} as const;
