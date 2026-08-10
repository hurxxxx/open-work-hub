import { sysPerfDbSave, sysPerfSheetData } from '../api/dataviz-api';
import { buildSysPerfDbSavePayload } from './sysperf-db-save';
import type { PartsState } from './sysperf-parts-state';
import type { SysPerfSheetPreview } from './sysperf-table-preview';
import type { CommonInfo, FileInfo } from './sysperf-testinfo';

export interface SysPerfTableLoaderDeps {
  getSheetData: typeof sysPerfSheetData;
  saveDb: typeof sysPerfDbSave;
}

export const SYS_PERF_TABLE_LOADER_DEPS: SysPerfTableLoaderDeps = {
  getSheetData: sysPerfSheetData,
  saveDb: sysPerfDbSave,
};

export interface SysPerfSheetPreviewLoadResult {
  preview: SysPerfSheetPreview | null;
  error: string | null;
}

export async function loadSysPerfSheetPreview({
  token,
  workspaceSlug,
  fileId,
  sheet,
  fallbackError,
  deps = SYS_PERF_TABLE_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  fileId: number;
  sheet: string;
  fallbackError: string;
  deps?: SysPerfTableLoaderDeps;
}): Promise<SysPerfSheetPreviewLoadResult> {
  try {
    const payload = await deps.getSheetData(
      token,
      workspaceSlug,
      fileId,
      sheet,
      500,
    );
    if (payload.error) {
      return { preview: null, error: payload.error };
    }
    return {
      preview: {
        columns: payload.columns,
        data: payload.data,
        total_rows: payload.total_rows,
      },
      error: null,
    };
  } catch (error) {
    return {
      preview: null,
      error: error instanceof Error ? error.message : fallbackError,
    };
  }
}

export async function saveSysPerfTableDb({
  token,
  workspaceSlug,
  fileId,
  sheet,
  common,
  perFile,
  parts,
  deps = SYS_PERF_TABLE_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  fileId: number;
  sheet: string;
  common: CommonInfo;
  perFile: Record<number, FileInfo>;
  parts: Record<number, PartsState>;
  deps?: SysPerfTableLoaderDeps;
}): ReturnType<typeof sysPerfDbSave> {
  return deps.saveDb(
    token,
    workspaceSlug,
    buildSysPerfDbSavePayload({
      fileId,
      sheet,
      common,
      perFile,
      parts,
    }),
  );
}
