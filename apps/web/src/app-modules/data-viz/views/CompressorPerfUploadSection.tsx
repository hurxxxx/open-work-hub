import { useTranslation } from 'react-i18next';
import { Loader2, Upload } from 'lucide-react';

import { cn } from '@/src/lib/utils';
import type {
  PerfCategory,
  PerfRefrigerant,
  PerfSourceUploadResult,
} from '../api/dataviz-api';
import type { CompressorPerfUploadSession } from './useCompressorPerfUploadSession';

const REFRIGERANTS: PerfRefrigerant[] = ['new', 'old'];

export interface CompressorPerfUploadSectionProps {
  session: CompressorPerfUploadSession;
  loading: string | null;
  uploadStatus: Record<string, string>;
  onUploadMaster: (
    category: PerfCategory,
    file: File | null,
    clearFile: () => void,
  ) => void | Promise<void>;
  onUploadSources: (
    category: PerfCategory,
    files: File[],
    refrigerant: PerfRefrigerant,
    capacity: string,
    clearFiles: () => void,
  ) => void | Promise<void>;
}

export function CompressorPerfUploadSection({
  session,
  loading,
  uploadStatus,
  onUploadMaster,
  onUploadSources,
}: CompressorPerfUploadSectionProps) {
  const { t } = useTranslation('apps');

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {session.columns.map((column) => {
        const label = t(`ai.dataViz.perf.categories.${column.key}`);
        return (
          <section
            key={column.key}
            className="flex flex-col gap-5 rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5"
          >
            <div>
              <h2 className="app-text-body-sm mb-2 border-l-4 border-app-accent pl-2 font-semibold text-app-ink">
                {t('ai.dataViz.perf.masterUploadTitle', { label })}
              </h2>
              <input
                ref={column.masterRef}
                type="file"
                accept=".xlsx,.xls"
                className="hidden"
                onChange={(event) =>
                  column.setMaster(event.target.files?.[0] ?? null)
                }
              />
              <div
                role="button"
                tabIndex={0}
                onClick={() => column.masterRef.current?.click()}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    column.masterRef.current?.click();
                  }
                }}
                className="flex cursor-pointer items-center justify-between gap-3 rounded-md border-2 border-dashed border-app-border p-3 transition-colors hover:border-app-accent/60 hover:bg-app-accent/5"
              >
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <p className="app-text-body-sm truncate text-center font-medium text-app-ink">
                    {column.master
                      ? column.master.name
                      : t('ai.dataViz.perf.masterPickFile')}
                  </p>
                </div>
              </div>
              <div className="mt-2 flex items-center justify-end gap-3">
                {uploadStatus[`master:${column.key}`] ? (
                  <span className="app-text-caption text-ui-success">
                    {uploadStatus[`master:${column.key}`]}
                  </span>
                ) : null}
                <button
                  type="button"
                  disabled={
                    !column.master || loading === `master:${column.key}`
                  }
                  onClick={() =>
                    void onUploadMaster(
                      column.key,
                      column.master,
                      column.clearMaster,
                    )
                  }
                  style={{ fontSize: '12px' }}
                  className="inline-flex h-7 items-center gap-1.5 rounded-md bg-app-accent px-2.5 font-medium text-app-accent-fg shadow-sm transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loading === `master:${column.key}` ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Upload size={14} />
                  )}
                  {t('ai.dataViz.perf.upload')}
                </button>
              </div>
            </div>

            <div>
              <h2 className="app-text-body-sm mb-2 border-l-4 border-app-accent pl-2 font-semibold text-app-ink">
                {t('ai.dataViz.perf.compFileUploadTitle', { label })}
              </h2>
              <div className="mb-2 inline-flex overflow-hidden rounded-full border border-app-border">
                {REFRIGERANTS.map((refrigerant) => (
                  <button
                    key={refrigerant}
                    type="button"
                    onClick={() => column.setSourceRefrigerant(refrigerant)}
                    style={{ fontSize: '12px' }}
                    className={cn(
                      'px-2 py-0.5 leading-tight transition-colors',
                      column.sourceRefrigerant === refrigerant
                        ? 'bg-app-accent text-app-accent-fg'
                        : 'bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
                    )}
                  >
                    {t(`ai.dataViz.perf.refrigerants.${refrigerant}`)}
                  </button>
                ))}
              </div>
              <div className="mb-2 flex flex-wrap gap-1">
                {column.sourceCapacities.map((capacity) => (
                  <button
                    key={capacity}
                    type="button"
                    onClick={() => column.setSourceCapacity(capacity)}
                    style={{ fontSize: '12px' }}
                    className={cn(
                      'rounded-full border px-1.5 py-0.5 leading-tight transition-colors',
                      column.sourceCapacity === capacity
                        ? 'border-app-accent bg-app-accent text-app-accent-fg'
                        : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover',
                    )}
                  >
                    {capacity}
                  </button>
                ))}
              </div>
              <div
                onDragOver={(event) => {
                  event.preventDefault();
                  column.setDragging(true);
                }}
                onDragLeave={() => column.setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  column.setDragging(false);
                  column.setSourceFiles(Array.from(event.dataTransfer.files));
                }}
                onClick={() => column.sourceInputRef.current?.click()}
                className={cn(
                  'flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed p-6 transition-colors',
                  column.dragging
                    ? 'border-app-accent bg-app-accent/5'
                    : 'border-app-border hover:border-app-accent/60 hover:bg-app-accent/5',
                )}
              >
                <p className="app-text-body-sm font-medium text-app-ink">
                  {t('ai.dataViz.perf.testDataUpload')}
                </p>
                <p className="app-text-caption text-app-ink/55">
                  {t('ai.dataViz.perf.multiFileUploadHint')}
                </p>
                {column.sourceFiles.length > 0 ? (
                  <p className="app-text-caption text-app-accent">
                    {t('ai.dataViz.perf.selectedFileCount', {
                      count: column.sourceFiles.length,
                    })}
                  </p>
                ) : null}
                <input
                  ref={column.sourceInputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  multiple
                  className="hidden"
                  onChange={(event) =>
                    column.setSourceFiles(Array.from(event.target.files ?? []))
                  }
                />
              </div>
              <div className="mt-2 flex items-center justify-end gap-3">
                {uploadStatus[`sources:${column.key}`] ? (
                  <span className="app-text-caption text-ui-success">
                    {uploadStatus[`sources:${column.key}`]}
                  </span>
                ) : null}
                <button
                  type="button"
                  disabled={
                    column.sourceFiles.length === 0 ||
                    loading === `sources:${column.key}`
                  }
                  onClick={() =>
                    void onUploadSources(
                      column.key,
                      column.sourceFiles,
                      column.sourceRefrigerant,
                      column.sourceCapacity,
                      column.clearSourceFiles,
                    )
                  }
                  style={{ fontSize: '12px' }}
                  className="inline-flex h-7 items-center gap-1.5 rounded-md bg-app-accent px-2.5 font-medium text-app-accent-fg shadow-sm transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loading === `sources:${column.key}` ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Upload size={14} />
                  )}
                  {t('ai.dataViz.perf.upload')}
                </button>
              </div>
              <p className="app-text-caption mt-2 text-app-ink/55">
                {t('ai.dataViz.perf.filenamePatternHint')}
              </p>
            </div>
          </section>
        );
      })}

      {session.uploadResult ? (
        <section className="rounded-2xl border border-app-border bg-app-surface p-4 lg:col-span-2 lg:p-5">
          <h2 className="app-text-body-sm mb-3 font-semibold text-app-ink">
            {t('ai.dataViz.perf.uploadResults')}
          </h2>
          <SmallResultTable result={session.uploadResult} />
        </section>
      ) : null}
    </div>
  );
}

