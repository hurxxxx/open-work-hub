import { sysPerfUpload, type SysPerfUploadedFile } from '../api/dataviz-api';
import {
  isUsableSysPerfUploadedFile,
  type UsableSysPerfUploadedFile,
} from './sysperf-files';

export interface SysPerfUploadLoaderDeps {
  upload: typeof sysPerfUpload;
}

export const SYS_PERF_UPLOAD_LOADER_DEPS: SysPerfUploadLoaderDeps = {
  upload: sysPerfUpload,
};

export interface SysPerfUploadFailure {
  filename: string;
  error: string;
}

export interface SysPerfUploadLoadResult {
  usableFiles: UsableSysPerfUploadedFile[];
  failures: SysPerfUploadFailure[];
}

export interface SysPerfUploadSelection {
  fileId: number;
  sheetName: string;
}

export async function uploadSysPerfFiles({
  token,
  workspaceSlug,
  files,
  deps = SYS_PERF_UPLOAD_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  files: File[];
  deps?: SysPerfUploadLoaderDeps;
}): Promise<SysPerfUploadLoadResult> {
  const response = await deps.upload(token, workspaceSlug, files);
  return splitSysPerfUploadResponseFiles(response.files);
}

export function splitSysPerfUploadResponseFiles(
  files: SysPerfUploadedFile[],
): SysPerfUploadLoadResult {
  return {
    usableFiles: files.filter(isUsableSysPerfUploadedFile),
    failures: files.flatMap((file) =>
      file.error ? [{ filename: file.filename, error: file.error }] : [],
    ),
  };
}

export function formatSysPerfUploadFailures(
  failures: SysPerfUploadFailure[],
): string {
  return failures
    .map((failure) => `${failure.filename}: ${failure.error}`)
    .join(' / ');
}

export function selectInitialSysPerfUploadSelection({
  usableFiles,
  currentFileId,
}: {
  usableFiles: UsableSysPerfUploadedFile[];
  currentFileId: number | null;
}): SysPerfUploadSelection | null {
  if (currentFileId != null) return null;
  const firstFile = usableFiles[0];
  if (!firstFile) return null;
  return {
    fileId: firstFile.file_id,
    sheetName: firstFile.sheets[0].sheet_name,
  };
}
