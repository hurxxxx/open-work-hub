import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Upload } from 'lucide-react';
import { InlineNotice } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import { type SysPerfUploadedFile } from '../api/dataviz-api';
import { isUsableSysPerfUploadedFile } from './sysperf-files';
import {
  formatSysPerfUploadFailures,
  selectInitialSysPerfUploadSelection,
  uploadSysPerfFiles,
} from './sysperf-upload-loader';
import { useSysPerfWorkspace } from './sysperf-workspace';

interface SysPerfUploadTabProps {
  uploaded: SysPerfUploadedFile[];
  setUploaded: Dispatch<SetStateAction<SysPerfUploadedFile[]>>;
  selFileId: number | null;
  setSelFileId: (id: number | null) => void;
  selSheet: string;
  setSelSheet: (s: string) => void;
}

export function SysPerfUploadTab({
  uploaded,
  setUploaded,
  selFileId,
  setSelFileId,
  selSheet,
  setSelSheet,
}: SysPerfUploadTabProps) {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const usableUploaded = useMemo(
    () => uploaded.filter(isUsableSysPerfUploadedFile),
    [uploaded],
  );
  const selFile = useMemo(
    () => usableUploaded.find((f) => f.file_id === selFileId) ?? null,
    [usableUploaded, selFileId],
  );

  const onUpload = useCallback(
    async (files: FileList | null) => {
      if (!files || !files.length || !token || !workspaceSlug) return;
      setBusy(true);
      setErr(null);
      try {
        const result = await uploadSysPerfFiles({
          token,
          workspaceSlug,
          files: Array.from(files),
        });
        setUploaded((prev) => [...prev, ...result.usableFiles]);
        if (result.failures.length) {
          setErr(formatSysPerfUploadFailures(result.failures));
        }
        const selection = selectInitialSysPerfUploadSelection({
          usableFiles: result.usableFiles,
          currentFileId: selFileId,
        });
        if (selection) {
          setSelFileId(selection.fileId);
          setSelSheet(selection.sheetName);
        }
      } catch (e) {
        setErr(
          e instanceof Error
            ? e.message
            : t('ai.dataViz.sysPerf.upload.uploadFailed'),
        );
      } finally {
        setBusy(false);
        if (fileRef.current) fileRef.current.value = '';
      }
    },
    [
      token,
      workspaceSlug,
      setUploaded,
      selFileId,
      setSelFileId,
      setSelSheet,
      t,
    ],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
        <div className="app-text-body-sm mb-2 font-semibold text-app-ink">
          {t('ai.dataViz.sysPerf.upload.title')}
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
          className="flex w-full flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-app-border bg-app-bg px-4 py-6 transition-colors hover:border-app-accent/60 hover:bg-app-accent/5 disabled:opacity-60 sm:w-2/3"
        >
          {busy ? (
            <>
              <Loader2 size={20} className="animate-spin text-app-accent" />
              <span className="app-text-body-sm text-app-ink/65">
                {t('ai.dataViz.sysPerf.upload.uploading')}
              </span>
            </>
          ) : (
            <>
              <span className="app-text-body-sm inline-flex items-center gap-2 font-bold text-app-ink">
                <Upload size={18} />
                {t('ai.dataViz.sysPerf.upload.pickExcel')}
              </span>
              <span className="app-text-caption font-bold text-app-ink/80">
                {t('ai.dataViz.sysPerf.upload.filenamePattern')}
              </span>
              <span className="app-text-caption text-app-ink/55">
                {t('ai.dataViz.sysPerf.upload.formatHint')}
              </span>
            </>
          )}
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".xlsx,.xls"
          className="hidden"
          onChange={(e) => onUpload(e.target.files)}
        />
        {err ? (
          <div className="mt-3">
            <InlineNotice tone="danger">{err}</InlineNotice>
          </div>
        ) : null}
      </div>

      {usableUploaded.length ? (
        <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
          <div className="app-text-body-sm mb-3 font-semibold text-app-ink">
            {t('ai.dataViz.sysPerf.upload.uploadedFiles', {
              count: usableUploaded.length,
            })}
          </div>
          <div className="flex flex-col gap-1.5">
            {usableUploaded.map((f) => (
              <button
                key={f.file_id}
                type="button"
                onClick={() => {
                  setSelFileId(f.file_id);
                  setSelSheet(f.sheets[0].sheet_name);
                }}
                className={cn(
                  'app-text-body-sm flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left transition-colors',
                  selFileId === f.file_id
                    ? 'border-app-accent bg-app-accent/5 text-app-ink'
                    : 'border-app-border text-app-ink/75 hover:bg-app-surface-hover',
                )}
              >
                <span className="truncate">{f.filename}</span>
                <span className="app-text-caption shrink-0 text-app-ink/45">
                  {t('ai.dataViz.sysPerf.upload.sheetCount', {
                    count: f.sheets?.length ?? 0,
                  })}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {selFile ? (
        <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
          <div className="app-text-body-sm mb-3 font-semibold text-app-ink">
            {t('ai.dataViz.sysPerf.upload.sheetSelectTitle', {
              filename: selFile.filename,
            })}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {(selFile.sheets ?? []).map((s) => (
              <button
                key={s.sheet_name}
                type="button"
                onClick={() => setSelSheet(s.sheet_name)}
                className={cn(
                  'app-text-control-sm rounded-md border px-2.5 py-1 transition-colors',
                  selSheet === s.sheet_name
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover',
                )}
              >
                {s.sheet_name}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
