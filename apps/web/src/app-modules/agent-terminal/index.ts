import { agentTerminalManifest } from './manifest';
import { agentTerminalGlobalRoutes } from './routes';

export { agentTerminalGlobalRoutes, agentTerminalManifest };

export const agentTerminalModule = {
  globalRoutes: agentTerminalGlobalRoutes,
  manifest: agentTerminalManifest,
} as const;
