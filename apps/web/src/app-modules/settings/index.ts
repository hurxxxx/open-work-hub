import { settingsManifest } from './manifest';
import { settingsShellNavResolver } from './shell-nav';

export { adminRedirectRoutes, adminSectionRoutes } from './routes';
export { settingsShellNavResolver } from './shell-nav';
export { settingsManifest };

export const settingsModule = {
  manifest: settingsManifest,
  shellNavResolver: settingsShellNavResolver,
} as const;
