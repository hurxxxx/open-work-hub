import { runRequestsWithConcurrency } from '@/src/platform/network/request-concurrency';

import {
  sysPerfCycleData,
  sysPerfGetRefrigerants,
  sysPerfGetRefrigerantProps,
  sysPerfPhDiagram,
  sysPerfTsDiagram,
  type SysPerfCycleData,
  type SysPerfPhDiagram,
  type SysPerfRefrigerantPropRow,
  type SysPerfTsDiagram,
} from '../api/dataviz-api';
import type { UsableSysPerfUploadedFile } from './sysperf-files';
import { SYS_PERF_DIAGRAM_DEFAULT_TIME } from './sysperf-diagram-session';
import type { SysPerfDiagramCycleCacheEntry } from './sysperf-diagram';

const SYS_PERF_DIAGRAM_CYCLE_LOAD_CONCURRENCY = 3;

export interface SysPerfDiagramRefrigerantRef {
  id: number;
  name: string;
}

export interface SysPerfDiagramParsedTime {
  requestTime: number | null;
  cacheTime: number;
}

export interface SysPerfDiagramCycleResult {
  fileIndex: number;
  requestedTime: number;
  data: SysPerfCycleData;
}

export interface SysPerfDiagramRunResult {
  props: SysPerfRefrigerantPropRow[];
  cache: Record<number, SysPerfDiagramCycleCacheEntry>;
  ph: SysPerfPhDiagram;
  ts: SysPerfTsDiagram;
  cycleError: string | undefined;
}

export interface SysPerfDiagramLoaderDeps {
  getRefrigerants: typeof sysPerfGetRefrigerants;
  getRefrigerantProps: typeof sysPerfGetRefrigerantProps;
  getCycleData: typeof sysPerfCycleData;
  getPhDiagram: typeof sysPerfPhDiagram;
  getTsDiagram: typeof sysPerfTsDiagram;
}

export const SYS_PERF_DIAGRAM_LOADER_DEPS: SysPerfDiagramLoaderDeps = {
  getRefrigerants: sysPerfGetRefrigerants,
  getRefrigerantProps: sysPerfGetRefrigerantProps,
  getCycleData: sysPerfCycleData,
  getPhDiagram: sysPerfPhDiagram,
  getTsDiagram: sysPerfTsDiagram,
};

export function findSysPerfRefrigerantId(
  refrigerants: SysPerfDiagramRefrigerantRef[],
  name: string,
): number | null {
  return (
    refrigerants.find(
      (refrigerant) => refrigerant.name === name && refrigerant.id,
    )?.id ?? null
  );
}

export async function loadSysPerfDiagramRefrigerants({
  token,
  workspaceSlug,
  deps = SYS_PERF_DIAGRAM_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  deps?: SysPerfDiagramLoaderDeps;
}): Promise<SysPerfDiagramRefrigerantRef[]> {
  const response = await deps
    .getRefrigerants(token, workspaceSlug)
    .catch(() => null);
  return (response?.data || [])
    .filter((refrigerant) => refrigerant.name)
    .map((refrigerant) => ({
      id: refrigerant.id,
      name: refrigerant.name,
    }));
}

export function parseSysPerfDiagramTime(
  value: string | undefined,
  defaultTime = Number(SYS_PERF_DIAGRAM_DEFAULT_TIME),
): SysPerfDiagramParsedTime {
  const parsed = Number.parseFloat(value ?? String(defaultTime));
  if (Number.isNaN(parsed)) {
    return { requestTime: null, cacheTime: defaultTime };
  }
  return { requestTime: parsed, cacheTime: parsed };
}

export function buildSysPerfDiagramCycleCache(
  results: SysPerfDiagramCycleResult[],
): Record<number, SysPerfDiagramCycleCacheEntry> {
  const cache: Record<number, SysPerfDiagramCycleCacheEntry> = {};
  results.forEach((result) => {
    if (result.data.error) return;
    cache[result.fileIndex] = {
      ...result.data,
      time: result.data.time ?? result.requestedTime,
    };
  });
  return cache;
}

export function findBlockingSysPerfDiagramCycleError(
  results: SysPerfDiagramCycleResult[],
): string | undefined {
  const errorResult = results.find((result) => result.data.error);
  if (!errorResult) return undefined;
  const hasSuccess = results.some((result) => !result.data.error);
  if (hasSuccess) return undefined;
  return errorResult.data.error || '';
}

export function buildFailedSysPerfDiagramCycleData({
  error,
  time,
}: {
  error: unknown;
  time: number;
}): SysPerfCycleData {
  return {
    status: 'error',
    time,
    row_index: -1,
    cycle: {},
    enthalpy: {},
    entropy: {},
    sh_sc: {},
    mappings: {},
    isenthalpic_notes: [],
    warnings: {},
    error: error instanceof Error ? error.message : '',
  };
}

export async function loadSysPerfDiagramRun({
  token,
  workspaceSlug,
  files,
  times,
  refrigerant,
  refrigerants,
  deps = SYS_PERF_DIAGRAM_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  files: UsableSysPerfUploadedFile[];
  times: Record<number, string>;
  refrigerant: string;
  refrigerants: SysPerfDiagramRefrigerantRef[];
  deps?: SysPerfDiagramLoaderDeps;
}): Promise<SysPerfDiagramRunResult> {
  const refrigerantId = findSysPerfRefrigerantId(refrigerants, refrigerant);
  const propsPromise = refrigerantId
    ? deps
        .getRefrigerantProps(token, workspaceSlug, refrigerantId)
        .then((response) => response.data || [])
        .catch(() => [])
    : Promise.resolve<SysPerfRefrigerantPropRow[]>([]);
  const cyclePromise = runRequestsWithConcurrency(
    files,
    SYS_PERF_DIAGRAM_CYCLE_LOAD_CONCURRENCY,
    (file, fileIndex) => {
      const parsedTime = parseSysPerfDiagramTime(times[fileIndex]);
      return deps
        .getCycleData(
          token,
          workspaceSlug,
          file.file_id,
          file.sheets[0].sheet_name,
          parsedTime.requestTime,
          refrigerant,
        )
        .then((data) => ({
          fileIndex,
          requestedTime: parsedTime.cacheTime,
          data,
        }))
        .catch((error) => ({
          fileIndex,
          requestedTime: parsedTime.cacheTime,
          data: buildFailedSysPerfDiagramCycleData({
            error,
            time: parsedTime.cacheTime,
          }),
        }));
    },
  );

  const [props, cycleResults, ph, ts] = await Promise.all([
    propsPromise,
    cyclePromise,
    deps.getPhDiagram(token, workspaceSlug, refrigerant, refrigerantId),
    deps.getTsDiagram(token, workspaceSlug, refrigerant, refrigerantId),
  ]);

  return {
    props,
    cache: buildSysPerfDiagramCycleCache(cycleResults),
    ph,
    ts,
    cycleError: findBlockingSysPerfDiagramCycleError(cycleResults),
  };
}
