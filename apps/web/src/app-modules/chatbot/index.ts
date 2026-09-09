import { chatbotManifest } from './manifest';
import { chatbotAppRoutes } from './routes';

export { chatbotAppRoutes, chatbotManifest };

export const chatbotModule = {
  manifest: chatbotManifest,
  appRoutes: chatbotAppRoutes,
} as const;
