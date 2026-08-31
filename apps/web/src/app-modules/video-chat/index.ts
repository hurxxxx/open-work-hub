import { videoChatManifest } from './manifest';
import { videoChatWorkspaceRoutes } from './routes';

export { videoChatManifest, videoChatWorkspaceRoutes };

export const videoChatModule = {
  manifest: videoChatManifest,
  workspaceRoutes: videoChatWorkspaceRoutes,
} as const;
