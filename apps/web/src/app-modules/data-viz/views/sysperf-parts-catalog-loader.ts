import {
  sysPerfDeletePartsCatalog,
  sysPerfGetPartsCatalog,
  sysPerfSavePartsCatalog,
  type SysPerfPartsCatalogItem,
  type SysPerfPartsCatalogSavePayload,
} from '../api/dataviz-api';

export type { SysPerfPartsCatalogItem };

export interface SysPerfPartsCatalogDraft {
  category: string;
  drive_type: string;
  sub_type: string;
  name: string;
}

export interface SysPerfPartsCatalogLoaderDeps {
  getPartsCatalog: typeof sysPerfGetPartsCatalog;
  savePartsCatalog: typeof sysPerfSavePartsCatalog;
  deletePartsCatalog: typeof sysPerfDeletePartsCatalog;
}

export const SYS_PERF_PARTS_CATALOG_LOADER_DEPS: SysPerfPartsCatalogLoaderDeps =
  {
    getPartsCatalog: sysPerfGetPartsCatalog,
    savePartsCatalog: sysPerfSavePartsCatalog,
    deletePartsCatalog: sysPerfDeletePartsCatalog,
  };

export function isSysPerfPartsCatalogNameSubmittable(name: string): boolean {
  return name.trim().length > 0;
}

export function buildSysPerfPartsCatalogSavePayload(
  draft: SysPerfPartsCatalogDraft,
): SysPerfPartsCatalogSavePayload {
  return {
    category: draft.category,
    drive_type: draft.drive_type,
    sub_type: draft.sub_type,
    name: draft.name.trim(),
  };
}

export async function loadSysPerfPartsCatalogRows({
  token,
  workspaceSlug,
  deps = SYS_PERF_PARTS_CATALOG_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  deps?: SysPerfPartsCatalogLoaderDeps;
}): Promise<SysPerfPartsCatalogItem[]> {
  const response = await deps.getPartsCatalog(token, workspaceSlug);
  return response.data;
}

export async function saveSysPerfPartsCatalogItem({
  token,
  workspaceSlug,
  draft,
  deps = SYS_PERF_PARTS_CATALOG_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  draft: SysPerfPartsCatalogDraft;
  deps?: SysPerfPartsCatalogLoaderDeps;
}): ReturnType<typeof sysPerfSavePartsCatalog> {
  return deps.savePartsCatalog(
    token,
    workspaceSlug,
    buildSysPerfPartsCatalogSavePayload(draft),
  );
}

export async function deleteSysPerfPartsCatalogItem({
  token,
  workspaceSlug,
  id,
  deps = SYS_PERF_PARTS_CATALOG_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  id: number;
  deps?: SysPerfPartsCatalogLoaderDeps;
}): ReturnType<typeof sysPerfDeletePartsCatalog> {
  return deps.deletePartsCatalog(token, workspaceSlug, id);
}
