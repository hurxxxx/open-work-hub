import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  ChatbotView,
  type ChatbotExperienceConfig,
} from '@/src/app-modules/chatbot/public-api';
import { LegacyIssueAnalysisArtifact } from './LegacyIssueAnalysisArtifact';
import { LegacyIssueEvidenceArtifact } from './LegacyIssueEvidenceArtifact';
import {
  LEGACY_ISSUE_SOURCE_ARTIFACT_TYPES,
  LegacyIssueReportArtifact,
} from './LegacyIssueReportArtifact';
import {
  LEGACY_ISSUE_ASSISTANT_PATH_SUFFIX,
  LEGACY_ISSUE_ASSISTANT_SCOPE_REF,
  LEGACY_ISSUE_ASSISTANT_SCOPE_RESOURCE_ID,
} from '../legacy-issue-datasets';

export function CoreBusinessLegacyIssueAssistantView() {
  const { t } = useTranslation(['apps']);
  const experience = useMemo<ChatbotExperienceConfig>(
    () => ({
      title: t('coreBusiness.assistant.title'),
      routeAppId: 'legacy-issues',
      routePathSuffix: LEGACY_ISSUE_ASSISTANT_PATH_SUFFIX,
      conversationScope: {
        ref: LEGACY_ISSUE_ASSISTANT_SCOPE_REF,
        resourceId: LEGACY_ISSUE_ASSISTANT_SCOPE_RESOURCE_ID,
      },
      sidebarEyebrow: t('coreBusiness.assistant.eyebrow'),
      sidebarTitle: t('coreBusiness.assistant.conversationsTitle'),
      emptyGreeting: t('coreBusiness.assistant.emptyGreeting'),
      emptySubline: t('coreBusiness.assistant.emptySubline'),
      executionMode: 'durable_background',
      sourceArtifactTypes: LEGACY_ISSUE_SOURCE_ARTIFACT_TYPES,
      artifactRenderers: [
        {
          type: 'document',
          render: (artifact, context) => (
            <LegacyIssueReportArtifact
              artifact={artifact}
              relatedArtifacts={context.relatedArtifacts}
            />
          ),
        },
        {
          type: 'legacy-issue-analysis',
          render: (artifact) => (
            <LegacyIssueAnalysisArtifact content={artifact.content} />
          ),
        },
        {
          type: 'legacy-issue-evidence',
          render: (artifact) => (
            <LegacyIssueEvidenceArtifact content={artifact.content} />
          ),
        },
      ],
    }),
    [t],
  );

  return <ChatbotView experience={experience} />;
}
