import { chatbotManifest } from './manifest';
import { chatbotWorkspaceRoutes } from './routes';

export { chatbotManifest, chatbotWorkspaceRoutes };

export const chatbotModule = {
  manifest: chatbotManifest,
  workspaceRoutes: chatbotWorkspaceRoutes,
} as const;
