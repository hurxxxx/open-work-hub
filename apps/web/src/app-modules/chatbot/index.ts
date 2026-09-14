import { chatbotManifest } from './manifest';
import { chatbotAppRoutes } from './routes';
import { chatbotSidebarConfig } from './sidebar';

export { chatbotAppRoutes, chatbotManifest };

export const chatbotModule = {
  manifest: chatbotManifest,
  appRoutes: chatbotAppRoutes,
  sidebarConfig: chatbotSidebarConfig,
} as const;
