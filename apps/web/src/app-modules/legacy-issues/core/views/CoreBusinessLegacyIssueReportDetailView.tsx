import { Tabs, TabsContent, TabsList, TabsTrigger } from '@ai-do/ui';
import {
  ArrowLeft,
  Database,
  Download,
  ExternalLink,
  FileSearch,
  Loader2,
  Lock,
  Share2,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { DocumentArtifact } from '@/src/components/artifacts/DocumentArtifact';
import { UserDateTime } from '@/src/components/date/UserDateTime';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  getLegacyIssueReport,
  getLegacyIssueReportQueryRows,
  listLegacyIssueReportQueries,
  listLegacyIssueReportSources,
  shareLegacyIssueReport,
  unshareLegacyIssueReport,
  type LegacyIssueReportDetail,
  type LegacyIssueReportQuery,
  type LegacyIssueReportQueryRows,
  type LegacyIssueReportSource,
} from '../api/legacy-issue-assistant-report-api';
import {
  LEGACY_ISSUE_ASSISTANT_PATH_SUFFIX,
  LEGACY_ISSUE_REPORTS_PATH_SUFFIX,
} from '../legacy-issue-datasets';
import {
  LegacyIssuePageHeader,
  LegacyIssueToolbarButton,
} from './LegacyIssuePageParts';
import { LegacyIssueReportDataGrid } from './LegacyIssueReportDataGrid';

const QUERY_ROW_PAGE_SIZE = 100;

