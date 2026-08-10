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
  personalAttendanceManifest,
  personalAttendanceModule,
} from '@/src/app-modules/personal-attendance';
import {
  communityManifest,
  communityModule,
} from '@/src/app-modules/community';
import { diagramsManifest } from '@/src/app-modules/diagrams/manifest';
import { docsManifest } from '@/src/app-modules/docs/manifest';
import { documentTranslateManifest } from '@/src/app-modules/document-translate';
import { draftingManifest } from '@/src/app-modules/drafting';
import { emailAssistantManifest } from '@/src/app-modules/email-assistant';
import { filesManifest } from '@/src/app-modules/files/manifest';
import { fmeaCompareManifest } from '@/src/app-modules/fmea-compare';
import { homeManifest, homeModule } from '@/src/app-modules/home';
import { imageWizardManifest } from '@/src/app-modules/image-wizard';
import { imdsMineralsManifest } from '@/src/app-modules/imds-minerals';
import { learningManifest } from '@/src/app-modules/learning/manifest';
import { lawSearchManifest } from '@/src/app-modules/law-search';
import { mailManifest, mailModule } from '@/src/app-modules/mail';
import {
  managementTasksManifest,
  managementTasksModule,
} from '@/src/app-modules/management-tasks';
import { meetingManifest } from '@/src/app-modules/meeting/manifest';
import { newsManifest, newsModule } from '@/src/app-modules/news';
import { patentAutomationManifest } from '@/src/app-modules/patent-automation/manifest';
import { patentAnalysisManifest } from '@/src/app-modules/patent-analysis';
import { patentComposeManifest } from '@/src/app-modules/patent-compose';
import { patentReportManifest } from '@/src/app-modules/patent-report';
import { plmManifest } from '@/src/app-modules/plm/manifest';
import { plannerManifest, plannerModule } from '@/src/app-modules/planner';
import { pmsManifest } from '@/src/app-modules/pms/manifest';
import { pptAssistantManifest } from '@/src/app-modules/ppt-assistant';
import { qaAssistantManifest } from '@/src/app-modules/qa-assistant/manifest';
import { retrievalSearchManifest } from '@/src/app-modules/retrieval-search';
import { recordingManifest } from '@/src/app-modules/recording/manifest';
import { settingsManifest, settingsModule } from '@/src/app-modules/settings';
import { specCompareManifest } from '@/src/app-modules/spec-compare';
import { videoChatManifest } from '@/src/app-modules/video-chat/manifest';
import {
  researchTrendsManifest,
  standardsMonitorManifest,
  webSearchManifest,
} from '@/src/app-modules/web-search/manifest';
import { whiteboardManifest } from '@/src/app-modules/whiteboard/manifest';
import type { FeatureModuleRegistryInput } from './feature-module-registry';

export {
  aiManifest,
  announcementsManifest,
  businessManifest,
  chatbotManifest,
  collaborationManifest,
  communityManifest,
  personalAttendanceManifest,
  diagramsManifest,
  docsManifest,
  documentTranslateManifest,
  draftingManifest,
  emailAssistantManifest,
  filesManifest,
  fmeaCompareManifest,
  homeManifest,
  imageWizardManifest,
  imdsMineralsManifest,
  learningManifest,
  lawSearchManifest,
  mailManifest,
  managementTasksManifest,
  meetingManifest,
  newsManifest,
  patentAutomationManifest,
  patentAnalysisManifest,
  patentComposeManifest,
  patentReportManifest,
  plmManifest,
  plannerManifest,
  pmsManifest,
  pptAssistantManifest,
  qaAssistantManifest,
  retrievalSearchManifest,
  researchTrendsManifest,
  recordingManifest,
  settingsManifest,
  specCompareManifest,
  standardsMonitorManifest,
  videoChatManifest,
  webSearchManifest,
  whiteboardManifest,
};

export const DEFAULT_APP_MODULES = [
  homeModule,
  aiModule,
  collaborationModule,
  communityModule,
  personalAttendanceModule,
  mailModule,
  plannerModule,
  newsModule,
  managementTasksModule,
  businessModule,
  settingsModule,
] as const;

export const DEFAULT_APP_MODULE_MANIFESTS = DEFAULT_APP_MODULES.map(
  (module) => module.manifest,
);

export const DEFAULT_FEATURE_MODULES: readonly FeatureModuleRegistryInput[] = [
  announcementsManifest,
  ...businessFeatureModules,
  qaAssistantManifest,
  webSearchManifest,
  researchTrendsManifest,
  standardsMonitorManifest,
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
