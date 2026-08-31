import { bentoAiBackgroundWorkSource } from './background-work';
import { bentoManifest } from './manifest';
import { bentoWorkspaceRoutes } from './routes';

export { bentoAiBackgroundWorkSource, bentoManifest, bentoWorkspaceRoutes };

export const bentoModule = {
  backgroundWorkSources: [bentoAiBackgroundWorkSource],
  manifest: bentoManifest,
  workspaceRoutes: bentoWorkspaceRoutes,
} as const;
