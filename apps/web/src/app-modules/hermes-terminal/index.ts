import { hermesTerminalManifest } from './manifest';
import { hermesTerminalWorkspaceRoutes } from './routes';

export { hermesTerminalManifest } from './manifest';
export { hermesTerminalWorkspaceRoutes } from './routes';

export const hermesTerminalModule = {
  manifest: hermesTerminalManifest,
  workspaceRoutes: hermesTerminalWorkspaceRoutes,
} as const;
