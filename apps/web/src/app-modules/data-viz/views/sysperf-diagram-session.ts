import {
  SYS_PERF_TS_AXIS_DEFAULTS,
  normalizeSysPerfTsAxis,
  type SysPerfTsAxis,
} from './sysperf-diagram';

export interface SysPerfDiagramStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export const SYS_PERF_DIAGRAM_DEFAULT_TIME = '30';

const PH_BULK_TIME_KEY = 'sp_ph_bulk_time';
const TS_AXIS_KEY_PREFIX = 'sp_ts_';
const TS_AXIS_KEYS = Object.keys(
  SYS_PERF_TS_AXIS_DEFAULTS,
) as (keyof SysPerfTsAxis)[];
export type SysPerfTsAxisKey = (typeof TS_AXIS_KEYS)[number];

export function getSysPerfDiagramBrowserStorage(): SysPerfDiagramStorage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function sysPerfDiagramTimeKey(fileIndex: number): string {
  return `sp_ph_time_fidx_${fileIndex}`;
}

function parseStoredNumber(value: string | null): number | null {
  if (value == null || value === '') return null;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function readStoredNumber(
  storage: SysPerfDiagramStorage | null | undefined,
  key: string,
): number | null {
  if (!storage) return null;
  try {
    return parseStoredNumber(storage.getItem(key));
  } catch {
    return null;
  }
}

function writeStoredNumber(
  storage: SysPerfDiagramStorage | null | undefined,
  key: string,
  value: number,
): boolean {
  if (!storage || !Number.isFinite(value)) return false;
  try {
    storage.setItem(key, String(value));
    return true;
  } catch {
    return false;
  }
}

export function loadSysPerfDiagramTimes({
  storage,
  fileCount,
  fallback = SYS_PERF_DIAGRAM_DEFAULT_TIME,
}: {
  storage: SysPerfDiagramStorage | null | undefined;
  fileCount: number;
  fallback?: string;
}): Record<number, string> {
  const times: Record<number, string> = {};
  for (let fileIndex = 0; fileIndex < fileCount; fileIndex += 1) {
    const stored = readStoredNumber(storage, sysPerfDiagramTimeKey(fileIndex));
    times[fileIndex] = stored == null ? fallback : String(stored);
  }
  return times;
}

export function saveSysPerfDiagramTime(
  storage: SysPerfDiagramStorage | null | undefined,
  fileIndex: number,
  value: string | number,
): boolean {
  const parsed = typeof value === 'number' ? value : Number.parseFloat(value);
  return writeStoredNumber(storage, sysPerfDiagramTimeKey(fileIndex), parsed);
}

export function loadSysPerfDiagramBulkTime(
  storage: SysPerfDiagramStorage | null | undefined,
  fallback = SYS_PERF_DIAGRAM_DEFAULT_TIME,
): string {
  const stored = readStoredNumber(storage, PH_BULK_TIME_KEY);
  return stored == null ? fallback : String(stored);
}

export function buildSysPerfDiagramBulkTimes({
  storage,
  fileCount,
  value,
}: {
  storage: SysPerfDiagramStorage | null | undefined;
  fileCount: number;
  value: string | number;
}): Record<number, string> | null {
  const parsed = typeof value === 'number' ? value : Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed < 0) return null;

  const times: Record<number, string> = {};
  for (let fileIndex = 0; fileIndex < fileCount; fileIndex += 1) {
    times[fileIndex] = String(parsed);
    writeStoredNumber(storage, sysPerfDiagramTimeKey(fileIndex), parsed);
  }
  writeStoredNumber(storage, PH_BULK_TIME_KEY, parsed);
  return times;
}

export function loadSysPerfDiagramTsAxis(
  storage: SysPerfDiagramStorage | null | undefined,
): SysPerfTsAxis {
  const axis = { ...SYS_PERF_TS_AXIS_DEFAULTS };
  TS_AXIS_KEYS.forEach((key) => {
    const stored = readStoredNumber(storage, `${TS_AXIS_KEY_PREFIX}${key}`);
    if (stored != null) axis[key] = stored;
  });
  return normalizeSysPerfTsAxis(axis);
}

export function saveSysPerfDiagramTsAxis(
  storage: SysPerfDiagramStorage | null | undefined,
  axis: SysPerfTsAxis,
): void {
  TS_AXIS_KEYS.forEach((key) => {
    writeStoredNumber(storage, `${TS_AXIS_KEY_PREFIX}${key}`, axis[key]);
  });
}

export function canApplySysPerfDiagramTsAxis(axis: SysPerfTsAxis): boolean {
  return (
    TS_AXIS_KEYS.every((key) => Number.isFinite(axis[key])) &&
    axis.xMin < axis.xMax &&
    axis.yMin < axis.yMax &&
    axis.xTick > 0 &&
    axis.yTick > 0
  );
}

export function updateSysPerfDiagramTsAxisDraft({
  axis,
  key,
  value,
}: {
  axis: SysPerfTsAxis;
  key: SysPerfTsAxisKey;
  value: string;
}): SysPerfTsAxis {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) return axis;
  return { ...axis, [key]: parsed };
}