export function CoreBusinessLegacyIssueReportDetailView() {
  const { reportNumber = '', workspaceSlug = '' } = useParams<{
    reportNumber: string;
    workspaceSlug: string;
  }>();
  const { token, user } = useAuth();
  const { t } = useTranslation(['apps', 'common']);
  const [detail, setDetail] = useState<LegacyIssueReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [sharePending, setSharePending] = useState(false);
  const [shareFailed, setShareFailed] = useState(false);
  const [activeTab, setActiveTab] = useState('report');
  const shareRequestIdRef = useRef(0);
  const shareControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    shareControllerRef.current?.abort();
    shareRequestIdRef.current += 1;
    setSharePending(false);
    setShareFailed(false);
    setActiveTab('report');
    if (!token || !workspaceSlug || !reportNumber) {
      setDetail(null);
      setLoading(false);
      setLoadFailed(true);
      return () => controller.abort();
    }
    setDetail(null);
    setLoading(true);
    setLoadFailed(false);
    getLegacyIssueReport({
      reportId: reportNumber,
      signal: controller.signal,
      token,
      workspaceSlug,
    })
      .then((response) => {
        if (!controller.signal.aborted) setDetail(response);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadFailed(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
      shareControllerRef.current?.abort();
    };
  }, [reportNumber, token, workspaceSlug]);

  const reportsPath = buildWorkspaceAppPath(
    workspaceSlug,
    'legacy-issues',
    LEGACY_ISSUE_REPORTS_PATH_SUFFIX,
  );
  const isOwner = Boolean(detail && user?.id === detail.owner_user_id);

  const toggleWorkspaceShare = async () => {
    if (!detail || !token || !workspaceSlug || !isOwner || sharePending) return;
    shareControllerRef.current?.abort();
    const controller = new AbortController();
    shareControllerRef.current = controller;
    const requestId = shareRequestIdRef.current + 1;
    shareRequestIdRef.current = requestId;
    setSharePending(true);
    setShareFailed(false);
    try {
      const response =
        detail.visibility === 'workspace'
          ? await unshareLegacyIssueReport({
              reportId: detail.report_number,
              signal: controller.signal,
              token,
              workspaceSlug,
            })
          : await shareLegacyIssueReport({
              reportId: detail.report_number,
              signal: controller.signal,
              token,
              workspaceSlug,
            });
      if (
        !controller.signal.aborted &&
        shareRequestIdRef.current === requestId
      ) {
        setDetail(response);
      }
    } catch {
      if (
        !controller.signal.aborted &&
        shareRequestIdRef.current === requestId
      ) {
        setShareFailed(true);
      }
    } finally {
      if (shareRequestIdRef.current === requestId) {
        setSharePending(false);
      }
    }
  };

  const downloadReport = () => {
    if (!detail) return;
    const markdown = [
      `${t('coreBusiness.reports.download.number')}: ${detail.report_number}`,
      `${t('coreBusiness.reports.download.generatedAt')}: ${
        detail.completed_at || detail.created_at
      }`,
      '',
      detail.content,
    ].join('\n');
    downloadBlobAsFile(
      new Blob([markdown], { type: 'text/markdown;charset=utf-8' }),
      reportDownloadFilename(detail),
    );
  };

  if (loading) {
    return (
      <ReportPageState
        label={t('common:feedback.loading')}
        role="status"
        spinning
      />
    );
  }
  if (loadFailed || !detail) {
    return (
      <ReportPageState
        label={t('coreBusiness.reports.errors.detailFailed')}
        role="alert"
      />
    );
  }

  const conversationPath =
    isOwner && detail.conversation_id
      ? `${buildWorkspaceAppPath(
          workspaceSlug,
          'legacy-issues',
          LEGACY_ISSUE_ASSISTANT_PATH_SUFFIX,
        )}?${new URLSearchParams({
          a: detail.report_id,
          c: detail.conversation_id,
        }).toString()}`
      : null;

  return (
    <div className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
      <LegacyIssuePageHeader
        actions={
          <>
            {conversationPath ? (
              <Link className="app-control h-9 px-3" to={conversationPath}>
                <ExternalLink aria-hidden="true" size={16} />
                {t('coreBusiness.reports.actions.openConversation')}
              </Link>
            ) : null}
            <LegacyIssueToolbarButton
              icon={<Download aria-hidden="true" size={16} />}
              label={t('coreBusiness.reports.actions.download')}
              onClick={downloadReport}
            />
            {isOwner ? (
              <LegacyIssueToolbarButton
                disabled={sharePending}
                icon={
                  sharePending ? (
                    <Loader2
                      aria-hidden="true"
                      className="animate-spin"
                      size={16}
                    />
                  ) : detail.visibility === 'workspace' ? (
                    <Lock aria-hidden="true" size={16} />
                  ) : (
                    <Share2 aria-hidden="true" size={16} />
                  )
                }
                label={t(
                  detail.visibility === 'workspace'
                    ? 'coreBusiness.reports.actions.unshare'
                    : 'coreBusiness.reports.actions.share',
                )}
                onClick={() => void toggleWorkspaceShare()}
              />
            ) : null}
          </>
        }
        eyebrow={detail.report_number}
        title={detail.title}
      />
      <main className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="mx-auto max-w-[96rem] space-y-4">
          <Link
            className="inline-flex items-center gap-1.5 app-text-body-sm font-medium text-app-accent hover:underline"
            to={reportsPath}
          >
            <ArrowLeft aria-hidden="true" size={15} />
            {t('coreBusiness.reports.actions.backToList')}
          </Link>

          <section className="rounded-lg border border-app-border bg-app-surface p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="app-text-micro font-semibold text-app-accent">
                  {detail.report_number}
                </p>
                {detail.question ? (
                  <p className="mt-2 app-text-body text-app-ink/80">
                    {detail.question}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2 app-text-micro text-app-ink/55">
                <span>
                  {detail.visibility === 'workspace'
                    ? t('coreBusiness.reports.visibility.workspace')
                    : t('coreBusiness.reports.visibility.private')}
                </span>
                {detail.owner_name ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>{detail.owner_name}</span>
                  </>
                ) : null}
                {detail.completed_at ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <UserDateTime
                      value={detail.completed_at}
                      options={{ hourCycle: 'h23' }}
                    />
                  </>
                ) : null}
              </div>
            </div>
            {shareFailed ? (
              <p className="mt-3 app-text-body-sm text-app-danger" role="alert">
                {t('coreBusiness.reports.errors.shareFailed')}
              </p>
            ) : null}
          </section>

          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList aria-label={t('coreBusiness.reports.detail.tabs.label')}>
              <TabsTrigger value="report">
                {t('coreBusiness.reports.detail.tabs.report')}
              </TabsTrigger>
              <TabsTrigger value="queries">
                {t('coreBusiness.reports.detail.tabs.queries', {
                  count: detail.query_count,
                })}
              </TabsTrigger>
              <TabsTrigger value="sources">
                {t('coreBusiness.reports.detail.tabs.sources', {
                  count: detail.source_count,
                })}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="report" className="mt-4">
              <section className="rounded-lg border border-app-border bg-app-surface p-5">
                <DocumentArtifact content={detail.content} />
              </section>
            </TabsContent>
            <TabsContent value="queries" className="mt-4">
              {activeTab === 'queries' ? (
                <ReportQueriesTab
                  reportNumber={detail.report_number}
                  token={token ?? ''}
                  workspaceSlug={workspaceSlug}
                />
              ) : null}
            </TabsContent>
            <TabsContent value="sources" className="mt-4">
              {activeTab === 'sources' ? (
                <ReportSourcesTab
                  reportNumber={detail.report_number}
                  token={token ?? ''}
                  workspaceSlug={workspaceSlug}
                />
              ) : null}
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
}

function ReportQueriesTab({
  reportNumber,
  token,
  workspaceSlug,
}: {
  reportNumber: string;
  token: string;
  workspaceSlug: string;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const [queries, setQueries] = useState<LegacyIssueReportQuery[] | null>(null);
  const [selectedQueryId, setSelectedQueryId] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setQueries(null);
    setSelectedQueryId('');
    setLoadFailed(false);
    listLegacyIssueReportQueries({
      reportId: reportNumber,
      signal: controller.signal,
      token,
      workspaceSlug,
    })
      .then((response) => {
        if (controller.signal.aborted) return;
        const sorted = [...response.items].sort(
          (left, right) => left.ordinal - right.ordinal,
        );
        setQueries(sorted);
        setSelectedQueryId(sorted[0]?.id ?? '');
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadFailed(true);
      });
    return () => controller.abort();
  }, [reportNumber, token, workspaceSlug]);

  if (loadFailed) {
    return (
      <ReportPanelState
        label={t('coreBusiness.reports.errors.queriesFailed')}
        role="alert"
      />
    );
  }
  if (queries === null) {
    return (
      <ReportPanelState
        label={t('common:feedback.loading')}
        role="status"
        spinning
      />
    );
  }
  if (queries.length === 0) {
    return (
      <ReportPanelState
        label={t('coreBusiness.reports.detail.queries.empty')}
      />
    );
  }

  const selectedQuery =
    queries.find((query) => query.id === selectedQueryId) ?? queries[0];

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-app-border bg-app-surface p-4">
        <label
          className="mb-2 block app-text-caption font-semibold text-app-ink/65"
          htmlFor="legacy-issue-report-query"
        >
          {t('coreBusiness.reports.detail.queries.select')}
        </label>
        <select
          id="legacy-issue-report-query"
          className="app-control h-9 w-full max-w-2xl px-3"
          value={selectedQuery.id}
          onChange={(event) => setSelectedQueryId(event.target.value)}
        >
          {queries.map((query) => (
            <option key={query.id} value={query.id}>
              {query.ordinal + 1}.{' '}
              {query.title ||
                query.family_id ||
                t('coreBusiness.reports.detail.queries.untitled')}
            </option>
          ))}
        </select>
      </section>
      <QueryMetadata query={selectedQuery} />
      <QueryRowsPanel
        query={selectedQuery}
        reportNumber={reportNumber}
        token={token}
        workspaceSlug={workspaceSlug}
      />
    </div>
  );
}

