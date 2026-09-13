import { agentTerminalManifest } from '@/src/app-modules/agent-terminal/manifest';
import { announcementsManifest } from '@/src/app-modules/announcements/manifest';
import { bentoManifest } from '@/src/app-modules/bento/manifest';
import { chatbotManifest } from '@/src/app-modules/chatbot/manifest';
import { communityManifest } from '@/src/app-modules/community/manifest';
import { diagramsManifest } from '@/src/app-modules/diagrams/manifest';
import { docsManifest } from '@/src/app-modules/docs/manifest';
import { filesManifest } from '@/src/app-modules/files/manifest';
import { homeManifest } from '@/src/app-modules/home/manifest';
import { mailManifest } from '@/src/app-modules/mail/manifest';
import { meetingManifest } from '@/src/app-modules/meeting/manifest';
import { plannerManifest } from '@/src/app-modules/planner/manifest';
import { pmsManifest } from '@/src/app-modules/pms/manifest';
import { recordingManifest } from '@/src/app-modules/recording/manifest';
import { retrievalSearchManifest } from '@/src/app-modules/retrieval-search/manifest';
import { settingsManifest } from '@/src/app-modules/settings/manifest';
import { videoChatManifest } from '@/src/app-modules/video-chat/manifest';
import { webSearchManifest } from '@/src/app-modules/web-search/manifest';
import { whiteboardManifest } from '@/src/app-modules/whiteboard/manifest';

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

export const DEFAULT_APP_CONTRACT_MANIFESTS = [
  homeManifest,
  agentTerminalManifest,
  chatbotManifest,
  webSearchManifest,
  pmsManifest,
  docsManifest,
  filesManifest,
  mailManifest,
  communityManifest,
  whiteboardManifest,
  diagramsManifest,
  bentoManifest,
  plannerManifest,
  meetingManifest,
  videoChatManifest,
  recordingManifest,
  retrievalSearchManifest,
] as const;

export const DEFAULT_FEATURE_CONTRACT_MANIFESTS = [
  announcementsManifest,
] as const;

export const DEFAULT_PLATFORM_CONTRACT_MANIFESTS = [
  ...DEFAULT_APP_CONTRACT_MANIFESTS,
  ...DEFAULT_FEATURE_CONTRACT_MANIFESTS,
] as const;
