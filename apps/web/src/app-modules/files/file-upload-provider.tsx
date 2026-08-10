import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  UploadCloud,
  X,
} from 'lucide-react';
import { useToast } from '@open-work-hub/ui/providers/toast-provider';

import { cn } from '@/src/lib/utils';
import { formatByteSize } from '@/src/platform/format/byte-size';
import { uploadDriveFile } from './api/files-api';
import {
  applyFileUploadProgress,
  canStartFileUpload,
  completeFileUploadRecord,
  createFileUploadId,
  createFileUploadRecord,
  dismissFileUploadRecord,
  failFileUploadRecord,
  getFileUploadSuccessEvents,
  runFileUploadBatch,
  type FileUploadRecord,
  type StartFileUploadInput,
} from './file-upload-session';

interface FileUploadManagerContextValue {
  hasActiveUploads: boolean;
  startUpload: (input: StartFileUploadInput) => boolean;
}

const FileUploadManagerContext =
  createContext<FileUploadManagerContextValue | null>(null);
const FILE_UPLOAD_PROVIDER_REQUIRED_ERROR =
  'useFileUploadManager must be used within FileUploadProvider';

export function FileUploadProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation('apps');
  const toast = useToast();
  const activeUploadRef = useRef(false);
  const activeUploadAbortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const sequenceRef = useRef(0);
  const [collapsed, setCollapsed] = useState(false);
  const [uploads, setUploads] = useState<FileUploadRecord[]>([]);
  const hasActiveUploads = uploads.some(
    (upload) => upload.status === 'uploading',
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      activeUploadAbortRef.current?.abort();
      activeUploadAbortRef.current = null;
      activeUploadRef.current = false;
    };
  }, []);

  const dismissUpload = useCallback((uploadId: string) => {
    setUploads((current) => dismissFileUploadRecord(current, uploadId));
  }, []);

  const startUpload = useCallback(
    (input: StartFileUploadInput) => {
      if (
        !canStartFileUpload({
          files: input.files,
          hasActiveUpload: activeUploadRef.current,
        })
      ) {
        return false;
      }

      const now = Date.now();
      sequenceRef.current += 1;
      const uploadId = createFileUploadId({
        now,
        sequence: sequenceRef.current,
      });
      activeUploadRef.current = true;
      const files = [...input.files];
      const abortController = new AbortController();
      activeUploadAbortRef.current = abortController;

      const releaseUpload = () => {
        if (activeUploadAbortRef.current === abortController) {
          activeUploadAbortRef.current = null;
        }
        activeUploadRef.current = false;
      };

      setCollapsed(false);
      setUploads((current) => [
        ...current,
        createFileUploadRecord({ files, id: uploadId, now }),
      ]);

      void runFileUploadBatch({
        files,
        fallbackErrorMessage: t('files.errors.uploadFailed'),
        folderId: input.folderId,
        onProgress: (progress) => {
          if (!mountedRef.current) {
            return;
          }
          setUploads((current) =>
            current.map((upload) =>
              upload.id === uploadId
                ? applyFileUploadProgress({
                    now: Date.now(),
                    progress,
                    upload,
                  })
                : upload,
            ),
          );
        },
        signal: abortController.signal,
        token: input.token,
        uploadFile: ({
          file,
          folderId,
          onProgress,
          signal,
          token,
          visibility,
          workspaceSlug,
        }) =>
          uploadDriveFile(token, workspaceSlug, file, {
            folderId,
            onProgress,
            signal,
            visibility,
          }),
        uploadVisibility: input.uploadVisibility,
        workspaceSlug: input.workspaceSlug,
      }).then((result) => {
        if (result.ok) {
          releaseUpload();
          if (!mountedRef.current) {
            return;
          }
          setUploads((current) =>
            current.map((upload) =>
              upload.id === uploadId
                ? completeFileUploadRecord({
                    now: Date.now(),
                    upload,
                  })
                : upload,
            ),
          );
          for (const event of getFileUploadSuccessEvents({
            folderId: input.folderId,
            workspaceSlug: input.workspaceSlug,
          })) {
            window.dispatchEvent(
              new CustomEvent(event.name, { detail: event.detail }),
            );
          }
          toast.success(
            t('files.uploadProgress.completedTitle'),
            t('files.uploadProgress.completedDescription', {
              count: files.length,
            }),
          );
          return;
        }

        releaseUpload();
        if (!mountedRef.current) {
          return;
        }
        setUploads((current) =>
          current.map((upload) =>
            upload.id === uploadId
              ? failFileUploadRecord({
                  errorMessage: result.errorMessage,
                  now: Date.now(),
                  upload,
                })
              : upload,
          ),
        );
        toast.error(t('files.uploadProgress.failedTitle'), result.errorMessage);
      });

      return true;
    },
    [t, toast],
  );

  const value = useMemo<FileUploadManagerContextValue>(
    () => ({
      hasActiveUploads,
      startUpload,
    }),
    [hasActiveUploads, startUpload],
  );

  return (
    <FileUploadManagerContext.Provider value={value}>
      {children}
      <FileUploadFloatingPanel
        collapsed={collapsed}
        onDismiss={dismissUpload}
        onToggleCollapsed={() => setCollapsed((current) => !current)}
        uploads={uploads}
      />
    </FileUploadManagerContext.Provider>
  );
}

