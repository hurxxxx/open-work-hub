import { FileUploadProvider } from '@/src/app-modules/files';
import { bentoAiBackgroundWorkSource } from '@/src/app-modules/bento';
import { collaborationManifest } from './manifest';
import {
  collaborationGlobalRoutes,
  collaborationToolViewRoutes,
  collaborationWorkspaceRoutes,
} from './routes';
import { collaborationShellNavResolver } from './shell-nav';
import { collaborationSidebarConfig } from './sidebar';

export {
  collaborationGlobalRoutes,
  collaborationManifest,
  collaborationShellNavResolver,
  collaborationSidebarConfig,
  collaborationToolViewRoutes,
  collaborationWorkspaceRoutes,
};

export const collaborationModule = {
  backgroundWorkSources: [bentoAiBackgroundWorkSource],
  globalRoutes: collaborationGlobalRoutes,
  manifest: collaborationManifest,
  shellNavResolver: collaborationShellNavResolver,
  shellProviders: [FileUploadProvider],
  sidebarConfig: collaborationSidebarConfig,
  toolViewRoutes: collaborationToolViewRoutes,
  workspaceRoutes: collaborationWorkspaceRoutes,
} as const;
