import type {
  FileUploadProgress,
  FileVisibility,
} from './api/files-api';

export const FILES_CHANGED_EVENT = 'files:changed';
export const FILES_UPLOAD_COMPLETED_EVENT = 'files:upload-completed';

export type FileUploadStatus = 'uploading' | 'succeeded' | 'failed';

export interface FileUploadRecord {
  id: string;
  currentFileIndex: number;
  currentFileName: string;
  errorMessage?: string;
  loadedBytes: number;
  percent: number;
  status: FileUploadStatus;
  totalBytes: number;
  totalFiles: number;
  updatedAt: number;
}

export interface StartFileUploadInput {
  files: File[];
  folderId: string | null;
  token: string;
  uploadVisibility: FileVisibility;
  workspaceSlug: string;
}

export type FileUploadProgressSnapshot = {
  fileIndex: number;
  fileName: string;
  loadedBytes: number;
  percent: number;
};

export type FileUploadEventDescriptor = {
  detail: {
    folderId: string | null;
    workspaceSlug: string;
  };
  name: typeof FILES_CHANGED_EVENT | typeof FILES_UPLOAD_COMPLETED_EVENT;
};

export type FileUploadFileAdapter = (input: {
  file: File;
  folderId: string | null;
  onProgress: (progress: FileUploadProgress) => void;
  signal: AbortSignal;
  token: string;
  visibility: FileVisibility;
  workspaceSlug: string;
}) => Promise<unknown>;

export type FileUploadBatchResult =
  | { ok: true }
  | { errorMessage: string; ok: false };

export function canStartFileUpload({
  hasActiveUpload,
  files,
}: {
  files: readonly File[];
  hasActiveUpload: boolean;
}): boolean {
  return !hasActiveUpload && files.length > 0;
}

export function createFileUploadId({
  now,
  sequence,
}: {
  now: number;
  sequence: number;
}): string {
  return `file-upload-${now}-${sequence}`;
}

export function createFileUploadRecord({
  files,
  id,
  now,
}: {
  files: readonly File[];
  id: string;
  now: number;
}): FileUploadRecord {
  return {
    id,
    currentFileIndex: 1,
    currentFileName: files[0]?.name ?? '',
    loadedBytes: 0,
    percent: 0,
    status: 'uploading',
    totalBytes: getTotalUploadBytes(files),
    totalFiles: files.length,
    updatedAt: now,
  };
}

export function dismissFileUploadRecord(
  uploads: readonly FileUploadRecord[],
  uploadId: string,
): FileUploadRecord[] {
  return uploads.filter(
    (upload) => upload.id !== uploadId || upload.status === 'uploading',
  );
}

export function applyFileUploadProgress({
  now,
  progress,
  upload,
}: {
  now: number;
  progress: FileUploadProgressSnapshot;
  upload: FileUploadRecord;
}): FileUploadRecord {
  return {
    ...upload,
    currentFileIndex: progress.fileIndex,
    currentFileName: progress.fileName,
    loadedBytes: progress.loadedBytes,
    percent: progress.percent,
    updatedAt: now,
  };
}

export function completeFileUploadRecord({
  now,
  upload,
}: {
  now: number;
  upload: FileUploadRecord;
}): FileUploadRecord {
  return {
    ...upload,
    loadedBytes: upload.totalBytes,
    percent: 100,
    status: 'succeeded',
    updatedAt: now,
  };
}

export function failFileUploadRecord({
  errorMessage,
  now,
  upload,
}: {
  errorMessage: string;
  now: number;
  upload: FileUploadRecord;
}): FileUploadRecord {
  return {
    ...upload,
    errorMessage,
    status: 'failed',
    updatedAt: now,
  };
}

export function getFileUploadSuccessEvents({
  folderId,
  workspaceSlug,
}: {
  folderId: string | null;
  workspaceSlug: string;
}): FileUploadEventDescriptor[] {
  const detail = { folderId, workspaceSlug };
  return [
    { detail, name: FILES_UPLOAD_COMPLETED_EVENT },
    { detail, name: FILES_CHANGED_EVENT },
  ];
}

export async function runFileUploadBatch({
  fallbackErrorMessage,
  files,
  folderId,
  onProgress,
  signal,
  token,
  uploadFile,
  uploadVisibility,
  workspaceSlug,
}: {
  fallbackErrorMessage: string;
  files: File[];
  folderId: string | null;
  onProgress: (progress: FileUploadProgressSnapshot) => void;
  signal: AbortSignal;
  token: string;
  uploadFile: FileUploadFileAdapter;
  uploadVisibility: FileVisibility;
  workspaceSlug: string;
}): Promise<FileUploadBatchResult> {
  const totalBytes = getTotalUploadBytes(files);
  let completedBytes = 0;

  try {
    for (const [index, file] of files.entries()) {
      const completedBytesBeforeFile = completedBytes;
      await uploadFile({
        file,
        folderId,
        onProgress: (progress) => {
          onProgress(
            buildFileUploadProgressSnapshot({
              completedBytes: completedBytesBeforeFile,
              file,
              fileIndex: index + 1,
              progress,
              totalBytes,
            }),
          );
        },
        signal,
        token,
        visibility: uploadVisibility,
        workspaceSlug,
      });
      completedBytes += file.size;
      onProgress({
        fileIndex: index + 1,
        fileName: file.name,
        loadedBytes: Math.min(totalBytes, completedBytes),
        percent:
          totalBytes > 0
            ? Math.round(
                (Math.min(totalBytes, completedBytes) / totalBytes) * 100,
              )
            : 100,
      });
    }
    return { ok: true };
  } catch (caughtError) {
    return {
      errorMessage:
        caughtError instanceof Error
          ? caughtError.message
          : fallbackErrorMessage,
      ok: false,
    };
  }
}

export function buildFileUploadProgressSnapshot({
  completedBytes,
  file,
  fileIndex,
  progress,
  totalBytes,
}: {
  completedBytes: number;
  file: File;
  fileIndex: number;
  progress: FileUploadProgress;
  totalBytes: number;
}): FileUploadProgressSnapshot {
  const currentLoaded =
    progress.total > 0
      ? Math.min(progress.loaded, progress.total)
      : Math.min(progress.loaded, file.size);
  const loadedBytes = Math.min(totalBytes, completedBytes + currentLoaded);
  return {
    fileIndex,
    fileName: file.name,
    loadedBytes,
    percent: totalBytes > 0 ? Math.round((loadedBytes / totalBytes) * 100) : 0,
  };
}

function getTotalUploadBytes(files: readonly File[]): number {
  return files.reduce((total, file) => total + file.size, 0);
}
