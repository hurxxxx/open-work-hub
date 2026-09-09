import { bentoAiBackgroundWorkSource } from './background-work';
import { bentoManifest } from './manifest';
import { bentoAppRoutes } from './routes';

export { bentoAiBackgroundWorkSource, bentoAppRoutes, bentoManifest };

export const bentoModule = {
  backgroundWorkSources: [bentoAiBackgroundWorkSource],
  manifest: bentoManifest,
  appRoutes: bentoAppRoutes,
} as const;
