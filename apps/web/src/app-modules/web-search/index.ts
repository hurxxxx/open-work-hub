import { webSearchManifest } from './manifest';
import { webSearchAppRoutes } from './routes';

export { webSearchAppRoutes, webSearchManifest };

export const webSearchModule = {
  manifest: webSearchManifest,
  appRoutes: webSearchAppRoutes,
} as const;
