import {
  createSysPerfGraphDefaultAxisSetting,
  type SysPerfGraphAxisSetting,
  type SysPerfGraphDataCache,
  type SysPerfGraphMissingItem,
  type SysPerfGraphSeries,
} from './sysperf-graph';

export interface SysPerfGraphFileRef {
  file_id: number;
}

export interface SysPerfGraphErrorSummary {
  allError: boolean;
  firstError: string | undefined;
}

export interface SysPerfGraphMissingGroup {
  fileIndex: number;
  items: string[];
}

export interface SysPerfGraphAxisState {
  axisX: SysPerfGraphAxisSetting;
  axisY: Record<number, SysPerfGraphAxisSetting>;
  appliedX: SysPerfGraphAxisSetting;
  appliedY: Record<number, SysPerfGraphAxisSetting>;
}

export function buildSysPerfGraphCheckedFiles(
  files: SysPerfGraphFileRef[],
): Record<number, boolean> {
  const checked: Record<number, boolean> = {};
  files.forEach((file) => {
    checked[file.file_id] = true;
  });
  return checked;
}

export function toggleSysPerfGraphItemSelection(
  selected: number[],
  itemNumber: number,
): number[] {
  return selected.includes(itemNumber)
    ? selected.filter((current) => current !== itemNumber)
    : [...selected, itemNumber];
}

export function toggleSysPerfGraphFileChecked(
  checked: Record<number, boolean>,
  fileId: number,
): Record<number, boolean> {
  return { ...checked, [fileId]: !checked[fileId] };
}

export function selectSysPerfGraphCheckedFiles<T extends SysPerfGraphFileRef>(
  files: T[],
  checked: Record<number, boolean>,
): T[] {
  return files.filter((file) => checked[file.file_id]);
}

export function summarizeSysPerfGraphErrors(
  files: SysPerfGraphFileRef[],
  cache: Record<number, SysPerfGraphDataCache>,
): SysPerfGraphErrorSummary {
  const firstError = files
    .map((file) => cache[file.file_id]?.error)
    .find(Boolean);
  return {
    allError:
      files.length > 0 && files.every((file) => !!cache[file.file_id]?.error),
    firstError,
  };
}

export function updateSysPerfGraphAxisField(
  axis: SysPerfGraphAxisSetting,
  field: keyof SysPerfGraphAxisSetting,
  value: string,
): SysPerfGraphAxisSetting {
  return { ...axis, [field]: value };
}

export function updateSysPerfGraphAxisMapField(
  axisMap: Record<number, SysPerfGraphAxisSetting>,
  itemNumber: number,
  field: keyof SysPerfGraphAxisSetting,
  value: string,
): Record<number, SysPerfGraphAxisSetting> {
  const current = axisMap[itemNumber] ?? createSysPerfGraphDefaultAxisSetting();
  return {
    ...axisMap,
    [itemNumber]: updateSysPerfGraphAxisField(current, field, value),
  };
}

export function createSysPerfGraphAxisState(): SysPerfGraphAxisState {
  return {
    axisX: createSysPerfGraphDefaultAxisSetting(),
    axisY: {},
    appliedX: createSysPerfGraphDefaultAxisSetting(),
    appliedY: {},
  };
}

export function groupSysPerfGraphMissingItems(
  missing: SysPerfGraphMissingItem[],
): SysPerfGraphMissingGroup[] {
  const groups = new Map<number, string[]>();
  missing.forEach((item) => {
    const values = groups.get(item.fi) ?? [];
    values.push(`${item.nm} (n=${item.n})`);
    groups.set(item.fi, values);
  });
  return Array.from(groups, ([fileIndex, items]) => ({ fileIndex, items }));
}

export function toSysPerfGraphDataCache(payload: {
  data?: Record<string, SysPerfGraphSeries>;
  units?: Record<string, string>;
  error?: string;
}): SysPerfGraphDataCache {
  const entry: SysPerfGraphDataCache = {
    data: payload.data ?? {},
    units: payload.units ?? {},
  };
  if (payload.error) entry.error = payload.error;
  return entry;
}
