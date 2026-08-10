// 시스템 성능 자동매칭 — 원본 sys_perf.js renderMatchArea() 의 0차/1차/2차 로직을 그대로 이식.
// 표준항목(_MI) 1개당 매칭된 원본 헤더명을 돌려준다: { [item.n]: headerName }.
//
// 0차 TIME : cat_type==='TIME' → 키워드 후보 중 유효 numeric 값(numericCounts) 최다 헤더. used 면제(공유).
// 1차 정확 : hl===kw. 단독항목은 used 선점, 하위(sub)는 공유 허용.
// 2차 부분 : hl.indexOf(kw)>=0 + P/T/SC 교차차단(압력↔온도↔SC 헤더 섞임 방지).
import { stdName, type MeasureItem } from './sysperf-items';

export type SysPerfValueState =
  | ''
  | 'loading'
  | 'ok'
  | 'nodata'
  | 'qmark'
  | 'err';
export type SysPerfFidMap<T> = Record<number, Record<number, T>>;
export type SysPerfAvgMode = 'direct' | 'avg';

export interface SysPerfMatchFileRef {
  file_id: number;
}

export interface SysPerfAllRow {
  col_index: number;
  original_name: string;
  standard_name: string;
  _itemNm: string;
  _itemN: number;
}

export type SysPerfAllMap = Record<number, SysPerfAllRow[]>;

export interface SysPerfInitialMatchState {
  match: SysPerfFidMap<string>;
  checked: SysPerfFidMap<boolean>;
  valueState: SysPerfFidMap<SysPerfValueState>;
  avgMode: Record<number, SysPerfAvgMode>;
  activeFid: number | null;
}

export interface SysPerfSyncResult {
  match: SysPerfFidMap<string>;
  checked: SysPerfFidMap<boolean>;
  copied: number;
  skipped: number;
}

export interface SysPerfRerunResult {
  match: SysPerfFidMap<string>;
  checked: SysPerfFidMap<boolean>;
  added: number;
}

export type SysPerfSheetDataProbeStatus = 'ok' | 'missing' | 'error';

export interface SysPerfSheetDataProbeResult {
  valueState: SysPerfFidMap<SysPerfValueState>;
  uncheckedItemNumbers: number[];
}

export interface SysPerfAverageModeToggleResult {
  avgMode: Record<number, SysPerfAvgMode>;
  checked: SysPerfFidMap<boolean>;
}

export interface SysPerfConfirmDuplicateWarning {
  fileIndex: number;
  originalName: string;
  itemNames: string[];
}

export interface SysPerfConfirmRoomAverageWarning {
  fileIndex: number;
}

export interface SysPerfConfirmPlan {
  match: SysPerfFidMap<string>;
  checked: SysPerfFidMap<boolean>;
  all: SysPerfAllMap;
  duplicateWarnings: SysPerfConfirmDuplicateWarning[];
  roomAverageWarnings: SysPerfConfirmRoomAverageWarning[];
}

export interface SysPerfConfirmRequestFileRef extends SysPerfMatchFileRef {
  sheets?: { sheet_name?: string | null }[];
}

export interface SysPerfConfirmRequestMapping {
  original_name: string;
  standard_name: string;
  col_index: number;
}

export interface SysPerfConfirmFileRequest {
  fileId: number;
  sheetName: string;
  fileIndex: number;
  mappings: SysPerfConfirmRequestMapping[];
}

export interface SysPerfConfirmDuplicateNotice {
  file: string;
  orig: string;
  items: string;
}

export interface SysPerfConfirmWarningNotice {
  dupes: SysPerfConfirmDuplicateNotice[];
  roomWarn: string[];
}

export type SysPerfMatchRowKind = 'target' | 'calculated' | 'match';

export interface SysPerfMatchFileCellView {
  fileId: number;
  visible: boolean;
  mode: SysPerfAvgMode;
  averageDisabled: boolean;
  currentMatch: string;
  checked: boolean;
  valueState: SysPerfValueState;
}

export interface SysPerfMatchRowView {
  item: MeasureItem;
  category: string;
  showCategory: boolean;
  categoryRowSpan: number;
  depth: number;
  kind: SysPerfMatchRowKind;
  success: boolean;
  avgGroup: string | undefined;
  fileCells: SysPerfMatchFileCellView[];
}

