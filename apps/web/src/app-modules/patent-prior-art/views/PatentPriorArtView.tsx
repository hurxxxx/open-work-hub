import { useTranslation } from 'react-i18next';
import {
  Check,
  FileSearch,
  Loader2,
  Paperclip,
  Play,
  Search,
  X,
} from 'lucide-react';

import { Button, InlineNotice } from '@open-alm/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';

import { PlanChipEditor } from '../components/PlanChipEditor';
import { PatentPriorArtHistoryPanel } from '../components/PatentPriorArtHistoryPanel';
import { PatentPriorArtJobStatusNotice } from '../components/PatentPriorArtJobStatusNotice';
import { PatentPriorArtResultPanel } from '../components/PatentPriorArtResultPanel';
import { usePatentPriorArtController } from '../controller/usePatentPriorArtController';
import {
  EDITABLE_PLAN_FIELDS,
  patentPriorArtJobDisplayStatus,
} from '../model/patent-prior-art-view-model';
import type {
  PatentPriorArtArtifact,
  PatentPriorArtReportFormat,
} from '../api/patent-prior-art-api';

const REPORT_DOWNLOAD_FILENAMES = {
  docx: 'patent-prior-art-report.docx',
  html: 'patent-prior-art-report.html',
  pdf: 'patent-prior-art-report.pdf',
  summary_docx: 'patent-prior-art-report-summary.docx',
  summary_pdf: 'patent-prior-art-report-summary.pdf',
} satisfies Record<PatentPriorArtReportFormat, string>;

