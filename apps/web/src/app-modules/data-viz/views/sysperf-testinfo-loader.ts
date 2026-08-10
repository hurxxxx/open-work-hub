import {
  sysPerfGetPartsCatalog,
  sysPerfSaveTestInfo,
} from '../api/dataviz-api';
import { rebuildPartCatalog, type PartCatalogTree } from './sysperf-parts';
import {
  buildSysPerfTestInfoItems,
  type CommonInfo,
  type FileInfo,
} from './sysperf-testinfo';
import type { UsableSysPerfUploadedFile } from './sysperf-files';

export interface SysPerfTestInfoLoaderDeps {
  getPartsCatalog: typeof sysPerfGetPartsCatalog;
  saveTestInfo: typeof sysPerfSaveTestInfo;
}

export const SYS_PERF_TESTINFO_LOADER_DEPS: SysPerfTestInfoLoaderDeps = {
  getPartsCatalog: sysPerfGetPartsCatalog,
  saveTestInfo: sysPerfSaveTestInfo,
};

export async function loadSysPerfTestInfoPartsCatalog({
  token,
  workspaceSlug,
  deps = SYS_PERF_TESTINFO_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  deps?: SysPerfTestInfoLoaderDeps;
}): Promise<PartCatalogTree> {
  const response = await deps
    .getPartsCatalog(token, workspaceSlug)
    .catch(() => ({ data: [] }));
  return rebuildPartCatalog(response.data);
}

export async function saveSysPerfTestInfo({
  token,
  workspaceSlug,
  files,
  common,
  perFile,
  deps = SYS_PERF_TESTINFO_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  files: UsableSysPerfUploadedFile[];
  common: CommonInfo;
  perFile: Record<number, FileInfo>;
  deps?: SysPerfTestInfoLoaderDeps;
}): ReturnType<typeof sysPerfSaveTestInfo> {
  return deps.saveTestInfo(
    token,
    workspaceSlug,
    buildSysPerfTestInfoItems({
      files,
      common,
      perFile,
    }),
  );
}