export function computeAutoMap(
  items: MeasureItem[],
  headers: string[],
  numericCounts: Record<string, number>,
): Record<number, string> {
  const map: Record<number, string> = {};
  const used: Record<number, boolean> = {}; // 헤더 인덱스 i 기준 선점 표시

  // 0차: TIME — 이름 매칭되는 후보 중 유효값 최다 헤더 선택 (used 표시 안 함)
  items.forEach((item) => {
    if (item.cat_type !== 'TIME' || !item.kw || !item.kw.length) return;
    let bestHdr: string | null = null;
    let bestCnt = -1;
    for (let i = 0; i < headers.length; i++) {
      const hl = headers[i].toLowerCase().trim();
      let matched = false;
      for (let k = 0; k < item.kw.length; k++) {
        const kl = item.kw[k].toLowerCase();
        if (hl === kl || hl.indexOf(kl) >= 0 || kl.indexOf(hl) >= 0) {
          matched = true;
          break;
        }
      }
      if (!matched) continue;
      let cnt = numericCounts[headers[i]];
      if (cnt === undefined) cnt = 0;
      if (cnt > bestCnt) {
        bestCnt = cnt;
        bestHdr = headers[i];
      }
    }
    if (bestHdr) map[item.n] = bestHdr; // used 표시 안함 — 다른 항목이 재사용 가능
  });

  // 1차: 정확히 일치 (상위 단독 항목 우선 선점)
  items.forEach((item) => {
    if (item.cat_type === 'TIME') return;
    if (!item.kw || !item.kw.length) return;
    const allowShare = !!item.sub; // 하위 항목은 공유 허용
    for (let i = 0; i < headers.length; i++) {
      if (used[i] && !allowShare) continue;
      const hl = headers[i].toLowerCase().trim();
      for (let k = 0; k < item.kw.length; k++) {
        if (hl === item.kw[k].toLowerCase()) {
          map[item.n] = headers[i];
          if (!allowShare) used[i] = true;
          break;
        }
      }
      if (map[item.n]) break;
    }
  });

  // 2차: 부분 일치 (압력P/온도T/SC/SH 교차 차단)
  items.forEach((item) => {
    if (item.cat_type === 'TIME') return;
    if (map[item.n]) return;
    if (!item.kw || !item.kw.length) return;
    const allowShare = !!item.sub;
    const isSC = item.nm.indexOf('S.C') >= 0 || item.nm.indexOf('S.H') >= 0;
    const isP = item.cat_type === 'P';
    const isT = item.cat_type === 'T';
    for (let i = 0; i < headers.length; i++) {
      if (used[i] && !allowShare) continue;
      const hl = headers[i].toLowerCase().trim();
      const hdrIsSC =
        hl.indexOf('sc ') === 0 ||
        hl.indexOf('sh ') === 0 ||
        hl.indexOf('sc(') >= 0 ||
        hl.indexOf('sh(') >= 0;
      if (!isSC && hdrIsSC) continue;
      if (isSC && !hdrIsSC) continue;
      if (isP && /^t[a-z]/i.test(hl) && !/press/i.test(hl)) continue;
      if (isT && /^p[a-z]/i.test(hl) && !/temp/i.test(hl)) continue;
      for (let k = 0; k < item.kw.length; k++) {
        if (hl.indexOf(item.kw[k].toLowerCase()) >= 0) {
          map[item.n] = headers[i];
          if (!allowShare) used[i] = true;
          break;
        }
      }
      if (map[item.n]) break;
    }
  });

  return map;
}

function cloneFidMap<T>(source: SysPerfFidMap<T>): SysPerfFidMap<T> {
  const out: SysPerfFidMap<T> = {};
  Object.keys(source).forEach((fidStr) => {
    const fid = Number(fidStr);
    out[fid] = { ...(source[fid] || {}) };
  });
  return out;
}

export function collectSysPerfSubGroups(
  items: MeasureItem[],
  group: string,
): string[] {
  let result = [group];
  items.forEach((item) => {
    if (item.sub === group && item.avg && item.grp) {
      result = result.concat(collectSysPerfSubGroups(items, item.grp));
    }
  });
  return result;
}