export function PatentPriorArtView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);
  const controller = usePatentPriorArtController({ token, workspaceSlug });
  const config = controller.config;
  const preview = controller.preview;

  const optionLabel = (labelKey: string, fallbackLabel: string) =>
    t(labelKey, { defaultValue: fallbackLabel });

  const handleDownload = async (artifact: PatentPriorArtArtifact) => {
    const blob = await controller.downloadArtifact(artifact);
    if (blob) downloadBlobAsFile(blob, artifact.filename);
  };

  const handleReportDownload = async (
    reportFormat: PatentPriorArtReportFormat,
  ) => {
    const blob = await controller.downloadReport(reportFormat);
    if (blob) {
      downloadBlobAsFile(blob, REPORT_DOWNLOAD_FILENAMES[reportFormat]);
    }
  };

  return (
    <main className="flex h-full min-h-0 w-full flex-col bg-app-bg text-app-ink">
      <header className="border-b border-app-border bg-app-surface px-4 py-4 sm:px-6">
        <div className="mx-auto flex w-full max-w-7xl items-start gap-3">
          <span className="rounded-lg bg-app-accent/10 p-2 text-app-accent">
            <FileSearch aria-hidden="true" className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h1 className="app-text-title-lg">
              {t('ai.patentPriorArt.title')}
            </h1>
            <p className="mt-1 app-text-body-sm text-app-ink/60">
              {t('ai.patentPriorArt.subtitle')}
            </p>
          </div>
        </div>
      </header>

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid w-full max-w-7xl gap-4 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
          <div className="order-2 min-w-0 space-y-4 lg:order-1">
            {controller.issue ? (
              <InlineNotice role="alert" tone="danger">
                {t(`ai.patentPriorArt.errors.${controller.issue}`)}
              </InlineNotice>
            ) : null}
            {controller.pollInterrupted ? (
              <InlineNotice role="status" tone="warning">
                {t('ai.patentPriorArt.poll.interrupted')}
              </InlineNotice>
            ) : null}
            {!workspaceSlug ? (
              <InlineNotice role="alert" tone="warning">
                {t('ai.patentPriorArt.errors.workspace')}
              </InlineNotice>
            ) : null}

            <section
              aria-labelledby="patent-prior-art-input-title"
              className="rounded-xl border border-app-border bg-app-surface p-4 sm:p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2
                    className="app-text-title-md"
                    id="patent-prior-art-input-title"
                  >
                    {t('ai.patentPriorArt.input.title')}
                  </h2>
                  <p className="mt-1 app-text-body-sm text-app-ink/55">
                    {t('ai.patentPriorArt.input.description')}
                  </p>
                </div>
                {controller.config ? (
                  <span className="rounded-full border border-app-border bg-app-surface-sidebar px-2.5 py-1 app-text-caption text-app-ink/55">
                    {t('ai.patentPriorArt.input.formats', {
                      formats: controller.config.allowed_upload_extensions
                        .join(', ')
                        .toUpperCase(),
                    })}
                  </span>
                ) : null}
              </div>

              <InlineNotice className="mt-4" tone="info">
                {t('ai.patentPriorArt.policy.externalProcessing')}
              </InlineNotice>

              {controller.loading ? (
                <div
                  aria-live="polite"
                  className="flex items-center gap-2 py-8 app-text-body-sm text-app-ink/55"
                >
                  <Loader2
                    aria-hidden="true"
                    className="animate-spin"
                    size={16}
                  />
                  {t('ai.patentPriorArt.common.loading')}
                </div>
              ) : null}

              {controller.config ? (
                <div className="mt-5 space-y-5">
                  <div>
                    <label
                      className="app-text-control-sm font-semibold"
                      htmlFor="patent-prior-art-title"
                    >
                      {t('ai.patentPriorArt.input.jobTitle')}
                    </label>
                    <input
                      className="mt-2 w-full rounded-md border border-app-border bg-app-surface px-3 py-2 app-text-body-sm text-app-ink outline-none focus:border-app-accent focus:ring-2 focus:ring-app-accent/15"
                      id="patent-prior-art-title"
                      maxLength={200}
                      onChange={(event) =>
                        controller.setTitle(event.target.value)
                      }
                      placeholder={t(
                        'ai.patentPriorArt.input.jobTitlePlaceholder',
                      )}
                      value={controller.title}
                    />
                  </div>

                  <div>
                    <label
                      className="app-text-control-sm font-semibold"
                      htmlFor="patent-prior-art-file"
                    >
                      {t('ai.patentPriorArt.input.fileLabel')}
                    </label>
                    <div className="mt-2 rounded-lg border border-dashed border-app-border bg-app-surface-sidebar p-3">
                      <div className="flex flex-wrap items-center gap-3">
                        <Paperclip
                          aria-hidden="true"
                          className="text-app-ink/45"
                          size={17}
                        />
                        <input
                          accept={controller.config.allowed_upload_extensions.join(
                            ',',
                          )}
                          aria-describedby="patent-prior-art-file-help"
                          className="min-w-0 flex-1 app-text-body-sm file:mr-3 file:rounded-md file:border file:border-app-border file:bg-app-surface file:px-3 file:py-1.5 file:app-text-control-sm file:text-app-ink hover:file:bg-app-surface-hover"
                          disabled={
                            controller.busyAction === 'parse' ||
                            Boolean(controller.parsedFile)
                          }
                          id="patent-prior-art-file"
                          onChange={(event) => {
                            const file = event.currentTarget.files?.[0];
                            if (file) void controller.parseFile(file);
                            event.currentTarget.value = '';
                          }}
                          type="file"
                        />
                        {controller.busyAction === 'parse' ? (
                          <span className="inline-flex items-center gap-1.5 app-text-caption text-app-ink/55">
                            <Loader2
                              aria-hidden="true"
                              className="animate-spin"
                              size={14}
                            />
                            {t('ai.patentPriorArt.input.parsing')}
                          </span>
                        ) : null}
                      </div>
                      <p
                        className="mt-2 app-text-caption text-app-ink/50"
                        id="patent-prior-art-file-help"
                      >
                        {t('ai.patentPriorArt.input.fileHelp', {
                          size: Math.floor(
                            controller.config.max_upload_bytes / 1024 / 1024,
                          ),
                        })}
                      </p>
                    </div>
                    {controller.parsedFile ? (
                      <div className="mt-2 flex items-center justify-between gap-3 rounded-md border border-app-success-border bg-app-success-bg px-3 py-2 app-text-body-sm text-app-success-text">
                        <span className="min-w-0 truncate">
                          {t('ai.patentPriorArt.input.parsedFile', {
                            count: controller.parsedFile.character_count,
                            filename: controller.parsedFile.filename,
                          })}
                        </span>
                        <button
                          aria-label={t('ai.patentPriorArt.input.removeFile', {
                            filename: controller.parsedFile.filename,
                          })}
                          className="shrink-0 rounded p-1 hover:bg-app-surface-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-app-accent"
                          onClick={controller.removeParsedFile}
                          type="button"
                        >
                          <X aria-hidden="true" size={15} />
                        </button>
                      </div>
                    ) : null}
                  </div>

                  <div>
                    <div className="flex items-end justify-between gap-3">
                      <label
                        className="app-text-control-sm font-semibold"
                        htmlFor="patent-prior-art-invention"
                      >
                        {t('ai.patentPriorArt.input.inventionLabel')}
                      </label>
                      <span className="app-text-caption text-app-ink/45">
                        {t('ai.patentPriorArt.input.characterCount', {
                          count: controller.inventionText.length,
                          max: controller.config.max_invention_chars,
                        })}
                      </span>
                    </div>
                    <textarea
                      className="mt-2 min-h-52 w-full resize-y rounded-md border border-app-border bg-app-surface px-3 py-2 app-text-body-sm leading-relaxed text-app-ink outline-none focus:border-app-accent focus:ring-2 focus:ring-app-accent/15"
                      id="patent-prior-art-invention"
                      maxLength={controller.config.max_invention_chars}
                      onChange={(event) =>
                        controller.setInventionText(event.target.value)
                      }
                      placeholder={t(
                        'ai.patentPriorArt.input.inventionPlaceholder',
                      )}
                      value={controller.inventionText}
                    />
                    {!controller.canPreview &&
                    controller.inventionText.length > 0 ? (
                      <p className="mt-1 app-text-caption text-app-ink/50">
                        {t('ai.patentPriorArt.input.minimumCharacters', {
                          count: controller.config.min_invention_chars,
                        })}
                      </p>
                    ) : null}
                  </div>

                  <fieldset>
                    <legend className="app-text-control-sm font-semibold">
                      {t('ai.patentPriorArt.input.categoryLegend')}
                    </legend>
                    <p className="mt-1 app-text-caption text-app-ink/50">
                      {t('ai.patentPriorArt.input.categoryHelp')}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {controller.config.categories.map((option) => {
                        const selected = controller.categoryIds.includes(
                          option.id,
                        );
                        return (
                          <button
                            aria-pressed={selected}
                            className={cn(
                              'inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 app-text-control-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-app-accent',
                              selected
                                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                                : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
                            )}
                            key={option.id}
                            onClick={() => controller.toggleCategory(option.id)}
                            title={
                              option.description_key
                                ? optionLabel(
                                    option.description_key,
                                    option.fallback_description ?? '',
                                  )
                                : undefined
                            }
                            type="button"
                          >
                            {selected ? (
                              <Check aria-hidden="true" size={14} />
                            ) : null}
                            {optionLabel(
                              option.label_key,
                              option.fallback_label,
                            )}
                          </button>
                        );
                      })}
                    </div>
                    <div className="mt-2 space-y-1" role="status">
                      {controller.config.categories
                        .filter(
                          (option) =>
                            controller.categoryIds.includes(option.id) &&
                            option.description_key,
                        )
                        .map((option) => (
                          <p
                            className="app-text-caption text-app-ink/55"
                            key={option.id}
                          >
                            {optionLabel(
                              option.description_key ?? '',
                              option.fallback_description ?? '',
                            )}
                          </p>
                        ))}
                    </div>
                  </fieldset>

                  <fieldset>
                    <legend className="app-text-control-sm font-semibold">
                      {t('ai.patentPriorArt.input.jurisdictionLegend')}
                    </legend>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {controller.config.jurisdictions.map((option) => {
                        const selected = controller.jurisdictionIds.includes(
                          option.id,
                        );
                        return (
                          <button
                            aria-pressed={selected}
                            className={cn(
                              'inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 app-text-control-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-app-accent',
                              selected
                                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                                : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
                            )}
                            key={option.id}
                            onClick={() =>
                              controller.toggleJurisdiction(option.id)
                            }
                            type="button"
                          >
                            {selected ? (
                              <Check aria-hidden="true" size={14} />
                            ) : null}
                            {optionLabel(
                              option.label_key,
                              option.fallback_label,
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </fieldset>

                  <div className="flex justify-end">
                    <Button
                      disabled={
                        !controller.canPreview ||
                        controller.busyAction === 'preview'
                      }
                      onClick={() => void controller.createPreview()}
                      variant="primary"
                    >
                      {controller.busyAction === 'preview' ? (
                        <Loader2
                          aria-hidden="true"
                          className="animate-spin"
                          size={15}
                        />
                      ) : (
                        <Search aria-hidden="true" size={15} />
                      )}
                      {t('ai.patentPriorArt.actions.preview')}
                    </Button>
                  </div>
                </div>
              ) : null}
            </section>

            {preview && config ? (
              <section
                aria-labelledby="patent-prior-art-plan-title"
                className="rounded-xl border border-app-border bg-app-surface p-4 sm:p-5"
              >
                <div>
                  <h2
                    className="app-text-title-md"
                    id="patent-prior-art-plan-title"
                  >
                    {t('ai.patentPriorArt.plan.title')}
                  </h2>
                  <p className="mt-1 app-text-body-sm text-app-ink/55">
                    {t('ai.patentPriorArt.plan.description')}
                  </p>
                </div>

                <div className="mt-4 rounded-lg border border-app-border bg-app-surface-sidebar p-3">
                  <h3 className="app-text-control-sm font-semibold">
                    {t('ai.patentPriorArt.plan.summary')}
                  </h3>
                  <p className="mt-1 whitespace-pre-wrap app-text-body-sm leading-relaxed text-app-ink/70">
                    {preview.technology_summary}
                  </p>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {EDITABLE_PLAN_FIELDS.map((field) => (
                    <PlanChipEditor
                      field={field}
                      key={field}
                      label={t(`ai.patentPriorArt.plan.fields.${field}`)}
                      maxValueChars={config.max_plan_value_chars}
                      maxValuesPerField={config.max_plan_values_per_field}
                      onAdd={controller.addPlanValue}
                      onRemove={controller.removePlanValue}
                      searchValues={preview.plan[field]}
                    />
                  ))}
                </div>

                <div className="mt-4">
                  <h3
                    className="app-text-control-sm font-semibold"
                    id="patent-prior-art-display-query-label"
                  >
                    {t('ai.patentPriorArt.plan.displayQuery')}
                  </h3>
                  <pre
                    aria-labelledby="patent-prior-art-display-query-label"
                    className="mt-2 min-h-20 overflow-x-auto whitespace-pre-wrap rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 font-mono app-text-caption text-app-ink/75"
                  >
                    {preview.plan.display_query}
                  </pre>
                  <p className="mt-1 app-text-caption text-app-ink/50">
                    {t('ai.patentPriorArt.plan.displayQueryHelp')}
                  </p>
                </div>

                {(preview.source_queries ?? []).length > 0 ? (
                  <details className="mt-4 rounded-lg border border-app-border bg-app-surface-sidebar p-3">
                    <summary className="cursor-pointer app-text-control-sm font-semibold">
                      {t('ai.patentPriorArt.plan.previewQueries', {
                        count: preview.source_queries?.length ?? 0,
                      })}
                    </summary>
                    <ul className="mt-3 space-y-2">
                      {(preview.source_queries ?? []).map((query, index) => (
                        <li
                          className="rounded border border-app-border bg-app-surface p-2"
                          key={`${query.source_id}-${query.jurisdiction}-${index}`}
                        >
                          <p className="app-text-caption font-semibold text-app-ink/60">
                            {query.source_label} · {query.jurisdiction}
                          </p>
                          <p className="mt-1 whitespace-pre-wrap font-mono app-text-caption text-app-ink/75">
                            {query.query_text}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}

                <div className="mt-5 flex justify-end">
                  <Button
                    disabled={!controller.canCreate}
                    onClick={() => void controller.createJob()}
                    variant="primary"
                  >
                    {controller.busyAction === 'create' ? (
                      <Loader2
                        aria-hidden="true"
                        className="animate-spin"
                        size={15}
                      />
                    ) : (
                      <Play aria-hidden="true" size={15} />
                    )}
                    {t('ai.patentPriorArt.actions.start')}
                  </Button>
                </div>
              </section>
            ) : null}

            {controller.activeJob ? (
              <section
                aria-labelledby="patent-prior-art-job-title"
                className="rounded-xl border border-app-border bg-app-surface p-4 sm:p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2
                      className="app-text-title-md"
                      id="patent-prior-art-job-title"
                    >
                      {controller.activeJob.title ||
                        t('ai.patentPriorArt.history.untitled')}
                    </h2>
                    <p className="mt-1 flex flex-wrap items-center gap-2 app-text-body-sm text-app-ink/55">
                      <span>
                        {t(
                          `ai.patentPriorArt.status.${patentPriorArtJobDisplayStatus(controller.activeJob)}`,
                        )}
                      </span>
                      <span aria-hidden="true">·</span>
                      <UserDateTime
                        display="datetime"
                        value={controller.activeJob.updated_at}
                      />
                    </p>
                  </div>
                  {controller.activeJob.can_cancel ? (
                    <Button
                      disabled={controller.busyAction === 'cancel'}
                      onClick={() => {
                        const job = controller.activeJob;
                        if (job) void controller.cancelJob(job);
                      }}
                      variant="secondary"
                    >
                      {t('ai.patentPriorArt.actions.cancel')}
                    </Button>
                  ) : null}
                </div>
                {['queued', 'running'].includes(controller.activeJob.status) ? (
                  <div className="mt-4">
                    <div className="mb-1 flex justify-between app-text-caption text-app-ink/55">
                      <span>{t('ai.patentPriorArt.progress.label')}</span>
                      <span>{controller.activeJob.progress_percent}%</span>
                    </div>
                    <div
                      aria-label={t('ai.patentPriorArt.progress.ariaLabel')}
                      aria-valuemax={100}
                      aria-valuemin={0}
                      aria-valuenow={controller.activeJob.progress_percent}
                      className="h-2 overflow-hidden rounded-full bg-app-surface-sidebar"
                      role="progressbar"
                    >
                      <div
                        className="h-full rounded-full bg-app-accent transition-[width]"
                        style={{
                          width: `${controller.activeJob.progress_percent}%`,
                        }}
                      />
                    </div>
                  </div>
                ) : null}
                <PatentPriorArtJobStatusNotice job={controller.activeJob} />
              </section>
            ) : null}

            {controller.result ? (
              <PatentPriorArtResultPanel
                busy={controller.busyAction === 'download'}
                onDownload={(artifact) => void handleDownload(artifact)}
                onDownloadReport={(reportFormat) =>
                  void handleReportDownload(reportFormat)
                }
                reportFormats={controller.config?.report_formats ?? []}
                result={controller.result}
              />
            ) : null}
          </div>

          <div className="order-1 lg:order-2 lg:sticky lg:top-4">
            <PatentPriorArtHistoryPanel
              activeJobId={controller.activeJob?.id ?? null}
              busy={controller.busyAction !== null}
              jobs={controller.history}
              onCancel={(job) => void controller.cancelJob(job)}
              onDelete={(job) => {
                if (
                  window.confirm(
                    t('ai.patentPriorArt.history.confirmDelete', {
                      title:
                        job.title || t('ai.patentPriorArt.history.untitled'),
                    }),
                  )
                ) {
                  void controller.deleteJob(job);
                }
              }}
              onRefresh={() => void controller.refreshHistory()}
              onSelect={controller.selectJob}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
