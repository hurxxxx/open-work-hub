import {
  agentTerminalManifest,
  agentTerminalModule,
} from '@/src/app-modules/agent-terminal';
import { announcementsManifest } from '@/src/app-modules/announcements/manifest';
import { bentoManifest, bentoModule } from '@/src/app-modules/bento';
import { chatbotManifest, chatbotModule } from '@/src/app-modules/chatbot';
import {
  communityManifest,
  communityModule,
} from '@/src/app-modules/community';
import { diagramsManifest, diagramsModule } from '@/src/app-modules/diagrams';
import { docsManifest, docsModule } from '@/src/app-modules/docs';
import { filesManifest, filesModule } from '@/src/app-modules/files';
import { homeManifest, homeModule } from '@/src/app-modules/home';
import { mailManifest, mailModule } from '@/src/app-modules/mail';
import { meetingManifest, meetingModule } from '@/src/app-modules/meeting';
import { plannerManifest, plannerModule } from '@/src/app-modules/planner';
import { pmsManifest, pmsModule } from '@/src/app-modules/pms';
import {
  recordingManifest,
  recordingModule,
} from '@/src/app-modules/recording';
import {
  retrievalSearchManifest,
  retrievalSearchModule,
} from '@/src/app-modules/retrieval-search';
import { settingsManifest, settingsModule } from '@/src/app-modules/settings';
import {
  videoChatManifest,
  videoChatModule,
} from '@/src/app-modules/video-chat';
import {
  webSearchManifest,
  webSearchModule,
} from '@/src/app-modules/web-search';
import {
  whiteboardManifest,
  whiteboardModule,
} from '@/src/app-modules/whiteboard';
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
