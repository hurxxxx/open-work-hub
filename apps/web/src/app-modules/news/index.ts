import { newsManifest } from './manifest';
import { newsGlobalRoutes } from './routes';
import { newsShellNavResolver } from './shell-nav';

export { newsGlobalRoutes, newsManifest, newsShellNavResolver };

export const newsModule = {
  globalRoutes: newsGlobalRoutes,
  manifest: newsManifest,
  shellNavResolver: newsShellNavResolver,
} as const;