export function depthOfSysPerfItem(
  items: MeasureItem[],
  item: MeasureItem,
): number {
  let depth = 0;
  let current: MeasureItem | undefined = item;
  while (current && current.sub) {
    const subGroup: string = current.sub;
    const parent: MeasureItem | undefined = items.find(
      (candidate) => candidate.grp === subGroup,
    );
    if (!parent) break;
    depth++;
    current = parent;
  }
  return depth;
}

export function buildSysPerfItemCategoryMap(
  items: MeasureItem[],
): Record<number, string> {
  const out: Record<number, string> = {};
  let current = '';
  for (const item of items) {
    if (item.cs) current = item.c || '';
    out[item.n] = current;
  }
  return out;
}

export function collectHiddenSysPerfSubGroups(
  items: MeasureItem[],
  collapsedGroups: Set<string>,
): Set<string> {
  const hidden = new Set<string>();
  collapsedGroups.forEach((group) => {
    collectSysPerfSubGroups(items, group).forEach((subGroup) =>
      hidden.add(subGroup),
    );
  });
  return hidden;
}

export function isSysPerfItemHidden(
  item: MeasureItem,
  hiddenSubGroups: Set<string>,
): boolean {
  return !!item.sub && hiddenSubGroups.has(item.sub);
}

export function countVisibleSysPerfCategories(
  items: MeasureItem[],
  hiddenSubGroups: Set<string>,
  itemCategories: Record<number, string>,
): Record<string, number> {
  const out: Record<string, number> = {};
  items.forEach((item) => {
    if (isSysPerfItemHidden(item, hiddenSubGroups)) return;
    const category = itemCategories[item.n] || '';
    out[category] = (out[category] || 0) + 1;
  });
  return out;
}

export function buildInitialSysPerfMatchState({
  items,
  files,
  headersByFileId,
  numericCountsByFileId,
}: {
  items: MeasureItem[];
  files: SysPerfMatchFileRef[];
  headersByFileId: Record<number, string[]>;
  numericCountsByFileId: Record<number, Record<string, number>>;
}): SysPerfInitialMatchState {
  const match: SysPerfFidMap<string> = {};
  const checked: SysPerfFidMap<boolean> = {};
  const valueState: SysPerfFidMap<SysPerfValueState> = {};

  files.forEach((file) => {
    const fid = file.file_id;
    const auto = computeAutoMap(
      items,
      headersByFileId[fid] ?? [],
      numericCountsByFileId[fid] ?? {},
    );
    match[fid] = {};
    checked[fid] = {};
    valueState[fid] = {};
    items.forEach((item) => {
      const hit = auto[item.n] || '';
      match[fid][item.n] = hit;
      checked[fid][item.n] = !!hit;
      valueState[fid][item.n] = hit ? 'loading' : '';
    });
  });

  const avgMode: Record<number, SysPerfAvgMode> = {};
  items.forEach((item) => {
    if (!item.avg) return;
    const hasAuto = files.some((file) => !!match[file.file_id]?.[item.n]);
    avgMode[item.n] = hasAuto ? 'direct' : 'avg';
    if (avgMode[item.n] === 'avg') {
      files.forEach((file) => {
        checked[file.file_id][item.n] = false;
      });
    }
  });

  return {
    match,
    checked,
    valueState,
    avgMode,
    activeFid: files[0]?.file_id ?? null,
  };
}

