import {
  sysPerfDeleteColumn,
  sysPerfGetColumns,
  sysPerfSaveColumn,
  type SysPerfStandardColumn,
} from '../api/dataviz-api';

export type { SysPerfStandardColumn };

export interface SysPerfBaseColumnDraft {
  standard_name: string;
  keywords: string;
  unit: string;
  category: string;
}

export interface SysPerfBaseColumnsLoaderDeps {
  getColumns: typeof sysPerfGetColumns;
  saveColumn: typeof sysPerfSaveColumn;
  deleteColumn: typeof sysPerfDeleteColumn;
}

export const SYS_PERF_BASE_COLUMNS_LOADER_DEPS: SysPerfBaseColumnsLoaderDeps = {
  getColumns: sysPerfGetColumns,
  saveColumn: sysPerfSaveColumn,
  deleteColumn: sysPerfDeleteColumn,
};

export function isSysPerfBaseColumnDraftSubmittable(
  draft: SysPerfBaseColumnDraft,
): boolean {
  return draft.standard_name.trim().length > 0;
}

export function buildSysPerfBaseColumnSavePayload(
  draft: SysPerfBaseColumnDraft,
): Partial<SysPerfStandardColumn> & { standard_name: string } {
  return {
    standard_name: draft.standard_name.trim(),
    keywords: draft.keywords,
    unit: draft.unit,
    category: draft.category,
  };
}

export async function loadSysPerfBaseColumns({
  token,
  workspaceSlug,
  deps = SYS_PERF_BASE_COLUMNS_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  deps?: SysPerfBaseColumnsLoaderDeps;
}): Promise<SysPerfStandardColumn[]> {
  const response = await deps.getColumns(token, workspaceSlug);
  return response.data;
}

export async function saveSysPerfBaseColumn({
  token,
  workspaceSlug,
  draft,
  deps = SYS_PERF_BASE_COLUMNS_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  draft: SysPerfBaseColumnDraft;
  deps?: SysPerfBaseColumnsLoaderDeps;
}): ReturnType<typeof sysPerfSaveColumn> {
  return deps.saveColumn(
    token,
    workspaceSlug,
    buildSysPerfBaseColumnSavePayload(draft),
  );
}

export async function deleteSysPerfBaseColumn({
  token,
  workspaceSlug,
  columnId,
  deps = SYS_PERF_BASE_COLUMNS_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  columnId: number;
  deps?: SysPerfBaseColumnsLoaderDeps;
}): ReturnType<typeof sysPerfDeleteColumn> {
  return deps.deleteColumn(token, workspaceSlug, columnId);
}
