import { useMemo, useRef, useState } from 'react';
import type { DragEvent, MouseEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  FileSearch,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Table2,
  Trash2,
  Upload,
  X,
} from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import { DocumentArtifact } from '@/src/components/artifacts/DocumentArtifact';
import {
  fetchSpecCompareReport,
  type SpecCompareJob,
  type SpecCompareJobStatus,
  type SpecCompareReportFormat,
  type SpecCompareResult,
  type SpecCompareRow,
  type SpecCompareRowStatus,
} from '../api/spec-compare-api';
import {
  ACTIVE_SPEC_COMPARE_STATUSES,
  buildSpecCompareSpecItemsProjection,
  buildSpecCompareSummaryCards,
  formatSpecCompareFileSize,
} from './spec-compare-view-model';
import { useSpecCompareJobWorkflow } from './useSpecCompareJobWorkflow';

const ACCEPTED_FILE_TYPES = '.pptx,.docx,.pdf';

async function downloadSpecCompareReport(
  job: SpecCompareJob | null,
  format: SpecCompareReportFormat,
  token: string | null | undefined,
  workspaceSlug: string | null,
  onError: (message: string) => void,
): Promise<void> {
  if (!job || !token) {
    return;
  }
  try {
    const blob = await fetchSpecCompareReport({
      token,
      workspaceSlug,
      jobId: job.id,
      format,
    });
    const rawName =
      (job.title || 'spec-compare-report')
        .replace(/[\\/:*?"<>|]+/g, '_')
        .trim() || 'spec-compare-report';
    downloadBlobAsFile(blob, `${rawName}.${format}`);
  } catch (error) {
    onError(error instanceof Error ? error.message : 'download failed');
  }
}

export function SpecCompareView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);
  const workspaceName =
    workspaceBootstrap.data?.workspace.name ?? workspaceSlug ?? '';
  const workflow = useSpecCompareJobWorkflow({
    messages: {
      createFailed: t('ai.specCompare.errors.create'),
      loadJobsFailed: t('ai.specCompare.errors.loadJobs'),
      loadResultFailed: t('ai.specCompare.errors.loadResult'),
      pollFailed: t('ai.specCompare.errors.poll'),
      deleteFailed: t('ai.specCompare.errors.delete'),
    },
    token,
    workspaceSlug,
  });
  const { actions, canSubmit, state } = workflow;
  const {
    baseFile,
    error,
    jobs,
    loadingJobs,
    loadingResult,
    result,
    resultTab,
    selectedJob,
    submitting,
    targetFile,
  } = state;

  const summaryCards = useMemo(
    () => buildSpecCompareSummaryCards(result),
    [result],
  );

  return (
    <main className="flex min-h-screen flex-col bg-app-bg text-app-ink">
      <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-app-border bg-app-surface px-6">
        <div className="flex min-w-0 items-baseline gap-2.5">
          <h1 className="truncate app-text-title-md font-semibold tracking-normal">
            {t('ai.specCompare.title')}
          </h1>
          {workspaceName ? (
            <span className="truncate app-text-body font-medium text-app-ink/60">
              {workspaceName}
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => void actions.refreshJobs()}
          className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md border border-app-border px-3 app-text-body font-medium text-app-ink/80 hover:bg-app-surface-hover disabled:opacity-60"
          disabled={loadingJobs}
        >
          {loadingJobs ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          {t('ai.specCompare.refresh')}
        </button>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-0 lg:grid-cols-[360px_minmax(0,1fr)]">
        <SpecCompareSidebar
          baseFile={baseFile}
          canSubmit={canSubmit}
          jobs={jobs}
          loadingJobs={loadingJobs}
          selectedJob={selectedJob}
          submitting={submitting}
          targetFile={targetFile}
          onBaseFileChange={actions.setBaseFile}
          onJobSelect={actions.selectJob}
          onJobDelete={(jobId) => void actions.deleteJob(jobId)}
          onReset={actions.reset}
          onSubmit={() => void actions.submit()}
          onTargetFileChange={actions.setTargetFile}
        />

        <section className="min-w-0 p-5 md:p-6">
          {error ? (
            <div className="mb-4 flex items-start gap-3 rounded-md border border-app-danger-border bg-app-danger-bg p-4 app-text-body text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}

          {!selectedJob ? (
            <EmptyResult />
          ) : (
            <div className="space-y-5">
              <JobHeader job={selectedJob} />
              {ACTIVE_SPEC_COMPARE_STATUSES.includes(selectedJob.status) ? (
                <ProgressPanel job={selectedJob} />
              ) : null}
              {selectedJob.status === 'failed' ? (
                <div className="rounded-md border border-app-danger-border bg-app-danger-bg p-4 app-text-body text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
                  {selectedJob.failure_reason ||
                    t('ai.specCompare.failedFallback')}
                </div>
              ) : null}
              {selectedJob.status === 'succeeded' ? (
                <div className="space-y-5">
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
                    {summaryCards.map((card) => (
                      <div
                        key={card.labelKey}
                        className="rounded-md border border-app-border bg-app-surface p-4"
                      >
                        <p className="app-text-caption font-medium text-app-ink/60">
                          {t(card.labelKey)}
                        </p>
                        <p className="mt-2 text-2xl font-semibold">
                          {card.value}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-md border border-app-border bg-app-surface">
                    <div className="flex flex-wrap gap-2 border-b border-app-border p-3">
                      <TabButton
                        active={resultTab === 'report'}
                        onClick={() => actions.setResultTab('report')}
                        icon={<FileText className="size-4" />}
                      >
                        {t('ai.specCompare.tabs.report')}
                      </TabButton>
                      <TabButton
                        active={resultTab === 'table'}
                        onClick={() => actions.setResultTab('table')}
                        icon={<Table2 className="size-4" />}
                      >
                        {t('ai.specCompare.tabs.table')}
                      </TabButton>
                      <TabButton
                        active={resultTab === 'specs'}
                        onClick={() => actions.setResultTab('specs')}
                        icon={<Database className="size-4" />}
                      >
                        {t('ai.specCompare.tabs.specs')}
                      </TabButton>
                      <TabButton
                        active={resultTab === 'evidence'}
                        onClick={() => actions.setResultTab('evidence')}
                        icon={<FileSearch className="size-4" />}
                      >
                        {t('ai.specCompare.tabs.evidence')}
                      </TabButton>
                      <div className="ml-auto flex items-center gap-2">
                        <span className="app-text-caption text-app-ink/50">
                          {t('ai.specCompare.download')}
                        </span>
                        {(['docx', 'pdf'] as SpecCompareReportFormat[]).map(
                          (format) => (
                            <button
                              key={format}
                              type="button"
                              onClick={() =>
                                void downloadSpecCompareReport(
                                  selectedJob,
                                  format,
                                  token,
                                  workspaceSlug,
                                  (message) => window.alert(message),
                                )
                              }
                              disabled={!result || !token}
                              className="inline-flex h-9 items-center gap-2 rounded-md border border-app-border px-3 app-text-body font-medium text-app-ink/80 hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              <Download className="size-4" />
                              {t(
                                format === 'docx'
                                  ? 'ai.specCompare.downloadWord'
                                  : 'ai.specCompare.downloadPdf',
                              )}
                            </button>
                          ),
                        )}
                      </div>
                    </div>
                    <div className="max-h-[calc(100vh-280px)] overflow-auto p-4">
                      {loadingResult || !result ? (
                        <div className="flex min-h-40 items-center justify-center gap-2 app-text-body text-app-ink/60">
                          <Loader2 className="size-4 animate-spin" />
                          {t('ai.specCompare.loadingResult')}
                        </div>
                      ) : null}
                      {result && resultTab === 'report' ? (
                        <DocumentArtifact content={result.report_markdown} />
                      ) : null}
                      {result && resultTab === 'table' ? (
                        <ComparisonTable rows={result.comparison_rows} />
                      ) : null}
                      {result && resultTab === 'specs' ? (
                        <SpecItemsGrid result={result} />
                      ) : null}
                      {result && resultTab === 'evidence' ? (
                        <EvidenceList evidenceBlocks={result.evidence_blocks} />
                      ) : null}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function SpecCompareSidebar({
  baseFile,
  canSubmit,
  jobs,
  loadingJobs,
  selectedJob,
  submitting,
  targetFile,
  onBaseFileChange,
  onJobSelect,
  onJobDelete,
  onReset,
  onSubmit,
  onTargetFileChange,
}: {
  baseFile: File | null;
  canSubmit: boolean;
  jobs: SpecCompareJob[];
  loadingJobs: boolean;
  selectedJob: SpecCompareJob | null;
  submitting: boolean;
  targetFile: File | null;
  onBaseFileChange: (file: File | null) => void;
  onJobSelect: (job: SpecCompareJob) => void;
  onJobDelete: (jobId: string) => void;
  onReset: () => void;
  onSubmit: () => void;
  onTargetFileChange: (file: File | null) => void;
}) {
  const { t } = useTranslation('apps');

  return (
    <aside className="border-b border-app-border bg-app-surface p-5 lg:border-b-0 lg:border-r">
      <section className="space-y-4">
        <FilePicker
          id="base-spec-file"
          label={t('ai.specCompare.baseFile')}
          file={baseFile}
          onChange={onBaseFileChange}
        />
        <FilePicker
          id="target-spec-file"
          label={t('ai.specCompare.targetFile')}
          file={targetFile}
          onChange={onTargetFileChange}
        />
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit}
            className="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-md bg-app-accent px-4 app-text-body font-semibold text-app-accent-fg hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:bg-app-surface-hover disabled:text-app-ink/40"
          >
            {submitting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Play className="size-4" />
            )}
            {t(
              submitting ? 'ai.specCompare.submitting' : 'ai.specCompare.start',
            )}
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={submitting || (!baseFile && !targetFile)}
            title={t('ai.specCompare.reset')}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-app-border px-3 app-text-body font-medium text-app-ink/80 hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw className="size-4" />
            {t('ai.specCompare.reset')}
          </button>
        </div>
        <p className="app-text-caption leading-5 text-app-ink/60">
          {t('ai.specCompare.supportedHint')}
        </p>
      </section>

      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="app-text-body font-semibold">
            {t('ai.specCompare.recentJobs')}
          </h2>
          {loadingJobs ? (
            <Loader2 className="size-4 animate-spin text-app-ink/50" />
          ) : null}
        </div>
        <div className="space-y-2">
          {jobs.length === 0 ? (
            <div className="rounded-md border border-dashed border-app-border p-4 app-text-body text-app-ink/60">
              {t('ai.specCompare.emptyJobs')}
            </div>
          ) : (
            jobs.map((job) => (
              <div
                key={job.id}
                className={cn(
                  'group relative rounded-md border transition',
                  selectedJob?.id === job.id
                    ? 'border-app-accent bg-app-surface-sidebar'
                    : 'border-app-border hover:bg-app-bg',
                )}
              >
                <button
                  type="button"
                  onClick={() => onJobSelect(job)}
                  className="block w-full rounded-md p-3 pb-7 text-left"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate app-text-body font-medium">
                        {job.title || t('ai.specCompare.untitledJob')}
                      </p>
                      <p className="mt-1 truncate app-text-caption text-app-ink/60">
                        {job.base_file.name} → {job.target_file.name}
                      </p>
                    </div>
                    <StatusPill status={job.status} />
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(t('ai.specCompare.deleteJobConfirm'))) {
                      onJobDelete(job.id);
                    }
                  }}
                  aria-label={t('ai.specCompare.deleteJob')}
                  title={t('ai.specCompare.deleteJob')}
                  className="absolute bottom-1.5 right-1.5 inline-flex size-6 items-center justify-center rounded-md text-app-ink/40 opacity-0 transition hover:bg-app-danger-bg hover:text-app-danger-text focus-visible:opacity-100 group-hover:opacity-100 dark:hover:bg-app-danger-bg dark:hover:text-app-danger-text"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </aside>
  );
}

function FilePicker({
  id,
  label,
  file,
  onChange,
}: {
  id: string;
  label: string;
  file: File | null;
  onChange: (file: File | null) => void;
}) {
  const { t } = useTranslation('apps');
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragActive(false);
    onChange(event.dataTransfer.files?.[0] ?? null);
  };

  const handleRemove = (event: MouseEvent) => {
    // Prevent the enclosing <label> from re-opening the file dialog, and reset
    // the native input so re-selecting the same file still fires onChange.
    event.preventDefault();
    event.stopPropagation();
    if (inputRef.current) {
      inputRef.current.value = '';
    }
    onChange(null);
  };

  return (
    <label
      htmlFor={id}
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      className={cn(
        'block rounded-md border border-dashed border-app-border bg-app-bg p-4 transition hover:border-app-ink/40',
        dragActive && 'border-app-accent bg-app-surface-sidebar',
      )}
    >
      <span className="flex items-center justify-between gap-2 app-text-body font-semibold">
        <span className="flex items-center gap-2">
          <Upload className="size-4" />
          {label}
        </span>
        {file ? (
          <button
            type="button"
            onClick={handleRemove}
            aria-label={t('ai.specCompare.removeFile')}
            title={t('ai.specCompare.removeFile')}
            className="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-app-ink/50 hover:bg-app-surface-hover hover:text-app-ink"
          >
            <X className="size-4" />
          </button>
        ) : null}
      </span>
      <span className="mt-3 block min-h-12 rounded-md bg-app-surface px-3 py-2 app-text-body text-app-ink/70">
        {file ? (
          <>
            <span className="block truncate font-medium text-app-ink">
              {file.name}
            </span>
            <span className="app-text-caption text-app-ink/60">
              {formatSpecCompareFileSize(file.size)}
            </span>
          </>
        ) : (
          <span className="text-app-ink/60">
            {t('ai.specCompare.chooseFile')}
          </span>
        )}
      </span>
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={ACCEPTED_FILE_TYPES}
        className="sr-only"
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
      />
    </label>
  );
}

function JobHeader({ job }: { job: SpecCompareJob }) {
  const { t } = useTranslation('apps');
  return (
    <div className="rounded-md border border-app-border bg-app-surface p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <FileSearch className="size-5 text-app-ink/60" />
            <h2 className="truncate app-text-title-md font-semibold">
              {job.title || t('ai.specCompare.untitledJob')}
            </h2>
          </div>
          <p className="mt-2 app-text-body text-app-ink/60">
            {job.base_file.name} → {job.target_file.name}
          </p>
        </div>
        <StatusPill status={job.status} />
      </div>
    </div>
  );
}

function ProgressPanel({ job }: { job: SpecCompareJob }) {
  const { t } = useTranslation('apps');
  const messageKey = `ai.specCompare.stage.${job.status_message}`;
  return (
    <div className="rounded-md border border-app-border bg-app-surface p-5">
      <div className="mb-3 flex items-center justify-between app-text-body">
        <span className="inline-flex items-center gap-2 font-medium">
          <Loader2 className="size-4 animate-spin" />
          {t(messageKey, { defaultValue: t('ai.specCompare.stage.running') })}
        </span>
        <span>{job.progress}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-app-surface-hover">
        <div
          className="h-full rounded-full bg-app-accent transition-all"
          style={{ width: `${Math.max(4, Math.min(100, job.progress))}%` }}
        />
      </div>
    </div>
  );
}

function EmptyResult() {
  const { t } = useTranslation('apps');
  return (
    <div className="flex min-h-[360px] items-center justify-center rounded-md border border-dashed border-app-border bg-app-surface p-8 text-center">
      <div>
        <FileSearch className="mx-auto size-10 text-app-ink/50" />
        <h2 className="mt-4 app-text-title-md font-semibold">
          {t('ai.specCompare.emptyTitle')}
        </h2>
        <p className="mt-2 max-w-md app-text-body text-app-ink/60">
          {t('ai.specCompare.emptyDescription')}
        </p>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: SpecCompareJobStatus }) {
  const { t } = useTranslation('apps');
  const active = status === 'queued' || status === 'running';
  const failed = status === 'failed' || status === 'cancelled';
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 app-text-caption font-medium',
        active &&
          'bg-app-info-bg text-app-info-text dark:bg-app-info-bg dark:text-app-info-text',
        status === 'succeeded' &&
          'bg-app-success-bg text-app-success-text dark:bg-emerald-950/50 dark:text-app-success-text',
        failed &&
          'bg-app-danger-bg text-app-danger-text dark:bg-red-950/50 dark:text-app-danger-text',
      )}
    >
      {active ? <Clock3 className="size-3" /> : null}
      {status === 'succeeded' ? <CheckCircle2 className="size-3" /> : null}
      {failed ? <AlertCircle className="size-3" /> : null}
      {t(`ai.specCompare.status.${status}`)}
    </span>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex h-9 items-center gap-2 rounded-md px-3 app-text-body font-medium',
        active
          ? 'bg-app-accent text-app-accent-fg'
          : 'text-app-ink/70 hover:bg-app-surface-hover',
      )}
    >
      {icon}
      {children}
    </button>
  );
}

function ComparisonTable({ rows }: { rows: SpecCompareRow[] }) {
  const { t } = useTranslation('apps');
  if (rows.length === 0) {
    return (
      <div className="py-10 text-center app-text-body text-app-ink/60">
        {t('ai.specCompare.emptyRows')}
      </div>
    );
  }
  return (
    <div className="overflow-auto">
      <table className="min-w-[900px] text-left app-text-body">
        <thead className="border-b border-app-border app-text-caption uppercase text-app-ink/60">
          <tr>
            <th className="px-3 py-2 font-semibold">
              {t('ai.specCompare.table.status')}
            </th>
            <th className="px-3 py-2 font-semibold">
              {t('ai.specCompare.table.spec')}
            </th>
            <th className="px-3 py-2 font-semibold">
              {t('ai.specCompare.table.base')}
            </th>
            <th className="px-3 py-2 font-semibold">
              {t('ai.specCompare.table.target')}
            </th>
            <th className="px-3 py-2 font-semibold">
              {t('ai.specCompare.table.summary')}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-app-border">
          {rows.map((row, index) => (
            <tr key={`${row.spec_name}-${index}`}>
              <td className="p-3 align-top">
                <RowStatusBadge status={row.status} />
              </td>
              <td className="max-w-[220px] p-3 align-top font-medium">
                {row.spec_name}
              </td>
              <td className="max-w-[240px] p-3 align-top text-app-ink/70">
                {row.base_value}
              </td>
              <td className="max-w-[240px] p-3 align-top text-app-ink/70">
                {row.target_value}
              </td>
              <td className="max-w-[280px] p-3 align-top text-app-ink/70">
                {row.summary}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RowStatusBadge({ status }: { status: SpecCompareRowStatus }) {
  const { t } = useTranslation('apps');
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-1 app-text-caption font-semibold ring-1 ring-inset',
        status === 'same' &&
          'bg-emerald-100 text-emerald-800 ring-emerald-300 dark:bg-emerald-950/50 dark:text-app-success-text dark:ring-emerald-800',
        status === 'different' &&
          'bg-red-100 text-app-danger-text ring-red-300 dark:bg-red-950/50 dark:text-app-danger-text dark:ring-red-800',
        status === 'base_only' &&
          'bg-blue-100 text-blue-800 ring-blue-300 dark:bg-app-info-bg dark:text-app-info-text dark:ring-blue-800',
        status === 'target_only' &&
          'bg-violet-100 text-violet-800 ring-violet-300 dark:bg-violet-950/50 dark:text-violet-200 dark:ring-violet-800',
        status === 'unknown' &&
          'bg-amber-100 text-app-warning-text ring-amber-300 dark:bg-app-warning-bg dark:text-app-warning-text dark:ring-amber-800',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'size-1.5 rounded-full',
          status === 'same' && 'bg-app-success',
          status === 'different' && 'bg-app-danger',
          status === 'base_only' && 'bg-app-info',
          status === 'target_only' && 'bg-violet-500',
          status === 'unknown' && 'bg-app-warning',
        )}
      />
      {t(`ai.specCompare.rowStatus.${status}`)}
    </span>
  );
}

function SpecItemsGrid({ result }: { result: SpecCompareResult }) {
  const { t } = useTranslation('apps');
  const specItems = buildSpecCompareSpecItemsProjection(result);

  if (specItems.rows.length === 0) {
    return (
      <div className="py-10 text-center app-text-body text-app-ink/60">
        {t('ai.specCompare.emptySpecItems')}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 app-text-body">
        <span className="rounded-full bg-app-surface-sidebar px-3 py-1 font-medium text-app-ink/80">
          {t('ai.specCompare.specItems.baseCount', {
            count: specItems.baseCount,
          })}
        </span>
        <span className="rounded-full bg-app-surface-sidebar px-3 py-1 font-medium text-app-ink/80">
          {t('ai.specCompare.specItems.targetCount', {
            count: specItems.targetCount,
          })}
        </span>
      </div>

      <div className="overflow-auto rounded-md border border-app-border">
        <table className="min-w-[1120px] text-left app-text-body">
          <thead className="border-b border-app-border bg-app-bg app-text-caption uppercase text-app-ink/60">
            <tr>
              <th className="px-3 py-2 font-semibold">
                {t('ai.specCompare.specItems.document')}
              </th>
              <th className="px-3 py-2 font-semibold">
                {t('ai.specCompare.specItems.category')}
              </th>
              <th className="px-3 py-2 font-semibold">
                {t('ai.specCompare.specItems.item')}
              </th>
              <th className="px-3 py-2 font-semibold">
                {t('ai.specCompare.specItems.value')}
              </th>
              <th className="px-3 py-2 font-semibold">
                {t('ai.specCompare.specItems.condition')}
              </th>
              <th className="px-3 py-2 font-semibold">
                {t('ai.specCompare.specItems.evidence')}
              </th>
              <th className="px-3 py-2 font-semibold">
                {t('ai.specCompare.specItems.confidence')}
              </th>
              <th className="px-3 py-2 font-semibold">
                {t('ai.specCompare.specItems.method')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-app-border">
            {specItems.rows.map((row) => (
              <tr key={row.key}>
                <td className="p-3 align-top">
                  <span
                    className={cn(
                      'inline-flex rounded-full px-2 py-1 app-text-caption font-medium',
                      row.document === 'base'
                        ? 'bg-app-surface-sidebar text-app-ink/80'
                        : 'bg-app-info-bg text-app-info-text dark:bg-app-info-bg dark:text-app-info-text',
                    )}
                  >
                    {t(
                      row.document === 'base'
                        ? 'ai.specCompare.specItems.baseDocument'
                        : 'ai.specCompare.specItems.targetDocument',
                    )}
                  </span>
                </td>
                <td className="max-w-[160px] p-3 align-top text-app-ink/70">
                  {row.category}
                </td>
                <td className="max-w-[220px] p-3 align-top">
                  <div className="font-medium">{row.itemName}</div>
                  {row.itemId ? (
                    <div className="mt-1 font-mono app-text-caption text-app-ink/50">
                      {row.itemId}
                    </div>
                  ) : null}
                </td>
                <td className="max-w-[220px] p-3 align-top text-app-ink/80">
                  {row.value}
                </td>
                <td className="max-w-[180px] p-3 align-top text-app-ink/70">
                  {row.condition}
                </td>
                <td className="max-w-[360px] p-3 align-top text-app-ink/70">
                  <div className="font-mono app-text-caption text-app-ink/60">
                    {row.evidenceId}
                  </div>
                  <div className="mt-1 app-text-caption">
                    {row.locatorLabel}
                  </div>
                  <div className="mt-1 app-text-caption text-app-ink/60">
                    {row.sectionPath}
                  </div>
                  {row.sourceText ? (
                    <p className="mt-2 max-h-20 overflow-hidden whitespace-pre-wrap app-text-caption leading-5">
                      {row.sourceText}
                    </p>
                  ) : null}
                </td>
                <td className="p-3 align-top text-app-ink/70">
                  {row.confidence}
                </td>
                <td className="max-w-[140px] p-3 align-top text-app-ink/70">
                  {row.extractionMethod}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EvidenceList({
  evidenceBlocks,
}: {
  evidenceBlocks: Array<Record<string, unknown>>;
}) {
  const { t } = useTranslation('apps');
  if (evidenceBlocks.length === 0) {
    return (
      <div className="py-10 text-center app-text-body text-app-ink/60">
        {t('ai.specCompare.emptyEvidence')}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {evidenceBlocks.map((block, index) => (
        <div
          key={String(block.block_id ?? index)}
          className="rounded-md border border-app-border p-3"
        >
          <div className="mb-2 flex flex-wrap items-center gap-2 app-text-caption text-app-ink/60">
            <span className="font-mono">{String(block.block_id ?? '')}</span>
            <span>{String(block.locator_label ?? '')}</span>
            <span>{String(block.section_path ?? '')}</span>
          </div>
          <p className="whitespace-pre-wrap app-text-body text-app-ink/80">
            {String(block.text ?? '')}
          </p>
        </div>
      ))}
    </div>
  );
}
