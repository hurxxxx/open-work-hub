import { aiManifest, aiModule } from '@/src/app-modules/ai';
import { announcementsManifest } from '@/src/app-modules/announcements/manifest';
import {
  businessFeatureModules,
  businessManifest,
  businessModule,
} from '@/src/app-modules/business';
import { chatbotManifest } from '@/src/app-modules/chatbot/manifest';
import {
  collaborationManifest,
  collaborationModule,
} from '@/src/app-modules/collaboration';
import {
  communityManifest,
  communityModule,
} from '@/src/app-modules/community';
import { diagramsManifest } from '@/src/app-modules/diagrams/manifest';
import { docsManifest } from '@/src/app-modules/docs/manifest';
import { emailAssistantManifest } from '@/src/app-modules/email-assistant';
import { filesManifest } from '@/src/app-modules/files/manifest';
import { homeManifest, homeModule } from '@/src/app-modules/home';
import { imageWizardManifest } from '@/src/app-modules/image-wizard';
import { mailManifest, mailModule } from '@/src/app-modules/mail';
import { meetingManifest } from '@/src/app-modules/meeting/manifest';
import { plannerManifest, plannerModule } from '@/src/app-modules/planner';
import { pmsManifest } from '@/src/app-modules/pms/manifest';
import { retrievalSearchManifest } from '@/src/app-modules/retrieval-search';
import { recordingManifest } from '@/src/app-modules/recording/manifest';
import { settingsManifest, settingsModule } from '@/src/app-modules/settings';
import { videoChatManifest } from '@/src/app-modules/video-chat/manifest';
import { webSearchManifest } from '@/src/app-modules/web-search/manifest';
import { whiteboardManifest } from '@/src/app-modules/whiteboard/manifest';
import type { FeatureModuleRegistryInput } from './feature-module-registry';

export {
  aiManifest,
  announcementsManifest,
  businessManifest,
  chatbotManifest,
  collaborationManifest,
  communityManifest,
  diagramsManifest,
  docsManifest,
  emailAssistantManifest,
  filesManifest,
  homeManifest,
  imageWizardManifest,
  mailManifest,
  meetingManifest,
  plannerManifest,
  pmsManifest,
  retrievalSearchManifest,
  recordingManifest,
  settingsManifest,
  videoChatManifest,
  webSearchManifest,
  whiteboardManifest,
};

export const DEFAULT_APP_MODULES = [
  homeModule,
  aiModule,
  collaborationModule,
  communityModule,
  mailModule,
  plannerModule,
  businessModule,
  settingsModule,
] as const;

export const DEFAULT_APP_MODULE_MANIFESTS = DEFAULT_APP_MODULES.map(
  (module) => module.manifest,
);

export const DEFAULT_FEATURE_MODULES: readonly FeatureModuleRegistryInput[] = [
  announcementsManifest,
  ...businessFeatureModules,
  webSearchManifest,
] as const;

export const DEFAULT_FEATURE_MODULE_MANIFESTS = DEFAULT_FEATURE_MODULES.map(
  (module) => ('manifest' in module ? module.manifest : module),
);

export const DEFAULT_PLATFORM_MODULE_MANIFESTS = [
  ...DEFAULT_APP_MODULE_MANIFESTS,
  chatbotManifest,
  ...DEFAULT_FEATURE_MODULE_MANIFESTS,
  docsManifest,
  meetingManifest,
  plannerManifest,
  pmsManifest,
  whiteboardManifest,
] as const;
