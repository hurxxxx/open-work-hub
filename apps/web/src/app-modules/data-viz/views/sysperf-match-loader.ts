import {
  sysPerfConfirmMatch,
  sysPerfGetItemKeywords,
  sysPerfSheetData,
} from '../api/dataviz-api';
import type { MeasureItem } from './sysperf-items';
import {
  applySysPerfSheetDataProbe,
  clearSysPerfCheckedItems,
  type SysPerfConfirmFileRequest,
  type SysPerfFidMap,
  type SysPerfSheetDataProbeResult,
  type SysPerfSheetDataProbeStatus,
  type SysPerfValueState,
} from './sysperf-match';
import type { UsableSysPerfUploadedFile } from './sysperf-files';

export interface SysPerfMatchLoaderDeps {
  getSheetData: typeof sysPerfSheetData;
  getItemKeywords: typeof sysPerfGetItemKeywords;
  confirmMatch: typeof sysPerfConfirmMatch;
}

export const SYS_PERF_MATCH_LOADER_DEPS: SysPerfMatchLoaderDeps = {
  getSheetData: sysPerfSheetData,
  getItemKeywords: sysPerfGetItemKeywords,
  confirmMatch: sysPerfConfirmMatch,
};

export interface SysPerfMatchSheetDataProbePayload {
  fileId: number;
  data?: Record<string, unknown> | null;
  status: SysPerfSheetDataProbeStatus;
}

export interface SysPerfConfirmMatchCommitResult {
  fileIndex: number;
  count: number;
}

export interface SysPerfMatchSheetDataProbeBatchResult {
  valueState: SysPerfFidMap<SysPerfValueState>;
  uncheckedByFileId: Record<number, number[]>;
}

export interface SysPerfMatchSheetDataProbeStateResult
  extends SysPerfMatchSheetDataProbeBatchResult {
  checked: SysPerfFidMap<boolean>;
}

export function areSysPerfFidMapsEqual<T>(
  left: SysPerfFidMap<T>,
  right: SysPerfFidMap<T>,
): boolean {
  const leftFileIds = Object.keys(left);
  const rightFileIds = Object.keys(right);
  if (leftFileIds.length !== rightFileIds.length) return false;

  return leftFileIds.every((fileIdKey) => {
    if (!Object.prototype.hasOwnProperty.call(right, fileIdKey)) return false;

    const fileId = Number(fileIdKey);
    const leftItems = left[fileId] || {};
    const rightItems = right[fileId] || {};
    const leftItemKeys = Object.keys(leftItems);
    const rightItemKeys = Object.keys(rightItems);
    if (leftItemKeys.length !== rightItemKeys.length) return false;

    return leftItemKeys.every((itemKey) => {
      if (!Object.prototype.hasOwnProperty.call(rightItems, itemKey))
        return false;
      const itemN = Number(itemKey);
      return Object.is(leftItems[itemN], rightItems[itemN]);
    });
  });
}

export function parseSysPerfItemKeywordOverrides(
  rows: { item_n: number; keywords: string }[],
): Record<number, string[]> {
  const overrides: Record<number, string[]> = {};
  rows.forEach((row) => {
    overrides[row.item_n] = (row.keywords || '')
      .split(',')
      .map((keyword) => keyword.trim())
      .filter(Boolean);
  });
  return overrides;
}

export function applySysPerfItemKeywordOverrides(
  items: MeasureItem[],
  overrides: Record<number, string[]>,
): MeasureItem[] {
  return items.map((item) =>
    overrides[item.n] !== undefined ? { ...item, kw: overrides[item.n] } : item,
  );
}

export async function loadSysPerfItemKeywordOverrides({
  token,
  workspaceSlug,
  deps = SYS_PERF_MATCH_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  deps?: SysPerfMatchLoaderDeps;
}): Promise<Record<number, string[]>> {
  const response = await deps
    .getItemKeywords(token, workspaceSlug)
    .catch(() => null);
  return parseSysPerfItemKeywordOverrides(response?.data || []);
}