export function useFileUploadManager(): FileUploadManagerContextValue {
  const context = use(FileUploadManagerContext);
  if (!context) {
    throw new Error(FILE_UPLOAD_PROVIDER_REQUIRED_ERROR);
  }
  return context;
}

function FileUploadFloatingPanel({
  collapsed,
  onDismiss,
  onToggleCollapsed,
  uploads,
}: {
  collapsed: boolean;
  onDismiss: (uploadId: string) => void;
  onToggleCollapsed: () => void;
  uploads: FileUploadRecord[];
}) {
  const { t } = useTranslation(['apps', 'common']);

  if (uploads.length === 0) {
    return null;
  }

  const activeCount = uploads.filter(
    (upload) => upload.status === 'uploading',
  ).length;

  return (
    <section
      aria-label={t('files.uploadProgress.regionLabel')}
      className="fixed bottom-24 right-4 z-30 w-[min(390px,calc(100vw-2rem))] overflow-hidden rounded-lg border border-app-border bg-app-bg shadow-2xl"
    >
      <header className="flex items-center justify-between gap-3 border-b border-app-border px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-app-accent/12 text-app-accent">
            <UploadCloud size={16} />
          </span>
          <div className="min-w-0">
            <h2 className="app-text-control-sm truncate font-semibold text-app-ink">
              {t('files.uploadProgress.title')}
            </h2>
            <p
              className="app-text-micro truncate text-app-ink/55"
              role="status"
              aria-atomic="true"
              aria-live="polite"
            >
              {activeCount > 0
                ? t('files.uploadProgress.activeSummary', {
                    count: activeCount,
                  })
                : t('files.uploadProgress.finishedSummary')}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onToggleCollapsed}
          title={t(
            collapsed
              ? 'files.uploadProgress.expandAction'
              : 'files.uploadProgress.collapseAction',
          )}
          aria-label={t(
            collapsed
              ? 'files.uploadProgress.expandAction'
              : 'files.uploadProgress.collapseAction',
          )}
          className="flex size-8 shrink-0 items-center justify-center rounded-md text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
        >
          {collapsed ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </header>

      {collapsed ? null : (
        <div className="max-h-80 overflow-y-auto">
          {uploads.map((upload) => (
            <UploadRow key={upload.id} onDismiss={onDismiss} upload={upload} />
          ))}
        </div>
      )}
    </section>
  );
}

function UploadRow({
  onDismiss,
  upload,
}: {
  onDismiss: (uploadId: string) => void;
  upload: FileUploadRecord;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const isUploading = upload.status === 'uploading';
  const StatusIcon =
    upload.status === 'succeeded'
      ? CheckCircle2
      : upload.status === 'failed'
        ? AlertCircle
        : Loader2;

  return (
    <div className="border-b border-app-border p-3 last:border-b-0">
      <div className="flex items-start gap-2">
        <StatusIcon
          size={16}
          className={cn(
            'mt-0.5 shrink-0',
            upload.status === 'uploading' && 'animate-spin text-app-accent',
            upload.status === 'succeeded' && 'text-app-success-text',
            upload.status === 'failed' && 'text-[var(--ui-color-danger)]',
          )}
        />
        <div className="min-w-0 flex-1">
          <p className="app-text-body-sm truncate font-medium text-app-ink">
            {t('files.uploadProgress.file', {
              current: upload.currentFileIndex,
              name: upload.currentFileName,
              total: upload.totalFiles,
            })}
          </p>
          <p className="app-text-caption mt-0.5 truncate text-app-ink/55">
            {upload.status === 'failed'
              ? upload.errorMessage
              : t('files.uploadProgress.bytes', {
                  loaded: formatByteSize(
                    upload.loadedBytes,
                    UPLOAD_BYTE_SIZE_OPTIONS,
                  ),
                  percent: upload.percent,
                  total: formatByteSize(
                    upload.totalBytes,
                    UPLOAD_BYTE_SIZE_OPTIONS,
                  ),
                })}
          </p>
        </div>
        {isUploading ? null : (
          <button
            type="button"
            onClick={() => onDismiss(upload.id)}
            title={t('common:actions.close')}
            aria-label={t('files.uploadProgress.dismissAction')}
            className="flex size-7 shrink-0 items-center justify-center rounded-md text-app-ink/45 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
          >
            <X size={14} />
          </button>
        )}
      </div>
      <progress
        className={cn(
          'mt-2 h-2 w-full overflow-hidden rounded-full appearance-none bg-app-surface-hover [&::-moz-progress-bar]:rounded-full [&::-moz-progress-bar]:transition-all [&::-webkit-progress-bar]:rounded-full [&::-webkit-progress-bar]:bg-app-surface-hover [&::-webkit-progress-value]:rounded-full [&::-webkit-progress-value]:transition-all',
          upload.status === 'failed'
            ? '[&::-moz-progress-bar]:bg-[var(--ui-color-danger)] [&::-webkit-progress-value]:bg-[var(--ui-color-danger)]'
            : '[&::-moz-progress-bar]:bg-app-accent [&::-webkit-progress-value]:bg-app-accent',
        )}
        aria-label={t('files.uploadProgress.file', {
          current: upload.currentFileIndex,
          name: upload.currentFileName,
          total: upload.totalFiles,
        })}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={upload.percent}
        max={100}
        value={upload.percent}
      />
    </div>
  );
}

const UPLOAD_BYTE_SIZE_OPTIONS = {
  fractionDigits: 'compact',
  units: ['KB', 'MB', 'GB', 'TB'],
} as const;