function QueryMetadata({ query }: { query: LegacyIssueReportQuery }) {
  const { t } = useTranslation('apps');
  return (
    <section className="overflow-hidden rounded-lg border border-app-border bg-app-surface">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-app-border bg-app-surface-sidebar px-4 py-3">
        <h2 className="app-text-subtitle font-semibold">
          {query.title ||
            query.family_id ||
            t('coreBusiness.reports.detail.queries.untitled')}
        </h2>
        <div className="flex flex-wrap gap-1.5 app-text-micro text-app-ink/60">
          <MetadataPill
            label={t('coreBusiness.reports.detail.queries.status')}
            value={queryStatusLabel(t, query.execution_status)}
          />
          {query.family_id ? (
            <MetadataPill
              label={t('coreBusiness.reports.detail.queries.family')}
              value={query.family_id}
            />
          ) : null}
          {query.duration_ms !== null ? (
            <MetadataPill
              label={t('coreBusiness.reports.detail.queries.duration')}
              value={t('coreBusiness.reports.detail.queries.durationValue', {
                value: query.duration_ms,
              })}
            />
          ) : null}
        </div>
      </header>
      <div className="grid gap-4 p-4 lg:grid-cols-2">
        <div className="min-w-0">
          <h3 className="mb-2 app-text-caption font-semibold text-app-ink/65">
            {t('coreBusiness.reports.detail.queries.sql')}
          </h3>
          <pre className="custom-scrollbar max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-app-border bg-app-bg p-3 app-text-caption text-app-ink/80">
            <code>
              {query.statement_text ||
                t('coreBusiness.reports.detail.queries.noSql')}
            </code>
          </pre>
        </div>
        <div className="min-w-0">
          <h3 className="mb-2 app-text-caption font-semibold text-app-ink/65">
            {t('coreBusiness.reports.detail.queries.params')}
          </h3>
          <pre className="custom-scrollbar max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-app-border bg-app-bg p-3 app-text-caption text-app-ink/80">
            <code>{formatJson(query.typed_params)}</code>
          </pre>
        </div>
      </div>
      {query.error_code ? (
        <p className="border-t border-app-border px-4 py-3 app-text-body-sm text-app-danger">
          {t('coreBusiness.reports.detail.queries.errorCode', {
            code: query.error_code,
          })}
        </p>
      ) : null}
    </section>
  );
}

