import { Tabs, TabsContent, TabsList, TabsTrigger } from '@open-work-hub/ui';
import { Download } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { DocumentArtifact } from '@/src/components/artifacts/DocumentArtifact';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import type { ArtifactBuffer } from '../../../api/agent-events';
import {
  getAiArtifact,
  listAiArtifactSources,
  type AiArtifact,
  type AiArtifactSource,
} from '../../../api/ai-artifacts-api';
import { AiArtifactSourceGrid } from './AiArtifactSourceGrid';
import { artifactDownloadSpec } from './artifact-download';

interface ReportArtifactState {
  detail: AiArtifact | null;
  detailSettled: boolean;
  sources: AiArtifactSource[];
  sourcesFailed: boolean;
  sourcesLoading: boolean;
}

const INITIAL_STATE: ReportArtifactState = {
  detail: null,
  detailSettled: false,
  sources: [],
  sourcesFailed: false,
  sourcesLoading: false,
};

export function AiReportArtifact({
  artifact,
  fallbackSources = null,
}: {
  artifact: ArtifactBuffer;
  fallbackSources?: ReactNode;
}) {
  const { token } = useAuth();
  const { workspaceSlug } = useParams<{ workspaceSlug: string }>();
  const { t } = useTranslation('apps');
  const [state, setState] = useState<ReportArtifactState>(INITIAL_STATE);
  const hasFallbackSources = fallbackSources !== null;
  const knownReport = artifact.kind === 'report' || hasFallbackSources;

  useEffect(() => {
    if (!token || !workspaceSlug || artifact.status === 'open') {
      setState({ ...INITIAL_STATE, detailSettled: true });
      return;
    }
    const controller = new AbortController();
    setState(INITIAL_STATE);
    getAiArtifact({
      artifactId: artifact.id,
      signal: controller.signal,
      token,
      workspaceSlug,
    })
      .then(async (detail) => {
        if (controller.signal.aborted) return;
        if (detail.kind !== 'report') {
          setState({
            ...INITIAL_STATE,
            detail,
            detailSettled: true,
          });
          return;
        }
        setState({
          ...INITIAL_STATE,
          detail,
          detailSettled: true,
          sourcesLoading: true,
        });
        try {
          const sources = await listAiArtifactSources({
            artifactId: artifact.id,
            signal: controller.signal,
            token,
            workspaceSlug,
          });
          if (controller.signal.aborted) return;
          setState({
            detail,
            detailSettled: true,
            sources,
            sourcesFailed: false,
            sourcesLoading: false,
          });
        } catch {
          if (controller.signal.aborted) return;
          setState({
            detail,
            detailSettled: true,
            sources: [],
            sourcesFailed: true,
            sourcesLoading: false,
          });
        }
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setState({
          ...INITIAL_STATE,
          detailSettled: true,
          sourcesFailed: knownReport && !hasFallbackSources,
        });
      });
    return () => controller.abort();
  }, [
    artifact.id,
    artifact.status,
    hasFallbackSources,
    knownReport,
    token,
    workspaceSlug,
  ]);

  const isReport = state.detail?.kind === 'report' || knownReport;
  const reportContent = state.detail?.contentMarkdown || artifact.content;
  const reportNumber =
    state.detail?.artifactNumber === null ||
    state.detail?.artifactNumber === undefined
      ? null
      : String(state.detail.artifactNumber);

  if (!state.detailSettled && !knownReport) {
    return <DocumentArtifact content={reportContent} />;
  }
  if (!isReport) {
    return <DocumentArtifact content={reportContent} />;
  }

  return (
    <div className="space-y-4">
      {reportNumber ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-app-border bg-app-bg px-3 py-2">
          <div className="min-w-0">
            <span className="app-text-micro text-app-ink/55">
              {t('ai.artifacts.reportDetail.numberLabel')}
            </span>
            <div className="truncate font-mono app-text-body-sm font-semibold text-app-ink">
              {reportNumber}
            </div>
          </div>
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-3 app-text-caption font-medium text-app-ink/75 hover:bg-app-surface-hover"
            type="button"
            onClick={() =>
              downloadReport({
                artifact,
                completedAt: state.detail?.completedAt ?? null,
                content: reportContent,
                completedAtLabel: t(
                  'ai.artifacts.reportDetail.download.completedAtLabel',
                ),
                numberLabel: t(
                  'ai.artifacts.reportDetail.download.numberLabel',
                ),
                reportNumber,
              })
            }
          >
            <Download aria-hidden="true" size={14} />
            {t('ai.artifacts.downloadMarkdown')}
          </button>
        </div>
      ) : null}
      <Tabs defaultValue="report" className="space-y-4">
        <TabsList aria-label={t('ai.artifacts.reportDetail.tabs.label')}>
          <TabsTrigger value="report">
            {t('ai.artifacts.reportDetail.tabs.report')}
          </TabsTrigger>
          <TabsTrigger value="sources">
            {t('ai.artifacts.reportDetail.tabs.sources')}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="report">
          <DocumentArtifact content={reportContent} />
        </TabsContent>
        <TabsContent value="sources">
          {state.sources.length > 0 ? (
            <AiArtifactSourceGrid sources={state.sources} />
          ) : fallbackSources ? (
            fallbackSources
          ) : state.sourcesLoading ? (
            <div
              className="rounded-md border border-app-border bg-app-bg p-6 text-center app-text-body-sm text-app-ink/55"
              role="status"
            >
              {t('ai.artifacts.reportDetail.sources.loading')}
            </div>
          ) : state.sourcesFailed ? (
            <div
              className="rounded-md border border-app-border bg-app-bg p-6 text-center app-text-body-sm text-app-danger"
              role="alert"
            >
              {t('ai.artifacts.reportDetail.sources.loadFailed')}
            </div>
          ) : (
            <AiArtifactSourceGrid sources={[]} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function downloadReport({
  artifact,
  completedAt,
  completedAtLabel,
  content,
  numberLabel,
  reportNumber,
}: {
  artifact: ArtifactBuffer;
  completedAt: string | null;
  completedAtLabel: string;
  content: string;
  numberLabel: string;
  reportNumber: string;
}) {
  const downloadSpec = artifactDownloadSpec(artifact);
  const metadata = [
    `${numberLabel}: ${reportNumber}`,
    completedAt ? `${completedAtLabel}: ${completedAt}` : null,
  ].filter((value): value is string => value !== null);
  downloadBlobAsFile(
    new Blob([`${metadata.join('\n')}\n\n${content}`], {
      type: downloadSpec.mimeType,
    }),
    `${reportNumber}_${downloadSpec.filename}`,
  );
}
