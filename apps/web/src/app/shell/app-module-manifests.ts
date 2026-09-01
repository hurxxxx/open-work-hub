import { agentTerminalModule } from '@/src/app-modules/agent-terminal';
import { bentoModule } from '@/src/app-modules/bento';
import { chatbotModule } from '@/src/app-modules/chatbot';
import { communityModule } from '@/src/app-modules/community';
import { diagramsModule } from '@/src/app-modules/diagrams';
import { docsModule } from '@/src/app-modules/docs';
import { filesModule } from '@/src/app-modules/files';
import { homeModule } from '@/src/app-modules/home';
import { hermesTerminalModule } from '@/src/app-modules/hermes-terminal';
import { mailModule } from '@/src/app-modules/mail';
import { meetingModule } from '@/src/app-modules/meeting';
import { plannerModule } from '@/src/app-modules/planner';
import { pmsModule } from '@/src/app-modules/pms';
import { recordingModule } from '@/src/app-modules/recording';
import { retrievalSearchModule } from '@/src/app-modules/retrieval-search';
import { settingsModule } from '@/src/app-modules/settings';
import { videoChatModule } from '@/src/app-modules/video-chat';
import { webSearchModule } from '@/src/app-modules/web-search';
import { whiteboardModule } from '@/src/app-modules/whiteboard';
import {
  agentTerminalManifest,
  announcementsManifest,
  bentoManifest,
  chatbotManifest,
  communityManifest,
  diagramsManifest,
  docsManifest,
  filesManifest,
  homeManifest,
  hermesTerminalManifest,
  mailManifest,
  meetingManifest,
  plannerManifest,
  pmsManifest,
  recordingManifest,
  retrievalSearchManifest,
  settingsManifest,
  videoChatManifest,
  webSearchManifest,
  whiteboardManifest,
} from './app-contract-manifests';
import type { FeatureModuleRegistryInput } from './feature-module-registry';

export {
  agentTerminalManifest,
  announcementsManifest,
  bentoManifest,
  chatbotManifest,
  communityManifest,
  diagramsManifest,
  docsManifest,
  filesManifest,
  homeManifest,
  hermesTerminalManifest,
  mailManifest,
  meetingManifest,
  plannerManifest,
  pmsManifest,
  recordingManifest,
  retrievalSearchManifest,
  settingsManifest,
  videoChatManifest,
  webSearchManifest,
  whiteboardManifest,
};

/** Executable identities are leaf apps. Categories never own routes. */
export const DEFAULT_APP_MODULES = [
  homeModule,
  agentTerminalModule,
  hermesTerminalModule,
  chatbotModule,
  webSearchModule,
  pmsModule,
  docsModule,
  filesModule,
  mailModule,
  communityModule,
  whiteboardModule,
  diagramsModule,
  bentoModule,
  plannerModule,
  meetingModule,
  videoChatModule,
  recordingModule,
  retrievalSearchModule,
] as const;

/** Shell-owned navigation surfaces are not executable app identities. */
export const DEFAULT_SHELL_MODULES = [settingsModule] as const;

export const DEFAULT_APP_MODULE_MANIFESTS = DEFAULT_APP_MODULES.map(
  (module) => module.manifest,
);

export const DEFAULT_SHELL_MODULE_MANIFESTS = DEFAULT_SHELL_MODULES.map(
  (module) => module.manifest,
);

export const DEFAULT_FEATURE_MODULES: readonly FeatureModuleRegistryInput[] = [
  announcementsManifest,
] as const;

export const DEFAULT_FEATURE_MODULE_MANIFESTS = DEFAULT_FEATURE_MODULES.map(
  (module) => ('manifest' in module ? module.manifest : module),
);

export const DEFAULT_PLATFORM_MODULE_MANIFESTS = [
  ...DEFAULT_APP_MODULE_MANIFESTS,
  ...DEFAULT_FEATURE_MODULE_MANIFESTS,
] as const;
