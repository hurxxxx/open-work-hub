import { settingsManifest } from './manifest';
import { settingsShellNavResolver } from './shell-nav';

export { settingsManifest };
export {
  adminRedirectRoutes,
  adminSectionRoutes,
  workspaceSettingsRoute,
} from './routes';
export { settingsShellNavResolver } from './shell-nav';

export const settingsModule = {
  manifest: settingsManifest,
  shellNavResolver: settingsShellNavResolver,
} as const;
