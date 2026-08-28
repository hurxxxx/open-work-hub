import { diagramsManifest } from './manifest';
import { diagramsWorkspaceRoutes } from './routes';
import { diagramsSidebarConfig } from './sidebar';

export { diagramsManifest };
export { diagramsToolElement, diagramsWorkspaceRoutes } from './routes';
export { diagramsSidebarConfig } from './sidebar';

export const diagramsModule = {
  manifest: diagramsManifest,
  sidebarConfig: diagramsSidebarConfig,
  workspaceRoutes: diagramsWorkspaceRoutes,
} as const;
