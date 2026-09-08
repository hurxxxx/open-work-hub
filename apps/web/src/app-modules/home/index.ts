import { homeManifest } from './manifest';
import { homeAppRoutes } from './routes';

export { homeAppRoutes, homeManifest };

export const homeModule = {
  manifest: homeManifest,
  appRoutes: homeAppRoutes,
} as const;
