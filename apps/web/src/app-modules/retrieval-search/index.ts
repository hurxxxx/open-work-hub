import { retrievalSearchManifest } from './manifest';
import { retrievalSearchAppRoutes } from './routes';

export { retrievalSearchManifest } from './manifest';
export { retrievalSearchAppRoutes, retrievalSearchElement } from './routes';

export const retrievalSearchModule = {
  manifest: retrievalSearchManifest,
  appRoutes: retrievalSearchAppRoutes,
} as const;
