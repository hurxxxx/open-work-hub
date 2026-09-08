import { hermesTerminalManifest } from './manifest';
import { hermesTerminalAppRoutes } from './routes';

export { hermesTerminalManifest } from './manifest';
export { hermesTerminalAppRoutes } from './routes';

export const hermesTerminalModule = {
  manifest: hermesTerminalManifest,
  appRoutes: hermesTerminalAppRoutes,
} as const;