export function applySysPerfSheetDataProbe({
  items,
  fileId,
  match,
  valueState,
  data,
  status,
}: {
  items: MeasureItem[];
  fileId: number;
  match: SysPerfFidMap<string>;
  valueState: SysPerfFidMap<SysPerfValueState>;
  data?: Record<string, unknown> | null;
  status: SysPerfSheetDataProbeStatus;
}): SysPerfSheetDataProbeResult {
  const nextValueState: SysPerfFidMap<SysPerfValueState> = {
    ...valueState,
    [fileId]: { ...(valueState[fileId] || {}) },
  };
  const uncheckedItemNumbers: number[] = [];

  if (status === 'missing') {
    items.forEach((item) => {
      if (match[fileId]?.[item.n]) nextValueState[fileId][item.n] = 'qmark';
    });
    return { valueState: nextValueState, uncheckedItemNumbers };
  }

  if (status === 'error') {
    items.forEach((item) => {
      if (match[fileId]?.[item.n]) nextValueState[fileId][item.n] = 'err';
    });
    return { valueState: nextValueState, uncheckedItemNumbers };
  }

  const keyMap: Record<string, string> = {};
  Object.keys(data ?? {}).forEach((key) => {
    keyMap[key.toLowerCase().trim()] = key;
  });

  items.forEach((item) => {
    const matched = match[fileId]?.[item.n];
    if (!matched) {
      nextValueState[fileId][item.n] = '';
      return;
    }

    let columnData = data?.[matched];
    if (columnData === undefined) {
      const alternativeKey = keyMap[matched.toLowerCase().trim()];
      if (alternativeKey) columnData = data?.[alternativeKey];
    }

    const hasData =
      Array.isArray(columnData) &&
      columnData.some(
        (value) =>
          value !== null && value !== undefined && !isNaN(value as number),
      );

    if (hasData) {
      nextValueState[fileId][item.n] = 'ok';
      return;
    }

    nextValueState[fileId][item.n] = 'nodata';
    uncheckedItemNumbers.push(item.n);
  });

  return { valueState: nextValueState, uncheckedItemNumbers };
}

export function clearSysPerfCheckedItems({
  checked,
  fileId,
  itemNumbers,
}: {
  checked: SysPerfFidMap<boolean>;
  fileId: number;
  itemNumbers: number[];
}): SysPerfFidMap<boolean> {
  if (!itemNumbers.length) return checked;
  const nextChecked: SysPerfFidMap<boolean> = {
    ...checked,
    [fileId]: { ...(checked[fileId] || {}) },
  };
  itemNumbers.forEach((itemN) => {
    nextChecked[fileId][itemN] = false;
  });
  return nextChecked;
}

export function toggleSysPerfAverageMode({
  files,
  itemN,
  avgMode,
  checked,
  match,
}: {
  files: SysPerfMatchFileRef[];
  itemN: number;
  avgMode: Record<number, SysPerfAvgMode>;
  checked: SysPerfFidMap<boolean>;
  match: SysPerfFidMap<string>;
}): SysPerfAverageModeToggleResult {
  const currentMode = avgMode[itemN] || 'direct';
  const nextMode: SysPerfAvgMode = currentMode === 'direct' ? 'avg' : 'direct';
  const nextChecked = cloneFidMap(checked);

  files.forEach((file) => {
    const fid = file.file_id;
    nextChecked[fid] = { ...(nextChecked[fid] || {}) };
    nextChecked[fid][itemN] =
      nextMode === 'avg' ? false : !!match[fid]?.[itemN];
  });

  return {
    avgMode: { ...avgMode, [itemN]: nextMode },
    checked: nextChecked,
  };
}

export function buildSysPerfMatchRows({
  items,
  files,
  activeFileId,
  hiddenSubGroups,
  itemCategories,
  match,
  checked,
  valueState,
  avgMode,
}: {
  items: MeasureItem[];
  files: SysPerfMatchFileRef[];
  activeFileId: number | null;
  hiddenSubGroups: Set<string>;
  itemCategories: Record<number, string>;
  match: SysPerfFidMap<string>;
  checked: SysPerfFidMap<boolean>;
  valueState: SysPerfFidMap<SysPerfValueState>;
  avgMode: Record<number, SysPerfAvgMode>;
}): SysPerfMatchRowView[] {
  const categoryCounts = countVisibleSysPerfCategories(
    items,
    hiddenSubGroups,
    itemCategories,
  );
  const fileIds = files.map((file) => file.file_id);

  return items
    .filter((item) => !isSysPerfItemHidden(item, hiddenSubGroups))
    .map((item) => {
      const kind: SysPerfMatchRowKind =
        item.n === 1 ? 'target' : item.calc ? 'calculated' : 'match';
      const category = itemCategories[item.n] || '';
      const mode = item.avg ? avgMode[item.n] || 'direct' : 'direct';
      const averageDisabled = !!item.avg && mode === 'avg';

      return {
        item,
        category,
        showCategory: !!item.cs,
        categoryRowSpan: Math.max(1, categoryCounts[category] || 1),
        depth: depthOfSysPerfItem(items, item),
        kind,
        success: isSysPerfMatchSuccessful({
          item,
          items,
          checked,
          avgMode,
          fileIds,
        }),
        avgGroup: item.avg ? item.grp : undefined,
        fileCells: files.map((file) => {
          const fid = file.file_id;
          return {
            fileId: fid,
            visible: files.length < 2 || activeFileId === fid,
            mode,
            averageDisabled,
            currentMatch: match[fid]?.[item.n] || '',
            checked: !!checked[fid]?.[item.n],
            valueState: valueState[fid]?.[item.n] || '',
          };
        }),
      };
    });
}