export async function loadSysPerfMatchSheetDataProbePayload({
  token,
  workspaceSlug,
  file,
  deps = SYS_PERF_MATCH_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  file: UsableSysPerfUploadedFile;
  deps?: SysPerfMatchLoaderDeps;
}): Promise<SysPerfMatchSheetDataProbePayload> {
  try {
    const payload = await deps.getSheetData(
      token,
      workspaceSlug,
      file.file_id,
      file.sheets[0].sheet_name ?? '',
      30,
    );
    return {
      fileId: file.file_id,
      data: payload.data,
      status: !payload.data || payload.error ? 'missing' : 'ok',
    };
  } catch {
    return {
      fileId: file.file_id,
      status: 'error',
    };
  }
}

export function applyLoadedSysPerfMatchSheetDataProbe({
  items,
  match,
  valueState,
  payload,
}: {
  items: MeasureItem[];
  match: SysPerfFidMap<string>;
  valueState: SysPerfFidMap<SysPerfValueState>;
  payload: SysPerfMatchSheetDataProbePayload;
}): SysPerfSheetDataProbeResult {
  return applySysPerfSheetDataProbe({
    items,
    fileId: payload.fileId,
    match,
    valueState,
    data: payload.data,
    status: payload.status,
  });
}

export function applyLoadedSysPerfMatchSheetDataProbes({
  items,
  match,
  valueState,
  payloads,
}: {
  items: MeasureItem[];
  match: SysPerfFidMap<string>;
  valueState: SysPerfFidMap<SysPerfValueState>;
  payloads: SysPerfMatchSheetDataProbePayload[];
}): SysPerfMatchSheetDataProbeBatchResult {
  let nextValueState = valueState;
  const uncheckedByFileId: Record<number, number[]> = {};

  payloads.forEach((payload) => {
    const result = applyLoadedSysPerfMatchSheetDataProbe({
      items,
      match,
      valueState: nextValueState,
      payload,
    });
    nextValueState = result.valueState;
    if (result.uncheckedItemNumbers.length) {
      uncheckedByFileId[payload.fileId] = result.uncheckedItemNumbers;
    }
  });

  return {
    valueState: nextValueState,
    uncheckedByFileId,
  };
}

export function applyLoadedSysPerfMatchSheetDataProbesToState({
  items,
  match,
  valueState,
  checked,
  payloads,
}: {
  items: MeasureItem[];
  match: SysPerfFidMap<string>;
  valueState: SysPerfFidMap<SysPerfValueState>;
  checked: SysPerfFidMap<boolean>;
  payloads: SysPerfMatchSheetDataProbePayload[];
}): SysPerfMatchSheetDataProbeStateResult {
  const result = applyLoadedSysPerfMatchSheetDataProbes({
    items,
    match,
    valueState,
    payloads,
  });
  let nextChecked = checked;

  Object.entries(result.uncheckedByFileId).forEach(([fileId, itemNumbers]) => {
    nextChecked = clearSysPerfCheckedItems({
      checked: nextChecked,
      fileId: Number(fileId),
      itemNumbers,
    });
  });

  return {
    valueState: result.valueState,
    checked: nextChecked,
    uncheckedByFileId: result.uncheckedByFileId,
  };
}

export async function confirmSysPerfMatchRequests({
  token,
  workspaceSlug,
  requests,
  deps = SYS_PERF_MATCH_LOADER_DEPS,
}: {
  token: string;
  workspaceSlug: string;
  requests: SysPerfConfirmFileRequest[];
  deps?: SysPerfMatchLoaderDeps;
}): Promise<SysPerfConfirmMatchCommitResult[]> {
  const results: SysPerfConfirmMatchCommitResult[] = [];
  for (const request of requests) {
    await deps.confirmMatch(
      token,
      workspaceSlug,
      request.fileId,
      request.sheetName,
      request.mappings,
    );
    results.push({
      fileIndex: request.fileIndex,
      count: request.mappings.length,
    });
  }
  return results;
}