function QueryRowsPanel({
  query,
  reportNumber,
  token,
  workspaceSlug,
}: {
  query: LegacyIssueReportQuery;
  reportNumber: string;
  token: string;
  workspaceSlug: string;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const [rows, setRows] = useState<LegacyIssueReportQueryRows | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const queryCompleted = query.execution_status === 'completed';

  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setLoadFailed(false);
    if (!queryCompleted) {
      return () => controller.abort();
    }
    loadAllQueryRows({
      queryId: query.id,
      reportNumber,
      signal: controller.signal,
      token,
      workspaceSlug,
    })
      .then((response) => {
        if (!controller.signal.aborted) setRows(response);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadFailed(true);
      });
    return () => controller.abort();
  }, [query.id, queryCompleted, reportNumber, token, workspaceSlug]);

  if (!queryCompleted) {
    return (
      <ReportPanelState
        label={t(
          query.execution_status === 'failed'
            ? 'coreBusiness.reports.detail.results.queryFailed'
            : 'coreBusiness.reports.detail.results.notExecuted',
        )}
        role={query.execution_status === 'failed' ? 'alert' : 'status'}
      />
    );
  }

  if (loadFailed) {
    return (
      <ReportPanelState
        label={t('coreBusiness.reports.errors.queryRowsFailed')}
        role="alert"
      />
    );
  }
  if (!rows) {
    return (
      <ReportPanelState
        label={t('common:feedback.loading')}
        role="status"
        spinning
      />
    );
  }

  return (
    <section className="overflow-hidden rounded-lg border border-app-border bg-app-surface">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-app-border bg-app-surface-sidebar px-4 py-3">
        <h2 className="flex items-center gap-2 app-text-subtitle font-semibold">
          <Database aria-hidden="true" size={16} />
          {t('coreBusiness.reports.detail.results.title')}
        </h2>
        <div className="flex flex-wrap items-center gap-2 app-text-micro text-app-ink/55">
          <span>
            {t('coreBusiness.reports.detail.results.capturedCount', {
              count: rows.captured_row_count,
            })}
          </span>
          <span aria-hidden="true">/</span>
          <span>
            {t('coreBusiness.reports.detail.results.originalCount', {
              count: rows.row_count ?? rows.rows.length,
            })}
          </span>
        </div>
      </header>
      {rows.truncated ? (
        <p
          className="border-b border-app-warning-border bg-app-warning-bg px-4 py-2 app-text-caption text-app-warning-text"
          role="status"
        >
          {t('coreBusiness.reports.detail.results.truncated')}
        </p>
      ) : null}
      <LegacyIssueReportDataGrid
        columns={rows.columns ?? []}
        emptyLabel={t('coreBusiness.reports.detail.results.empty')}
        layoutId={`legacy-issues.reports.${reportNumber}.queries.${query.id}`}
        loading={false}
        loadingLabel={t('common:feedback.loading')}
        rows={rows.rows}
      />
    </section>
  );
}

