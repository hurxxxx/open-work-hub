import { Tabs, TabsContent, TabsList, TabsTrigger } from '@open-alm/ui';
import { FileText, Loader2, RefreshCw, Share2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  listLegacyIssueReports,
  type LegacyIssueReportListView,
  type LegacyIssueReportSummary,
} from '../api/legacy-issue-assistant-report-api';
import { LEGACY_ISSUE_REPORTS_PATH_SUFFIX } from '../legacy-issue-datasets';
import {
  LegacyIssuePageHeader,
  LegacyIssueToolbarButton,
} from './LegacyIssuePageParts';

const REPORTS_PER_PAGE = 30;

export function CoreBusinessLegacyIssueReportManagementView() {
  const { workspaceSlug = '' } = useParams<{ workspaceSlug: string }>();
  const { token, user } = useAuth();
  const { t } = useTranslation(['apps', 'common']);
  const [view, setView] = useState<LegacyIssueReportListView>('mine');
  const ownerKey =
    token && user?.id && workspaceSlug
      ? `${user.id}:${workspaceSlug}:${view}`
      : null;
  const [reports, setReports] = useState<LegacyIssueReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [pagination, setPagination] = useState<{
    offset: number;
    ownerKey: string | null;
  }>({ offset: 0, ownerKey: null });
  const [total, setTotal] = useState(0);
  const [loadedOwnerKey, setLoadedOwnerKey] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const offset = pagination.ownerKey === ownerKey ? pagination.offset : 0;

  const loadReports = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (!token || !workspaceSlug || !ownerKey) {
      setReports([]);
      setTotal(0);
      setLoadedOwnerKey(null);
      setLoadFailed(false);
      setLoading(false);
      return;
    }
    setReports([]);
    setTotal(0);
    setLoadedOwnerKey(null);
    setLoading(true);
    setLoadFailed(false);
    try {
      const response = await listLegacyIssueReports({
        limit: REPORTS_PER_PAGE,
        offset,
        token,
        view,
        workspaceSlug,
      });
      if (requestIdRef.current === requestId) {
        setReports(response.items);
        setTotal(response.total);
        setLoadedOwnerKey(ownerKey);
      }
    } catch {
      if (requestIdRef.current === requestId) {
        setReports([]);
        setTotal(0);
        setLoadedOwnerKey(ownerKey);
        setLoadFailed(true);
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [offset, ownerKey, token, view, workspaceSlug]);

  useEffect(() => {
    void loadReports();
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadReports]);

  const reportsBelongToCurrentOwner = loadedOwnerKey === ownerKey;
  const visibleReports = reportsBelongToCurrentOwner ? reports : [];
  const visibleTotal = reportsBelongToCurrentOwner ? total : 0;
  const isLoadingCurrentOwner =
    ownerKey !== null && (loading || !reportsBelongToCurrentOwner);

  return (
    <div className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
      <LegacyIssuePageHeader
        actions={
          <LegacyIssueToolbarButton
            disabled={isLoadingCurrentOwner}
            icon={
              <RefreshCw
                aria-hidden="true"
                className={isLoadingCurrentOwner ? 'animate-spin' : undefined}
                size={16}
              />
            }
            label={t('coreBusiness.reports.actions.refresh')}
            onClick={() => void loadReports()}
          />
        }
        eyebrow={t('coreBusiness.reports.eyebrow')}
        title={t('coreBusiness.reports.title')}
      />
      <main className="min-h-0 flex-1 overflow-y-auto p-4">
        <section
          className="mx-auto max-w-5xl overflow-hidden rounded-lg border border-app-border bg-app-surface"
          aria-labelledby="legacy-issue-report-list-title"
        >
          <Tabs
            value={view}
            onValueChange={(value) => {
              const nextView =
                value === 'shared' ? ('shared' as const) : ('mine' as const);
              setPagination({ offset: 0, ownerKey: null });
              setView(nextView);
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-app-border px-4 py-3">
              <h2
                id="legacy-issue-report-list-title"
                className="app-text-subtitle font-semibold"
              >
                {t('coreBusiness.reports.listTitle')}
              </h2>
              <TabsList
                aria-label={t('coreBusiness.reports.views.label')}
                className="h-8"
              >
                <TabsTrigger value="mine" className="h-7 px-3">
                  {t('coreBusiness.reports.views.mine')}
                </TabsTrigger>
                <TabsTrigger value="shared" className="h-7 px-3">
                  {t('coreBusiness.reports.views.shared')}
                </TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value={view} className="mt-0">
              {isLoadingCurrentOwner ? (
                <div
                  className="flex min-h-40 items-center justify-center gap-2 px-4 py-8 app-text-body-sm text-app-ink/60"
                  role="status"
                >
                  <Loader2
                    aria-hidden="true"
                    className="animate-spin"
                    size={18}
                  />
                  {t('common:feedback.loading')}
                </div>
              ) : loadFailed ? (
                <p
                  className="flex min-h-40 items-center justify-center px-4 py-8 app-text-body-sm text-app-danger"
                  role="alert"
                >
                  {t('coreBusiness.reports.errors.listFailed')}
                </p>
              ) : visibleReports.length === 0 ? (
                <p className="flex min-h-40 items-center justify-center px-4 py-8 app-text-body-sm text-app-ink/55">
                  {t(
                    view === 'shared'
                      ? 'coreBusiness.reports.emptyShared'
                      : 'coreBusiness.reports.emptyMine',
                  )}
                </p>
              ) : (
                <ul className="divide-y divide-app-border">
                  {visibleReports.map((report) => (
                    <li key={report.report_id}>
                      <Link
                        className="flex gap-3 px-4 py-4 transition-colors hover:bg-app-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-app-accent"
                        to={buildReportLink(
                          workspaceSlug,
                          report.report_number,
                        )}
                      >
                        <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-md bg-app-accent/10 text-app-accent">
                          <FileText aria-hidden="true" size={18} />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="app-text-micro font-semibold text-app-accent">
                              {report.report_number}
                            </span>
                            {report.visibility === 'workspace' ? (
                              <span className="inline-flex items-center gap-1 rounded border border-app-border bg-app-bg px-1.5 py-0.5 app-text-micro text-app-ink/55">
                                <Share2 aria-hidden="true" size={11} />
                                {t('coreBusiness.reports.visibility.workspace')}
                              </span>
                            ) : (
                              <span className="rounded border border-app-border bg-app-bg px-1.5 py-0.5 app-text-micro text-app-ink/55">
                                {t('coreBusiness.reports.visibility.private')}
                              </span>
                            )}
                          </span>
                          <span className="mt-1 block app-text-body font-semibold">
                            {report.title}
                          </span>
                          {report.question ? (
                            <span className="mt-1 block app-text-caption text-app-ink/65">
                              {report.question}
                            </span>
                          ) : null}
                          {report.preview ? (
                            <span className="mt-2 line-clamp-2 block app-text-body-sm text-app-ink/80">
                              {report.preview}
                            </span>
                          ) : null}
                          <span className="mt-2 flex flex-wrap items-center gap-1.5 app-text-micro text-app-ink/45">
                            {view === 'shared' && report.owner_name ? (
                              <>
                                <span>{report.owner_name}</span>
                                <span aria-hidden="true">·</span>
                              </>
                            ) : null}
                            {report.completed_at ? (
                              <>
                                <UserDateTime
                                  value={report.completed_at}
                                  options={{ hourCycle: 'h23' }}
                                />
                                <span aria-hidden="true">·</span>
                              </>
                            ) : null}
                            <span>
                              {t('coreBusiness.reports.queryCount', {
                                count: report.query_count,
                              })}
                            </span>
                            <span aria-hidden="true">·</span>
                            <span>
                              {t('coreBusiness.reports.sourceCount', {
                                count: report.source_count,
                              })}
                            </span>
                          </span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              {!isLoadingCurrentOwner &&
              !loadFailed &&
              visibleTotal > REPORTS_PER_PAGE ? (
                <ReportPagination
                  label={t('coreBusiness.reports.listTitle')}
                  offset={offset}
                  onPageChange={(page) =>
                    setPagination({
                      offset: (page - 1) * REPORTS_PER_PAGE,
                      ownerKey,
                    })
                  }
                  total={visibleTotal}
                />
              ) : null}
            </TabsContent>
          </Tabs>
        </section>
      </main>
    </div>
  );
}

// Kept for source compatibility with the former conversation-history route.
export const CoreBusinessLegacyIssueAssistantHistoryView =
  CoreBusinessLegacyIssueReportManagementView;

function buildReportLink(workspaceSlug: string, reportNumber: string): string {
  return `${buildWorkspaceAppPath(
    workspaceSlug,
    'legacy-issues',
    LEGACY_ISSUE_REPORTS_PATH_SUFFIX,
  )}/${encodeURIComponent(reportNumber)}`;
}

function ReportPagination({
  label,
  offset,
  onPageChange,
  total,
}: {
  label: string;
  offset: number;
  onPageChange: (page: number) => void;
  total: number;
}) {
  const pageCount = Math.ceil(total / REPORTS_PER_PAGE);
  const currentPage = Math.floor(offset / REPORTS_PER_PAGE) + 1;
  const firstItem = offset + 1;
  const lastItem = Math.min(offset + REPORTS_PER_PAGE, total);

  return (
    <nav
      aria-label={label}
      className="flex items-center justify-end gap-3 border-t border-app-border px-4 py-3"
    >
      <span className="app-text-micro text-app-ink/50">
        {firstItem}-{lastItem} / {total}
      </span>
      <label className="sr-only" htmlFor="legacy-issue-report-page">
        {label}
      </label>
      <select
        id="legacy-issue-report-page"
        className="app-control h-8 min-w-20 px-2"
        value={currentPage}
        onChange={(event) => onPageChange(Number(event.target.value))}
      >
        {Array.from({ length: pageCount }, (_, index) => {
          const page = index + 1;
          return (
            <option key={page} value={page}>
              {page} / {pageCount}
            </option>
          );
        })}
      </select>
    </nav>
  );
}
