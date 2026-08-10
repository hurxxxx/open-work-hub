import { runRequestsWithConcurrency } from '@/src/platform/network/request-concurrency';

import { sysPerfGraphData, type SysPerfGraphData } from '../api/dataviz-api';
import type { UsableSysPerfUploadedFile } from './sysperf-files';
import type { SysPerfGraphDataCache } from './sysperf-graph';
import { toSysPerfGraphDataCache } from './sysperf-graph-state';

const SYS_PERF_GRAPH_FILE_LOAD_CONCURRENCY = 3;

export interface SysPerfGraphLoaderDeps {
  getGraphData: typeof sysPerfGraphData;
}

export const SYS_PERF_GRAPH_LOADER_DEPS: SysPerfGraphLoaderDeps = {
  getGraphData: sysPerfGraphData,
};

export interface SysPerfGraphLoadResult {
  fileId: number;
  cache: SysPerfGraphDataCache;
}

export function selectMissingSysPerfGraphFiles({
  files,
  cache,
  checked,
  retryErrors = false,
}: {
  files: UsableSysPerfUploadedFile[];
  cache: Record<number, SysPerfGraphDataCache>;
  checked?: Record<number, boolean>;
  retryErrors?: boolean;
}): UsableSysPerfUploadedFile[] {
  return files.filter((file) => {
    if (checked && !checked[file.file_id]) return false;
    const cached = cache[file.file_id];
    return !cached || (retryErrors && !!cached.error);
  });
}

export function mergeSysPerfGraphLoadResults(
  cache: Record<number, SysPerfGraphDataCache>,
  results: SysPerfGraphLoadResult[],
): Record<number, SysPerfGraphDataCache> {
  if (!results.length) return cache;
  const next = { ...cache };
  results.forEach((result) => {
    next[result.fileId] = result.cache;
  });
  return next;
}

export async function loadSysPerfGraphFile({
  token,
  workspaceSlug,
  file,
  maxPoints = 3000,
  fallbackError,
  cacheErrors = true,
  deps = SYS_PERF_GRAPH_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  file: UsableSysPerfUploadedFile;
  maxPoints?: number;
  fallbackError: string;
  cacheErrors?: boolean;
  deps?: SysPerfGraphLoaderDeps;
}): Promise<SysPerfGraphLoadResult | null> {
  try {
    const payload: SysPerfGraphData = await deps.getGraphData(
      token,
      workspaceSlug,
      file.file_id,
      file.sheets[0].sheet_name,
      maxPoints,
    );
    return {
      fileId: file.file_id,
      cache: toSysPerfGraphDataCache(payload),
    };
  } catch (error) {
    if (!cacheErrors) return null;
    return {
      fileId: file.file_id,
      cache: {
        data: {},
        units: {},
        error: error instanceof Error ? error.message : fallbackError,
      },
    };
  }
}

export async function loadMissingSysPerfGraphFiles({
  token,
  workspaceSlug,
  files,
  cache,
  checked,
  fallbackError,
  cacheErrors = true,
  deps = SYS_PERF_GRAPH_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  files: UsableSysPerfUploadedFile[];
  cache: Record<number, SysPerfGraphDataCache>;
  checked?: Record<number, boolean>;
  fallbackError: string;
  cacheErrors?: boolean;
  deps?: SysPerfGraphLoaderDeps;
}): Promise<SysPerfGraphLoadResult[]> {
  const missingFiles = selectMissingSysPerfGraphFiles({
    files,
    cache,
    checked,
    retryErrors: !cacheErrors,
  });
  const results = await runRequestsWithConcurrency(
    missingFiles,
    SYS_PERF_GRAPH_FILE_LOAD_CONCURRENCY,
    (file) =>
      loadSysPerfGraphFile({
        token,
        workspaceSlug,
        file,
        fallbackError,
        cacheErrors,
        deps,
      }),
  );
  return results.filter(
    (result): result is SysPerfGraphLoadResult => result !== null,
  );
}