function ReportSourcesTab({
  reportNumber,
  token,
  workspaceSlug,
}: {
  reportNumber: string;
  token: string;
  workspaceSlug: string;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const [sources, setSources] = useState<LegacyIssueReportSource[] | null>(
    null,
  );
  const [selectedSourceId, setSelectedSourceId] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setSources(null);
    setSelectedSourceId('');
    setLoadFailed(false);
    listLegacyIssueReportSources({
      reportId: reportNumber,
      signal: controller.signal,
      token,
      workspaceSlug,
    })
      .then((response) => {
        if (controller.signal.aborted) return;
        const sorted = [...response.items].sort(
          (left, right) => left.ordinal - right.ordinal,
        );
        setSources(sorted);
        setSelectedSourceId(sorted[0]?.id ?? '');
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadFailed(true);
      });
    return () => controller.abort();
  }, [reportNumber, token, workspaceSlug]);

  if (loadFailed) {
    return (
      <ReportPanelState
        label={t('coreBusiness.reports.errors.sourcesFailed')}
        role="alert"
      />
    );
  }
  if (sources === null) {
    return (
      <ReportPanelState
        label={t('common:feedback.loading')}
        role="status"
        spinning
      />
    );
  }
  if (sources.length === 0) {
    return (
      <ReportPanelState
        label={t('coreBusiness.reports.detail.sources.empty')}
      />
    );
  }

  const source =
    sources.find((item) => item.id === selectedSourceId) ?? sources[0];

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-app-border bg-app-surface p-4">
        <label
          className="mb-2 block app-text-caption font-semibold text-app-ink/65"
          htmlFor="legacy-issue-report-source"
        >
          {t('coreBusiness.reports.detail.sources.select')}
        </label>
        <select
          id="legacy-issue-report-source"
          className="app-control h-9 w-full max-w-2xl px-3"
          value={source.id}
          onChange={(event) => setSelectedSourceId(event.target.value)}
        >
          {sources.map((item) => (
            <option key={item.id} value={item.id}>
              {item.ordinal + 1}.{' '}
              {item.title || t('coreBusiness.reports.detail.sources.untitled')}
            </option>
          ))}
        </select>
      </section>
      <section className="overflow-hidden rounded-lg border border-app-border bg-app-surface">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-app-border bg-app-surface-sidebar px-4 py-3">
          <h2 className="flex items-center gap-2 app-text-subtitle font-semibold">
            <FileSearch aria-hidden="true" size={16} />
            {source.title || t('coreBusiness.reports.detail.sources.untitled')}
          </h2>
          <div className="flex flex-wrap items-center gap-2 app-text-micro text-app-ink/55">
            <span>
              {t('coreBusiness.reports.detail.sources.rowCount', {
                count: source.row_count ?? source.grid_rows?.length ?? 0,
              })}
            </span>
          </div>
        </header>
        {source.truncated ? (
          <p
            className="border-b border-app-warning-border bg-app-warning-bg px-4 py-2 app-text-caption text-app-warning-text"
            role="status"
          >
            {t('coreBusiness.reports.detail.sources.truncated')}
          </p>
        ) : null}
        <LegacyIssueReportDataGrid
          columns={source.grid_columns ?? []}
          emptyLabel={t('coreBusiness.reports.detail.sources.noRows')}
          layoutId={`legacy-issues.reports.${reportNumber}.sources.${source.id}`}
          loading={false}
          loadingLabel={t('common:feedback.loading')}
          rows={source.grid_rows ?? []}
        />
      </section>
    </div>
  );
}