function SmallResultTable({ result }: { result: PerfSourceUploadResult }) {
  const { t } = useTranslation('apps');
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-app-border text-left">
            <th className="app-text-caption px-2 py-1.5 font-medium text-app-ink/65">
              {t('ai.dataViz.perf.file')}
            </th>
            <th className="app-text-caption px-2 py-1.5 font-medium text-app-ink/65">
              {t('ai.dataViz.perf.status')}
            </th>
            <th className="app-text-caption px-2 py-1.5 font-medium text-app-ink/65">
              {t('ai.dataViz.perf.rows')}
            </th>
            <th className="app-text-caption px-2 py-1.5 font-medium text-app-ink/65">
              {t('ai.dataViz.perf.warnings')}
            </th>
          </tr>
        </thead>
        <tbody>
          {result.results.map((item) => (
            <tr key={item.filename} className="border-b border-app-border">
              <td className="app-text-body-sm px-2 py-1.5 text-app-ink">
                {item.filename}
              </td>
              <td className="app-text-body-sm px-2 py-1.5 text-app-ink">
                {t(`ai.dataViz.perf.uploadStatus.${item.status}`)}
              </td>
              <td className="app-text-body-sm tabular-nums px-2 py-1.5 text-app-ink">
                {item.row_count}
              </td>
              <td className="app-text-body-sm tabular-nums px-2 py-1.5 text-app-ink">
                {item.warning_count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
