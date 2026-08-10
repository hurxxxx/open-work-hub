import {
  sysPerfDeleteCarModel,
  sysPerfGetCarModels,
  sysPerfSaveCarModel,
  type SysPerfCarModel,
} from '../api/dataviz-api';
import {
  buildSysPerfBaseCarSavePayload,
  type SysPerfBaseCarDraft,
} from './sysperf-base-cars';

export type { SysPerfCarModel };

export interface SysPerfBaseCarsLoaderDeps {
  getCarModels: typeof sysPerfGetCarModels;
  saveCarModel: typeof sysPerfSaveCarModel;
  deleteCarModel: typeof sysPerfDeleteCarModel;
}

export const SYS_PERF_BASE_CARS_LOADER_DEPS: SysPerfBaseCarsLoaderDeps = {
  getCarModels: sysPerfGetCarModels,
  saveCarModel: sysPerfSaveCarModel,
  deleteCarModel: sysPerfDeleteCarModel,
};

export function isSysPerfBaseCarDraftSubmittable(
  draft: SysPerfBaseCarDraft,
): boolean {
  return buildSysPerfBaseCarSavePayload(draft) !== null;
}

export async function loadSysPerfBaseCarModels({
  token,
  workspaceSlug,
  deps = SYS_PERF_BASE_CARS_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  deps?: SysPerfBaseCarsLoaderDeps;
}): Promise<SysPerfCarModel[]> {
  const response = await deps.getCarModels(token, workspaceSlug, {});
  return response.data;
}

export async function saveSysPerfBaseCarModel({
  token,
  workspaceSlug,
  draft,
  deps = SYS_PERF_BASE_CARS_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  draft: SysPerfBaseCarDraft;
  deps?: SysPerfBaseCarsLoaderDeps;
}): Promise<Awaited<ReturnType<typeof sysPerfSaveCarModel>> | null> {
  const payload = buildSysPerfBaseCarSavePayload(draft);
  if (!payload) return Promise.resolve(null);
  return deps.saveCarModel(token, workspaceSlug, payload);
}

export async function deleteSysPerfBaseCarModel({
  token,
  workspaceSlug,
  modelId,
  deps = SYS_PERF_BASE_CARS_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  modelId: number;
  deps?: SysPerfBaseCarsLoaderDeps;
}): ReturnType<typeof sysPerfDeleteCarModel> {
  return deps.deleteCarModel(token, workspaceSlug, modelId);
}