export function isSysPerfMatchSuccessful({
  item,
  items,
  checked,
  avgMode,
  fileIds,
}: {
  item: MeasureItem;
  items: MeasureItem[];
  checked: SysPerfFidMap<boolean>;
  avgMode: Record<number, SysPerfAvgMode>;
  fileIds: number[];
}): boolean {
  const anyChecked = (itemN: number) =>
    fileIds.some((fileId) => !!checked[fileId]?.[itemN]);

  if (item.calc) return true;
  if (item.n === 64) {
    return (
      (anyChecked(65) && anyChecked(70)) || (anyChecked(75) && anyChecked(80))
    );
  }
  if (item.avg && item.grp) {
    const mode = avgMode[item.n] || 'direct';
    if (mode === 'direct') return anyChecked(item.n);
    return items
      .filter((candidate) => candidate.sub === item.grp)
      .some((subItem) => anyChecked(subItem.n));
  }
  return anyChecked(item.n);
}

export function applySysPerfRerunAutoMatch({
  items,
  files,
  headersByFileId,
  numericCountsByFileId,
  match,
  checked,
}: {
  items: MeasureItem[];
  files: SysPerfMatchFileRef[];
  headersByFileId: Record<number, string[]>;
  numericCountsByFileId: Record<number, Record<string, number>>;
  match: SysPerfFidMap<string>;
  checked: SysPerfFidMap<boolean>;
}): SysPerfRerunResult {
  const nextMatch = cloneFidMap(match);
  const nextChecked = cloneFidMap(checked);
  let added = 0;

  files.forEach((file) => {
    const fid = file.file_id;
    nextMatch[fid] = { ...(nextMatch[fid] || {}) };
    nextChecked[fid] = { ...(nextChecked[fid] || {}) };
    const auto = computeAutoMap(
      items,
      headersByFileId[fid] ?? [],
      numericCountsByFileId[fid] ?? {},
    );
    items.forEach((item) => {
      if (item.calc) return;
      if (nextMatch[fid][item.n]) return;
      if (!auto[item.n]) return;
      nextMatch[fid][item.n] = auto[item.n];
      nextChecked[fid][item.n] = true;
      added++;
    });
  });

  return { match: nextMatch, checked: nextChecked, added };
}

export function syncSysPerfMatchesFromFirstFile({
  items,
  files,
  headersByFileId,
  match,
  checked,
}: {
  items: MeasureItem[];
  files: SysPerfMatchFileRef[];
  headersByFileId: Record<number, string[]>;
  match: SysPerfFidMap<string>;
  checked: SysPerfFidMap<boolean>;
}): SysPerfSyncResult {
  const firstFile = files[0];
  const nextMatch = cloneFidMap(match);
  const nextChecked = cloneFidMap(checked);
  let copied = 0;
  let skipped = 0;

  if (!firstFile || files.length < 2) {
    return { match: nextMatch, checked: nextChecked, copied, skipped };
  }

  const sourceFileId = firstFile.file_id;
  items.forEach((item) => {
    const source = nextMatch[sourceFileId]?.[item.n] || '';
    if (!source || !nextChecked[sourceFileId]?.[item.n]) return;
    files.forEach((file, fileIndex) => {
      if (fileIndex === 0) return;
      const fid = file.file_id;
      nextMatch[fid] = { ...(nextMatch[fid] || {}) };
      nextChecked[fid] = { ...(nextChecked[fid] || {}) };
      if ((headersByFileId[fid] ?? []).indexOf(source) < 0) {
        skipped++;
        return;
      }
      nextMatch[fid][item.n] = source;
      nextChecked[fid][item.n] = true;
      copied++;
    });
  });

  return { match: nextMatch, checked: nextChecked, copied, skipped };
}