async function loadAllQueryRows({
  queryId,
  reportNumber,
  signal,
  token,
  workspaceSlug,
}: {
  queryId: string;
  reportNumber: string;
  signal: AbortSignal;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueReportQueryRows> {
  let offset = 0;
  let firstPage: LegacyIssueReportQueryRows | null = null;
  const combinedRows: Array<Record<string, unknown>> = [];

  while (!signal.aborted) {
    const page = await getLegacyIssueReportQueryRows({
      limit: QUERY_ROW_PAGE_SIZE,
      offset,
      queryId,
      reportId: reportNumber,
      signal,
      token,
      workspaceSlug,
    });
    firstPage ??= page;
    combinedRows.push(...page.rows);
    offset += page.rows.length;
    if (page.rows.length === 0 || offset >= page.total) break;
  }
  if (!firstPage) {
    throw new DOMException('Aborted', 'AbortError');
  }
  return {
    ...firstPage,
    limit: combinedRows.length,
    offset: 0,
    rows: combinedRows,
  };
}

function MetadataPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded border border-app-border bg-app-bg px-2 py-1">
      {label}: {value}
    </span>
  );
}

function ReportPageState({
  label,
  role,
  spinning = false,
}: {
  label: string;
  role: 'alert' | 'status';
  spinning?: boolean;
}) {
  return (
    <div className="flex h-full min-h-60 items-center justify-center bg-app-bg p-8">
      <div
        className="flex items-center gap-2 app-text-body-sm text-app-ink/60"
        role={role}
      >
        {spinning ? (
          <Loader2 aria-hidden="true" className="animate-spin" size={18} />
        ) : null}
        {label}
      </div>
    </div>
  );
}

function ReportPanelState({
  label,
  role,
  spinning = false,
}: {
  label: string;
  role?: 'alert' | 'status';
  spinning?: boolean;
}) {
  return (
    <div
      className="flex min-h-40 items-center justify-center gap-2 rounded-lg border border-dashed border-app-border bg-app-surface p-8 app-text-body-sm text-app-ink/55"
      role={role}
    >
      {spinning ? (
        <Loader2 aria-hidden="true" className="animate-spin" size={18} />
      ) : null}
      {label}
    </div>
  );
}

function reportDownloadFilename(report: LegacyIssueReportDetail): string {
  const title =
    report.title
      .trim()
      .replace(/[\\/:*?"<>|]+/g, '-')
      .replace(/\s+/g, '-') || 'report';
  return `${report.report_number}_${title}.md`;
}

function formatJson(value: unknown): string {
  if (value === null || value === undefined) return '{}';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function queryStatusLabel(t: (key: string) => string, status: string): string {
  switch (status) {
    case 'completed':
      return t('coreBusiness.reports.detail.queries.statuses.completed');
    case 'failed':
      return t('coreBusiness.reports.detail.queries.statuses.failed');
    case 'not_executed':
      return t('coreBusiness.reports.detail.queries.statuses.notExecuted');
    default:
      return t('coreBusiness.reports.detail.queries.statuses.unknown');
  }
}
