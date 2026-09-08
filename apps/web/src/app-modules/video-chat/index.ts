import { videoChatManifest } from './manifest';
import { videoChatAppRoutes } from './routes';

export { videoChatAppRoutes, videoChatManifest };

export const videoChatModule = {
  manifest: videoChatManifest,
  appRoutes: videoChatAppRoutes,
} as const;