export function buildSysPerfConfirmPlan({
  items,
  files,
  headersByFileId,
  match,
  checked,
}: {
  items: MeasureItem[];
  files: SysPerfMatchFileRef[];
  headersByFileId: Record<number, string[]>;
  match: SysPerfFidMap<string>;
  checked: SysPerfFidMap<boolean>;
}): SysPerfConfirmPlan {
  const syncResult = syncSysPerfMatchesFromFirstFile({
    items,
    files,
    headersByFileId,
    match,
    checked,
  });
  const all: SysPerfAllMap = {};

  items.forEach((item) => {
    files.forEach((file) => {
      const fid = file.file_id;
      if (!syncResult.checked[fid]?.[item.n]) return;
      const originalName = syncResult.match[fid]?.[item.n] || '';
      if (!originalName) return;
      (all[fid] = all[fid] || []).push({
        col_index: (headersByFileId[fid] ?? []).indexOf(originalName),
        original_name: originalName,
        standard_name: stdName(item),
        _itemNm: item.nm,
        _itemN: item.n,
      });
    });
  });

  const duplicateWarnings: SysPerfConfirmDuplicateWarning[] = [];
  Object.keys(all).forEach((fidStr) => {
    const fid = Number(fidStr);
    const fileIndex = files.findIndex((file) => file.file_id === fid);
    const originalMap: Record<string, string[]> = {};
    all[fid].forEach((mapping) => {
      (originalMap[mapping.original_name] =
        originalMap[mapping.original_name] || []).push(mapping._itemNm);
    });
    Object.keys(originalMap).forEach((originalName) => {
      if (originalMap[originalName].length <= 1) return;
      duplicateWarnings.push({
        fileIndex,
        originalName,
        itemNames: originalMap[originalName],
      });
    });
  });

  const roomAverageWarnings: SysPerfConfirmRoomAverageWarning[] = [];
  Object.keys(all).forEach((fidStr) => {
    const fid = Number(fidStr);
    const fileIndex = files.findIndex((file) => file.file_id === fid);
    const has = (itemN: number) =>
      all[fid].some((mapping) => mapping._itemN === itemN);
    if (has(65) && has(70) && has(75) && has(80)) {
      roomAverageWarnings.push({ fileIndex });
    }
  });

  return {
    match: syncResult.match,
    checked: syncResult.checked,
    all,
    duplicateWarnings,
    roomAverageWarnings,
  };
}

export function buildSysPerfConfirmRequests({
  files,
  all,
}: {
  files: SysPerfConfirmRequestFileRef[];
  all: SysPerfAllMap;
}): SysPerfConfirmFileRequest[] {
  return files
    .map((file, fileIndex) => {
      const mappings = (all[file.file_id] || []).map((mapping) => ({
        original_name: mapping.original_name,
        standard_name: mapping.standard_name,
        col_index: mapping.col_index,
      }));
      return {
        fileId: file.file_id,
        sheetName: file.sheets?.[0]?.sheet_name ?? '',
        fileIndex,
        mappings,
      };
    })
    .filter((request) => request.mappings.length > 0);
}

export function buildSysPerfConfirmWarningNotice({
  plan,
  fileLabel,
  roomAverageWarning,
}: {
  plan: Pick<SysPerfConfirmPlan, 'duplicateWarnings' | 'roomAverageWarnings'>;
  fileLabel: (warning: { fileIndex: number; fileNumber: number }) => string;
  roomAverageWarning: (warning: {
    fileIndex: number;
    fileNumber: number;
  }) => string;
}): SysPerfConfirmWarningNotice {
  return {
    dupes: plan.duplicateWarnings.map((warning) => ({
      file: fileLabel({
        fileIndex: warning.fileIndex,
        fileNumber: warning.fileIndex + 1,
      }),
      orig: warning.originalName,
      items: warning.itemNames.join(', '),
    })),
    roomWarn: plan.roomAverageWarnings.map((warning) =>
      roomAverageWarning({
        fileIndex: warning.fileIndex,
        fileNumber: warning.fileIndex + 1,
      }),
    ),
  };
}
