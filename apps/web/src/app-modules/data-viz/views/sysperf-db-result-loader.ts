import {
  sysPerfDbCsv,
  sysPerfDbDelete,
  sysPerfDbList,
} from '../api/dataviz-api';

export interface SysPerfDbResultLoaderDeps {
  list: typeof sysPerfDbList;
  csv: typeof sysPerfDbCsv;
  delete: typeof sysPerfDbDelete;
}

export const SYS_PERF_DB_RESULT_LOADER_DEPS: SysPerfDbResultLoaderDeps = {
  list: sysPerfDbList,
  csv: sysPerfDbCsv,
  delete: sysPerfDbDelete,
};

export interface SysPerfDbCsvDownload {
  blob: Blob;
  filename: string;
}

export function buildSysPerfDbCsvFilename(
  name: string | null | undefined,
): string {
  const stem = name?.trim() || 'test';
  return `${stem}.csv`;
}

export async function listSysPerfDbResults({
  token,
  workspaceSlug,
  deps = SYS_PERF_DB_RESULT_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  deps?: SysPerfDbResultLoaderDeps;
}): ReturnType<typeof sysPerfDbList> {
  return deps.list(token, workspaceSlug);
}

export async function downloadSysPerfDbCsv({
  token,
  workspaceSlug,
  testId,
  deps = SYS_PERF_DB_RESULT_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  testId: number;
  deps?: SysPerfDbResultLoaderDeps;
}): Promise<Blob> {
  return deps.csv(token, workspaceSlug, testId);
}

export async function prepareSysPerfDbCsvDownload({
  token,
  workspaceSlug,
  testId,
  name,
  deps = SYS_PERF_DB_RESULT_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  testId: number;
  name: string | null | undefined;
  deps?: SysPerfDbResultLoaderDeps;
}): Promise<SysPerfDbCsvDownload> {
  return {
    blob: await deps.csv(token, workspaceSlug, testId),
    filename: buildSysPerfDbCsvFilename(name),
  };
}

export async function deleteSysPerfDbResult({
  token,
  workspaceSlug,
  testId,
  deps = SYS_PERF_DB_RESULT_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  testId: number;
  deps?: SysPerfDbResultLoaderDeps;
}): ReturnType<typeof sysPerfDbDelete> {
  return deps.delete(token, workspaceSlug, testId);
}
