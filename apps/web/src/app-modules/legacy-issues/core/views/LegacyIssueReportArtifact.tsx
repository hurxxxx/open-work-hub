import {
  AiReportArtifact,
  type ArtifactBuffer,
} from '@/src/app-modules/chatbot/public-api';
import { LegacyIssueAnalysisArtifact } from './LegacyIssueAnalysisArtifact';
import { LegacyIssueEvidenceArtifact } from './LegacyIssueEvidenceArtifact';

export const LEGACY_ISSUE_SOURCE_ARTIFACT_TYPES = [
  'legacy-issue-analysis',
  'legacy-issue-evidence',
] as const;

export function LegacyIssueReportArtifact({
  artifact,
  relatedArtifacts,
}: {
  artifact: ArtifactBuffer;
  relatedArtifacts: readonly ArtifactBuffer[];
}) {
  const sources = relatedArtifacts.filter((candidate) =>
    LEGACY_ISSUE_SOURCE_ARTIFACT_TYPES.includes(
      candidate.type as (typeof LEGACY_ISSUE_SOURCE_ARTIFACT_TYPES)[number],
    ),
  );

  return (
    <AiReportArtifact
      artifact={artifact}
      fallbackSources={
        sources.length > 0 ? (
          <div className="space-y-5">
            {sources.map((source) => (
              <section
                key={source.id}
                className="rounded-md border border-app-border bg-app-surface p-4"
              >
                {source.type === 'legacy-issue-analysis' ? (
                  <LegacyIssueAnalysisArtifact content={source.content} />
                ) : (
                  <LegacyIssueEvidenceArtifact content={source.content} />
                )}
              </section>
            ))}
          </div>
        ) : null
      }
    />
  );
}
