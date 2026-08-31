import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  ChatbotView,
  type ChatbotExperienceConfig,
} from '@/src/app-modules/chatbot/public-api';
import {
  buildFilesRagSourcesPreview,
  FilesRagSourcesArtifact,
} from './FilesRagSourcesArtifact';

export function FilesChatView() {
  const { t } = useTranslation('apps');
  const experience = useMemo<ChatbotExperienceConfig>(
    () => ({
      title: t('files.chat.title'),
      routeAppId: 'files',
      routeId: 'files.chat',
      conversationScope: {
        ref: 'files',
        resourceId: 'workspace',
      },
      sidebarEyebrow: t('files.chat.eyebrow'),
      sidebarTitle: t('files.chat.conversationsTitle'),
      emptyGreeting: t('files.chat.emptyGreeting'),
      emptySubline: t('files.chat.emptySubline'),
      autoOpenArtifacts: false,
      artifactRenderers: [
        {
          type: 'files-rag-sources',
          preview: (artifact) => buildFilesRagSourcesPreview(artifact.content),
          render: (artifact) => (
            <FilesRagSourcesArtifact content={artifact.content} />
          ),
        },
      ],
    }),
    [t],
  );

  return <ChatbotView experience={experience} />;
}
