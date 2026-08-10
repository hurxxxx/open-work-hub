import { useTranslation } from 'react-i18next';
import { Download, ExternalLink, FileJson, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Button, EmptyState, InlineNotice } from '@ai-do/ui';

import type {
  PatentPriorArtArtifact,
  PatentPriorArtReportFormat,
  PatentPriorArtResult,
} from '../api/patent-prior-art-api';
import {
  patentPriorArtQueryFailureMessageKey,
  safePatentDocumentUrl,
} from '../model/patent-prior-art-view-model';

function ArtifactIcon({ kind }: { kind: PatentPriorArtArtifact['kind'] }) {
  return kind === 'report_markdown' ? (
    <FileText aria-hidden="true" size={15} />
  ) : (
    <FileJson aria-hidden="true" size={15} />
  );
}

export function PatentPriorArtResultPanel({
  busy,
  onDownload,
  onDownloadReport,
  reportFormats,
  result,
}: {
  busy: boolean;
  onDownload: (artifact: PatentPriorArtArtifact) => void;
  onDownloadReport: (reportFormat: PatentPriorArtReportFormat) => void;
  reportFormats: readonly PatentPriorArtReportFormat[];
  result: PatentPriorArtResult;
}) {
  const { t } = useTranslation('apps');
  const failedQueries = (result.executed_queries ?? []).filter(
    (query) => query.status === 'failed',
  );
  const partial = result.partial === true || failedQueries.length > 0;

  return (
    <section
      aria-labelledby="patent-prior-art-result-title"
      className="space-y-4"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="app-text-title-md" id="patent-prior-art-result-title">
            {t('ai.patentPriorArt.results.title')}
          </h2>
          <p className="mt-1 app-text-body-sm text-app-ink/55">
            {t('ai.patentPriorArt.results.candidateCount', {
              count: result.candidate_count,
            })}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(result.artifacts ?? []).map((artifact) => (
            <Button
              disabled={busy}
              key={artifact.id}
              onClick={() => onDownload(artifact)}
              variant="secondary"
            >
              <ArtifactIcon kind={artifact.kind} />
              {t(`ai.patentPriorArt.artifacts.${artifact.kind}`)}
              <Download aria-hidden="true" size={14} />
            </Button>
          ))}
        </div>
      </div>

      {partial ? (
        <InlineNotice role="status" tone="warning">
          <div>
            <p className="font-semibold">
              {t('ai.patentPriorArt.results.partialTitle')}
            </p>
            <p className="mt-1">
              {t('ai.patentPriorArt.results.partialDescription')}
            </p>
            {failedQueries.length > 0 ? (
              <div className="mt-3">
                <p className="app-text-control-sm font-semibold">
                  {t('ai.patentPriorArt.results.failedScopes')}
                </p>
                <ul className="mt-1.5 space-y-1.5">
                  {failedQueries.map((query, index) => (
                    <li
                      className="rounded-md border border-app-warning-border bg-app-surface/60 px-2.5 py-2"
                      key={`${query.source_id}-${query.jurisdiction}-${index}`}
                    >
                      <span className="block app-text-body-sm font-medium">
                        {t('ai.patentPriorArt.results.failedScopeItem', {
                          jurisdiction: query.jurisdiction,
                          source: query.source_label,
                        })}
                      </span>
                      <span className="block app-text-caption opacity-80">
                        {t(
                          patentPriorArtQueryFailureMessageKey(
                            query.failure_code,
                          ),
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </InlineNotice>
      ) : null}

      {reportFormats.length > 0 ? (
        <section
          aria-labelledby="patent-prior-art-reports-title"
          className="rounded-xl border border-app-border bg-app-surface p-4"
        >
          <h3 className="app-text-title-sm" id="patent-prior-art-reports-title">
            {t('ai.patentPriorArt.reports.title')}
          </h3>
          <p className="mt-1 app-text-body-sm text-app-ink/55">
            {t('ai.patentPriorArt.reports.description')}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {reportFormats.map((reportFormat) => (
              <Button
                disabled={busy}
                key={reportFormat}
                onClick={() => onDownloadReport(reportFormat)}
                variant="secondary"
              >
                <FileText aria-hidden="true" size={15} />
                {t(`ai.patentPriorArt.reports.${reportFormat}`)}
                <Download aria-hidden="true" size={14} />
              </Button>
            ))}
          </div>
        </section>
      ) : null}

      <section
        aria-labelledby="patent-prior-art-candidates-title"
        className="rounded-xl border border-app-border bg-app-surface"
      >
        <div className="border-b border-app-border px-4 py-3">
          <h3
            className="app-text-title-sm"
            id="patent-prior-art-candidates-title"
          >
            {t('ai.patentPriorArt.results.candidates')}
          </h3>
        </div>
        {(result.candidates ?? []).length === 0 ? (
          <div className="p-6">
            <EmptyState
              description={t('ai.patentPriorArt.results.candidatesEmpty')}
              title={t('ai.patentPriorArt.results.candidatesEmptyTitle')}
            />
          </div>
        ) : (
          <ol className="divide-y divide-app-border">
            {(result.candidates ?? []).map((candidate) => (
              <li
                className="p-4"
                key={`${candidate.rank}-${candidate.publication_number}`}
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-app-accent/10 app-text-control-sm font-bold text-app-accent">
                    {candidate.rank}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <h4 className="app-text-body-sm font-semibold text-app-ink">
                          {candidate.title}
                        </h4>
                        <p className="mt-0.5 app-text-caption text-app-ink/55">
                          {candidate.publication_number} ·{' '}
                          {candidate.jurisdiction}
                        </p>
                      </div>
                      <span className="rounded-full border border-app-border bg-app-surface-sidebar px-2.5 py-1 app-text-caption text-app-ink/65">
                        {t(
                          `ai.patentPriorArt.relevance.${candidate.relevance_band}`,
                        )}
                      </span>
                    </div>

                    <dl className="mt-3 grid gap-x-4 gap-y-1 app-text-caption sm:grid-cols-2">
                      {(candidate.assignees ?? []).length > 0 ? (
                        <div className="flex gap-2">
                          <dt className="shrink-0 text-app-ink/45">
                            {t('ai.patentPriorArt.results.assignees')}
                          </dt>
                          <dd className="text-app-ink/70">
                            {(candidate.assignees ?? []).join(', ')}
                          </dd>
                        </div>
                      ) : null}
                      {candidate.publication_date ? (
                        <div className="flex gap-2">
                          <dt className="shrink-0 text-app-ink/45">
                            {t('ai.patentPriorArt.results.publicationDate')}
                          </dt>
                          <dd className="text-app-ink/70">
                            {candidate.publication_date}
                          </dd>
                        </div>
                      ) : null}
                      {(candidate.classification_codes ?? []).length > 0 ? (
                        <div className="flex gap-2 sm:col-span-2">
                          <dt className="shrink-0 text-app-ink/45">
                            {t('ai.patentPriorArt.results.classifications')}
                          </dt>
                          <dd className="text-app-ink/70">
                            {(candidate.classification_codes ?? []).join(', ')}
                          </dd>
                        </div>
                      ) : null}
                    </dl>

                    {candidate.summary || candidate.abstract ? (
                      <p className="mt-3 whitespace-pre-wrap app-text-body-sm leading-relaxed text-app-ink/75">
                        {candidate.summary || candidate.abstract}
                      </p>
                    ) : null}

                    {(candidate.match_reasons ?? []).length > 0 ? (
                      <ul className="mt-3 flex flex-wrap gap-1.5">
                        {(candidate.match_reasons ?? []).map((reason) => (
                          <li
                            className="rounded bg-app-surface-sidebar px-2 py-1 app-text-caption text-app-ink/65"
                            key={reason}
                          >
                            {reason}
                          </li>
                        ))}
                      </ul>
                    ) : null}

                    {safePatentDocumentUrl(candidate.external_url) ? (
                      <a
                        className="mt-3 inline-flex items-center gap-1 app-text-control-sm text-app-accent hover:underline"
                        href={
                          safePatentDocumentUrl(candidate.external_url) ??
                          undefined
                        }
                        rel="noreferrer"
                        target="_blank"
                      >
                        {t('ai.patentPriorArt.results.openSource')}
                        <ExternalLink aria-hidden="true" size={13} />
                      </a>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section
        aria-labelledby="patent-prior-art-queries-title"
        className="rounded-xl border border-app-border bg-app-surface"
      >
        <div className="border-b border-app-border px-4 py-3">
          <h3 className="app-text-title-sm" id="patent-prior-art-queries-title">
            {t('ai.patentPriorArt.results.executedQueries')}
          </h3>
        </div>
        <div className="custom-scrollbar overflow-x-auto">
          <table className="w-full min-w-[46rem] border-collapse text-left app-text-body-sm">
            <thead className="bg-app-surface-sidebar text-app-ink/55">
              <tr>
                <th className="px-4 py-2 font-semibold">
                  {t('ai.patentPriorArt.results.source')}
                </th>
                <th className="px-4 py-2 font-semibold">
                  {t('ai.patentPriorArt.results.jurisdiction')}
                </th>
                <th className="px-4 py-2 font-semibold">
                  {t('ai.patentPriorArt.results.query')}
                </th>
                <th className="px-4 py-2 text-right font-semibold">
                  {t('ai.patentPriorArt.results.hits')}
                </th>
                <th className="px-4 py-2 font-semibold">
                  {t('ai.patentPriorArt.results.queryStatus')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-app-border">
              {(result.executed_queries ?? []).map((query, index) => (
                <tr key={`${query.source_id}-${query.jurisdiction}-${index}`}>
                  <td className="px-4 py-2 text-app-ink/70">
                    {query.source_label}
                  </td>
                  <td className="px-4 py-2 text-app-ink/70">
                    {query.jurisdiction}
                  </td>
                  <td className="max-w-xl whitespace-pre-wrap px-4 py-2 font-mono app-text-caption text-app-ink">
                    {query.query_text}
                  </td>
                  <td className="px-4 py-2 text-right text-app-ink/70">
                    {query.result_count ??
                      t('ai.patentPriorArt.common.notAvailable')}
                  </td>
                  <td className="px-4 py-2 text-app-ink/70">
                    {t(
                      `ai.patentPriorArt.results.queryStatuses.${query.status === 'failed' ? 'failed' : 'succeeded'}`,
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(result.executed_queries ?? []).length === 0 ? (
            <p className="p-4 app-text-body-sm text-app-ink/50">
              {t('ai.patentPriorArt.results.queriesEmpty')}
            </p>
          ) : null}
        </div>
      </section>

      <section
        aria-labelledby="patent-prior-art-report-title"
        className="rounded-xl border border-app-border bg-app-surface p-5"
      >
        <h3 className="app-text-title-sm" id="patent-prior-art-report-title">
          {t('ai.patentPriorArt.results.report')}
        </h3>
        {result.report_markdown ? (
          <article className="prose prose-sm mt-4 max-w-none text-app-ink dark:prose-invert">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {result.report_markdown}
            </ReactMarkdown>
          </article>
        ) : (
          <p className="mt-3 app-text-body-sm text-app-ink/50">
            {t('ai.patentPriorArt.results.reportEmpty')}
          </p>
        )}
      </section>
    </section>
  );
}
