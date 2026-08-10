import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button, InlineNotice } from '@open-alm/ui';

import {
  getAdminDocumentProcessingSnapshot,
  type AdminDocumentProcessingSnapshot,
  type DocumentVisionWorkload,
} from './admin-document-processing-api';
import { EmptyPanel, SurfaceCard } from './admin-shared';

function StatusText({ ready }: { ready: boolean }) {
  const { t } = useTranslation('apps');
  return (
    <span className={ready ? 'text-app-success-text' : 'text-app-danger-text'}>
      {t(
        ready
          ? 'admin.console.documentProcessing.values.ready'
          : 'admin.console.documentProcessing.values.notReady',
      )}
    </span>
  );
}

function BooleanText({ value }: { value: boolean }) {
  const { t } = useTranslation('apps');
  return (
    <span>
      {t(
        value
          ? 'admin.console.documentProcessing.values.enabled'
          : 'admin.console.documentProcessing.values.disabled',
      )}
    </span>
  );
}

function ConfiguredText({ value }: { value: boolean }) {
  const { t } = useTranslation('apps');
  return (
    <span>
      {t(
        value
          ? 'admin.console.documentProcessing.values.configured'
          : 'admin.console.documentProcessing.values.notConfigured',
      )}
    </span>
  );
}

function DetailRows({
  rows,
}: {
  rows: Array<{ label: string; value: React.ReactNode }>;
}) {
  return (
    <dl className="divide-y divide-app-border">
      {rows.map((row) => (
        <div
          className="grid gap-1 py-2 sm:grid-cols-[180px_minmax(0,1fr)] sm:items-start"
          key={row.label}
        >
          <dt className="app-text-caption text-app-ink/55">{row.label}</dt>
          <dd className="app-text-body-sm min-w-0 break-words text-app-ink">
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function workloadReadiness(
  workload: DocumentVisionWorkload,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  if (workload.ready) {
    return t('admin.console.documentProcessing.values.ready');
  }
  if (workload.readiness_code === 'admin.ai_model_capability_mismatch') {
    return t('admin.console.documentProcessing.values.capabilityMismatch');
  }
  return t('admin.console.documentProcessing.values.notReady');
}

export function AdminDocumentProcessingSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const [snapshot, setSnapshot] =
    useState<AdminDocumentProcessingSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await getAdminDocumentProcessingSnapshot(token));
    } catch {
      setError(t('admin.console.documentProcessing.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t, token]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !snapshot) {
    return (
      <EmptyPanel
        description={t('admin.console.documentProcessing.loadingDescription')}
        title={t('admin.console.documentProcessing.loadingTitle')}
      />
    );
  }

  if (!snapshot) {
    return (
      <EmptyPanel
        description={t('admin.console.documentProcessing.loadFailed')}
        title={t('admin.console.documentProcessing.emptyTitle')}
      />
    );
  }

  const gatewayReady =
    snapshot.providers.length > 0 &&
    snapshot.providers.every((provider) => provider.ready);
  const visionReady =
    snapshot.vision.enabled &&
    snapshot.vision.workloads.length > 0 &&
    snapshot.vision.workloads.every((workload) => workload.ready);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-app-border pb-3">
        <p className="app-text-body-sm text-app-ink/55">
          {t('admin.console.documentProcessing.readOnlyNotice')}
        </p>
        <Button
          disabled={loading}
          onClick={() => void load()}
          size="dense"
          variant="secondary"
        >
          <RefreshCw size={14} />
          {t('admin.console.documentProcessing.refresh')}
        </Button>
      </div>

      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
      {!visionReady ? (
        <InlineNotice tone="warning">
          {t('admin.console.documentProcessing.visionWarning')}
        </InlineNotice>
      ) : null}

      <SurfaceCard
        description={t('admin.console.documentProcessing.runtime.description')}
        title={t('admin.console.documentProcessing.runtime.title')}
      >
        <DetailRows
          rows={[
            {
              label: t('admin.console.documentProcessing.fields.ragEnabled'),
              value: <BooleanText value={snapshot.enabled} />,
            },
            {
              label: t('admin.console.documentProcessing.fields.apiHealth'),
              value: <StatusText ready={snapshot.ready} />,
            },
            {
              label: t(
                'admin.console.documentProcessing.fields.providerHealth',
              ),
              value: <StatusText ready={gatewayReady} />,
            },
            {
              label: t('admin.console.documentProcessing.fields.workerHealth'),
              value: t('admin.console.documentProcessing.values.notObserved'),
            },
            {
              label: t(
                'admin.console.documentProcessing.fields.configurationSource',
              ),
              value: t('admin.console.documentProcessing.values.environment'),
            },
            {
              label: t('admin.console.documentProcessing.fields.queryTimeout'),
              value: `${snapshot.query_timeout_ms} ms`,
            },
          ]}
        />
      </SurfaceCard>

      <div className="grid gap-4 xl:grid-cols-2">
        <SurfaceCard
          description={t('admin.console.documentProcessing.ocr.description')}
          title={t('admin.console.documentProcessing.ocr.title')}
        >
          <DetailRows
            rows={[
              {
                label: t('admin.console.documentProcessing.fields.provider'),
                value: snapshot.ocr.provider,
              },
              {
                label: t('admin.console.documentProcessing.fields.endpoint'),
                value: (
                  <ConfiguredText value={snapshot.ocr.endpoint_configured} />
                ),
              },
              {
                label: t('admin.console.documentProcessing.fields.forceOcr'),
                value: <BooleanText value={snapshot.ocr.force_ocr} />,
              },
              {
                label: t('admin.console.documentProcessing.fields.engine'),
                value: snapshot.ocr.engine,
              },
              {
                label: t('admin.console.documentProcessing.fields.languages'),
                value: snapshot.ocr.languages.join(', '),
              },
              {
                label: t('admin.console.documentProcessing.fields.minimumText'),
                value: snapshot.ocr.minimum_text_chars,
              },
            ]}
          />
        </SurfaceCard>

        <SurfaceCard
          description={t('admin.console.documentProcessing.vision.description')}
          title={t('admin.console.documentProcessing.vision.title')}
        >
          <DetailRows
            rows={[
              {
                label: t('admin.console.documentProcessing.fields.enabled'),
                value: <BooleanText value={snapshot.vision.enabled} />,
              },
              {
                label: t('admin.console.documentProcessing.fields.pageLimit'),
                value: snapshot.vision.max_pages,
              },
              {
                label: t('admin.console.documentProcessing.fields.renderDpi'),
                value: snapshot.vision.dpi,
              },
            ]}
          />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-app-border text-left">
                  <th className="app-text-overline py-2 pr-3 text-app-ink/55">
                    {t('admin.console.documentProcessing.fields.workload')}
                  </th>
                  <th className="app-text-overline py-2 pr-3 text-app-ink/55">
                    {t(
                      'admin.console.documentProcessing.fields.effectiveModel',
                    )}
                  </th>
                  <th className="app-text-overline py-2 text-app-ink/55">
                    {t('admin.console.documentProcessing.fields.status')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-app-border">
                {snapshot.vision.workloads.map((workload) => (
                  <tr key={workload.workload_id}>
                    <td className="app-text-body-sm py-2 pr-3 text-app-ink">
                      {workload.workload_id}
                    </td>
                    <td className="app-text-body-sm py-2 pr-3 text-app-ink">
                      {workload.model_key ??
                        t(
                          'admin.console.documentProcessing.values.notResolved',
                        )}
                    </td>
                    <td
                      className={`app-text-body-sm py-2 ${workload.ready ? 'text-app-success-text' : 'text-app-danger-text'}`}
                    >
                      {workloadReadiness(workload, t)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard
        description={t('admin.console.documentProcessing.models.description')}
        title={t('admin.console.documentProcessing.models.title')}
      >
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-app-border text-left">
                {['function', 'provider', 'model', 'detail'].map((field) => (
                  <th
                    className="app-text-overline py-2 pr-4 text-app-ink/55"
                    key={field}
                  >
                    {t(`admin.console.documentProcessing.columns.${field}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-app-border">
              <tr>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {t('admin.console.documentProcessing.functions.embedding')}
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {snapshot.embedding.provider}
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {snapshot.embedding.model}
                </td>
                <td className="app-text-body-sm py-2 text-app-ink/65">
                  {t('admin.console.documentProcessing.values.batchSize', {
                    count: snapshot.embedding.batch_size,
                  })}
                </td>
              </tr>
              <tr>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {t('admin.console.documentProcessing.functions.rerank')}
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {snapshot.rerank.provider}
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {snapshot.rerank.model}
                </td>
                <td className="app-text-body-sm py-2 text-app-ink/65">
                  {t('admin.console.documentProcessing.values.candidateLimit', {
                    count: snapshot.rerank.candidate_limit,
                  })}
                </td>
              </tr>
              <tr>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {t('admin.console.documentProcessing.functions.vectorIndex')}
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {snapshot.vector_index.provider}
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {snapshot.vector_index.active_collection ??
                    snapshot.vector_index.collection_prefix}
                </td>
                <td className="app-text-body-sm py-2 text-app-ink/65">
                  {t('admin.console.documentProcessing.values.genericRag')}
                </td>
              </tr>
              <tr>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {t('admin.console.documentProcessing.functions.keywordIndex')}
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {snapshot.keyword_index.provider}
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {snapshot.keyword_index.index_prefix}
                </td>
                <td className="app-text-body-sm py-2 text-app-ink/65">
                  OpenSearch
                </td>
              </tr>
              <tr>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  {t('admin.console.documentProcessing.functions.legacyVector')}
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  PostgreSQL
                </td>
                <td className="app-text-body-sm py-2 pr-4 text-app-ink">
                  pgvector
                </td>
                <td className="app-text-body-sm py-2 text-app-ink/65">
                  {t('admin.console.documentProcessing.values.dimensions', {
                    count: snapshot.legacy_issues.embedding_dimensions,
                  })}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SurfaceCard>

      <div className="grid gap-4 xl:grid-cols-2">
        <SurfaceCard
          description={t('admin.console.documentProcessing.legacy.description')}
          title={t('admin.console.documentProcessing.legacy.title')}
        >
          <DetailRows
            rows={[
              {
                label: t(
                  'admin.console.documentProcessing.fields.attachmentIndex',
                ),
                value: (
                  <BooleanText
                    value={snapshot.legacy_issues.attachment_index_enabled}
                  />
                ),
              },
              {
                label: t(
                  'admin.console.documentProcessing.fields.alwaysVision',
                ),
                value: (
                  <BooleanText
                    value={snapshot.legacy_issues.always_use_vision}
                  />
                ),
              },
              {
                label: t(
                  'admin.console.documentProcessing.fields.semanticSearch',
                ),
                value: (
                  <BooleanText
                    value={snapshot.legacy_issues.semantic_search_enabled}
                  />
                ),
              },
              {
                label: t(
                  'admin.console.documentProcessing.fields.maximumChunks',
                ),
                value: snapshot.legacy_issues.maximum_chunks,
              },
            ]}
          />
        </SurfaceCard>
        <SurfaceCard
          description={t(
            'admin.console.documentProcessing.chunking.description',
          )}
          title={t('admin.console.documentProcessing.chunking.title')}
        >
          <DetailRows
            rows={[
              {
                label: t('admin.console.documentProcessing.fields.strategy'),
                value: snapshot.chunking.strategy,
              },
              {
                label: t('admin.console.documentProcessing.fields.targetChars'),
                value: snapshot.chunking.target_chars,
              },
              {
                label: t(
                  'admin.console.documentProcessing.fields.maximumChars',
                ),
                value: snapshot.chunking.hard_max_chars,
              },
              {
                label: t(
                  'admin.console.documentProcessing.fields.overlapChars',
                ),
                value: snapshot.chunking.overlap_chars,
              },
            ]}
          />
        </SurfaceCard>
      </div>
    </div>
  );
}
