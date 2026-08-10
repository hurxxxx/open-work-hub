import { describe, expect, it } from 'vitest';

import { stdName, type MeasureItem } from './sysperf-items';
import {
  applySysPerfRerunAutoMatch,
  applySysPerfSheetDataProbe,
  buildSysPerfItemCategoryMap,
  buildSysPerfMatchRows,
  buildInitialSysPerfMatchState,
  buildSysPerfConfirmPlan,
  buildSysPerfConfirmRequests,
  buildSysPerfConfirmWarningNotice,
  clearSysPerfCheckedItems,
  collectHiddenSysPerfSubGroups,
  isSysPerfMatchSuccessful,
  syncSysPerfMatchesFromFirstFile,
  toggleSysPerfAverageMode,
  type SysPerfFidMap,
} from './sysperf-match';

const ITEMS: MeasureItem[] = [
  {
    n: 10,
    c: 'Air',
    nm: 'Group Avg',
    u: '',
    kw: ['GROUP AVG'],
    avg: true,
    grp: 'grp',
  },
  { n: 11, nm: 'Child A', u: '', kw: ['CHILD A'], sub: 'grp' },
  { n: 12, nm: 'Child B', u: '', kw: ['CHILD B'], sub: 'grp' },
  { n: 20, nm: 'Manual', u: '', kw: ['MANUAL'] },
  { n: 30, nm: 'Calculated', u: '', kw: [], calc: true },
  { n: 64, nm: 'Room Avg', u: '', kw: [], avg: true, grp: 'rm' },
  {
    n: 65,
    nm: 'Room A',
    u: '',
    kw: ['ROOM A'],
    avg: true,
    grp: 'ra',
    sub: 'rm',
  },
  {
    n: 70,
    nm: 'Room B',
    u: '',
    kw: ['ROOM B'],
    avg: true,
    grp: 'rb',
    sub: 'rm',
  },
  {
    n: 75,
    nm: 'Room C',
    u: '',
    kw: ['ROOM C'],
    avg: true,
    grp: 'rc',
    sub: 'rm',
  },
  {
    n: 80,
    nm: 'Room D',
    u: '',
    kw: ['ROOM D'],
    avg: true,
    grp: 'rd',
    sub: 'rm',
  },
];

const files = [{ file_id: 1 }, { file_id: 2 }, { file_id: 3 }];

const ROW_ITEMS: MeasureItem[] = [
  { n: 1, c: 'Target', nm: 'Target Temp', u: 'C', cs: 1, kw: [] },
  {
    n: 10,
    c: 'Air',
    nm: 'Group Avg',
    u: '',
    cs: 4,
    kw: [],
    avg: true,
    grp: 'grp',
  },
  { n: 11, nm: 'Child A', u: '', kw: [], sub: 'grp' },
  {
    n: 12,
    nm: 'Nested Avg',
    u: '',
    kw: [],
    avg: true,
    grp: 'nested',
    sub: 'grp',
  },
  { n: 13, nm: 'Nested Child', u: '', kw: [], sub: 'nested' },
  { n: 30, c: 'Calc', nm: 'Calculated', u: '', cs: 1, kw: [], calc: true },
];

function item(itemN: number): MeasureItem {
  const found = ITEMS.find((candidate) => candidate.n === itemN);
  if (!found) throw new Error(`Missing test item ${itemN}`);
  return found;
}

describe('sysperf match model', () => {
  it('initializes auto matches, checked state, value state, and average mode', () => {
    const state = buildInitialSysPerfMatchState({
      items: ITEMS,
      files: files.slice(0, 2),
      headersByFileId: {
        1: ['CHILD A'],
        2: ['GROUP AVG'],
      },
      numericCountsByFileId: {
        1: { 'CHILD A': 12 },
        2: { 'GROUP AVG': 8 },
      },
    });

    expect(state.activeFid).toBe(1);
    expect(state.match[1][11]).toBe('CHILD A');
    expect(state.checked[1][11]).toBe(true);
    expect(state.valueState[1][11]).toBe('loading');
    expect(state.match[1][12]).toBe('');
    expect(state.checked[1][12]).toBe(false);
    expect(state.valueState[1][12]).toBe('');
    expect(state.avgMode[10]).toBe('direct');
    expect(state.checked[2][10]).toBe(true);
  });

  it('defaults an unmatched average parent to average mode and clears parent checks', () => {
    const state = buildInitialSysPerfMatchState({
      items: ITEMS,
      files: files.slice(0, 1),
      headersByFileId: { 1: ['CHILD A'] },
      numericCountsByFileId: { 1: { 'CHILD A': 3 } },
    });

    expect(state.avgMode[10]).toBe('avg');
    expect(state.checked[1][10]).toBe(false);
    expect(state.checked[1][11]).toBe(true);
  });

  it('reruns auto matching only for empty entries and preserves manual matches', () => {
    const result = applySysPerfRerunAutoMatch({
      items: ITEMS,
      files: files.slice(0, 1),
      headersByFileId: { 1: ['MANUAL', 'CHILD A'] },
      numericCountsByFileId: { 1: { MANUAL: 4, 'CHILD A': 4 } },
      match: { 1: { 20: 'Manual Column', 11: '' } },
      checked: { 1: { 20: true, 11: false } },
    });

    expect(result.added).toBe(1);
    expect(result.match[1][20]).toBe('Manual Column');
    expect(result.match[1][11]).toBe('CHILD A');
    expect(result.checked[1][11]).toBe(true);
  });

  it('probes matched sheet data, trims alternate header keys, and reports unchecked nodata rows', () => {
    const result = applySysPerfSheetDataProbe({
      items: ITEMS,
      fileId: 1,
      match: { 1: { 11: 'Child A', 12: 'Child B', 20: '' } },
      valueState: { 1: { 11: 'loading', 12: 'loading', 20: '' } },
      data: {
        ' child a ': [null, 0],
        'Child B': [null, undefined, Number.NaN],
      },
      status: 'ok',
    });

    expect(result.valueState[1][11]).toBe('ok');
    expect(result.valueState[1][12]).toBe('nodata');
    expect(result.valueState[1][20]).toBe('');
    expect(result.uncheckedItemNumbers).toEqual([12]);
  });

  it('marks unresolved sheet probes as qmark and rejected probes as err', () => {
    const base = {
      items: ITEMS,
      fileId: 1,
      match: { 1: { 11: 'Child A', 12: '' } },
      valueState: { 1: { 11: 'loading', 12: '' } },
    };

    const missing = applySysPerfSheetDataProbe({
      ...base,
      data: null,
      status: 'missing',
    });
    const error = applySysPerfSheetDataProbe({
      ...base,
      status: 'error',
    });

    expect(missing.valueState[1][11]).toBe('qmark');
    expect(missing.valueState[1][12]).toBe('');
    expect(missing.uncheckedItemNumbers).toEqual([]);
    expect(error.valueState[1][11]).toBe('err');
    expect(error.valueState[1][12]).toBe('');
  });

  it('clears checked rows reported by the data probe without touching other items', () => {
    const checked = clearSysPerfCheckedItems({
      checked: { 1: { 11: true, 12: true }, 2: { 11: true } },
      fileId: 1,
      itemNumbers: [12],
    });

    expect(checked).toEqual({ 1: { 11: true, 12: false }, 2: { 11: true } });
  });

  it('toggles average mode and updates parent checks from matched direct values', () => {
    const toAverage = toggleSysPerfAverageMode({
      files: files.slice(0, 2),
      itemN: 10,
      avgMode: { 10: 'direct' },
      checked: { 1: { 10: true, 11: true }, 2: { 10: true, 20: true } },
      match: { 1: { 10: 'GROUP AVG' }, 2: { 10: '' } },
    });

    expect(toAverage.avgMode[10]).toBe('avg');
    expect(toAverage.checked[1][10]).toBe(false);
    expect(toAverage.checked[2][10]).toBe(false);
    expect(toAverage.checked[1][11]).toBe(true);
    expect(toAverage.checked[2][20]).toBe(true);

    const toDirect = toggleSysPerfAverageMode({
      files,
      itemN: 10,
      avgMode: toAverage.avgMode,
      checked: { ...toAverage.checked, 3: { 20: true } },
      match: { 1: { 10: 'GROUP AVG' }, 2: { 10: '' }, 3: { 10: 'GROUP AVG' } },
    });

    expect(toDirect.avgMode[10]).toBe('direct');
    expect(toDirect.checked[1][10]).toBe(true);
    expect(toDirect.checked[2][10]).toBe(false);
    expect(toDirect.checked[3][10]).toBe(true);
    expect(toDirect.checked[3][20]).toBe(true);
  });

  it('builds table row views with recursive collapse, depth, row kind, and per-file cell state', () => {
    const hidden = collectHiddenSysPerfSubGroups(
      ROW_ITEMS,
      new Set(['nested']),
    );
    const rows = buildSysPerfMatchRows({
      items: ROW_ITEMS,
      files: files.slice(0, 2),
      activeFileId: 2,
      hiddenSubGroups: hidden,
      itemCategories: buildSysPerfItemCategoryMap(ROW_ITEMS),
      match: { 1: { 10: 'GROUP AVG' }, 2: { 10: 'GROUP AVG', 11: 'CHILD A' } },
      checked: { 1: { 10: true }, 2: { 11: true } },
      valueState: { 2: { 11: 'ok' } },
      avgMode: { 10: 'avg' },
    });

    expect(rows.map((row) => row.item.n)).toEqual([1, 10, 11, 12, 30]);
    expect(rows.find((row) => row.item.n === 13)).toBeUndefined();

    const targetRow = rows.find((row) => row.item.n === 1);
    const groupRow = rows.find((row) => row.item.n === 10);
    const childRow = rows.find((row) => row.item.n === 11);
    const nestedRow = rows.find((row) => row.item.n === 12);
    const calcRow = rows.find((row) => row.item.n === 30);

    expect(targetRow?.kind).toBe('target');
    expect(groupRow?.kind).toBe('match');
    expect(groupRow?.categoryRowSpan).toBe(3);
    expect(groupRow?.avgGroup).toBe('grp');
    expect(groupRow?.success).toBe(true);
    expect(groupRow?.fileCells.map((cell) => cell.visible)).toEqual([
      false,
      true,
    ]);
    expect(groupRow?.fileCells[1]).toEqual(
      expect.objectContaining({
        fileId: 2,
        averageDisabled: true,
        currentMatch: 'GROUP AVG',
        valueState: '',
      }),
    );
    expect(childRow?.depth).toBe(1);
    expect(childRow?.fileCells[1]).toEqual(
      expect.objectContaining({
        checked: true,
        currentMatch: 'CHILD A',
        valueState: 'ok',
      }),
    );
    expect(nestedRow?.depth).toBe(1);
    expect(calcRow?.kind).toBe('calculated');
    expect(calcRow?.success).toBe(true);
  });

  it('hides all recursive average descendants when a parent group is collapsed', () => {
    const rows = buildSysPerfMatchRows({
      items: ROW_ITEMS,
      files: files.slice(0, 1),
      activeFileId: 1,
      hiddenSubGroups: collectHiddenSysPerfSubGroups(
        ROW_ITEMS,
        new Set(['grp']),
      ),
      itemCategories: buildSysPerfItemCategoryMap(ROW_ITEMS),
      match: {},
      checked: {},
      valueState: {},
      avgMode: {},
    });

    expect(rows.map((row) => row.item.n)).toEqual([1, 10, 30]);
  });

  it('syncs checked first-file matches only when target headers exist', () => {
    const result = syncSysPerfMatchesFromFirstFile({
      items: ITEMS,
      files,
      headersByFileId: {
        1: ['SYNC', 'UNCHECKED'],
        2: ['SYNC', 'UNCHECKED'],
        3: ['OTHER'],
      },
      match: { 1: { 20: 'SYNC', 11: 'UNCHECKED' }, 2: {}, 3: {} },
      checked: { 1: { 20: true, 11: false }, 2: {}, 3: {} },
    });

    expect(result.copied).toBe(1);
    expect(result.skipped).toBe(1);
    expect(result.match[2][20]).toBe('SYNC');
    expect(result.checked[2][20]).toBe(true);
    expect(result.match[2][11]).toBeUndefined();
  });

  it('builds confirm mappings with contract standard names and raw warnings', () => {
    const match: SysPerfFidMap<string> = {
      1: {
        65: 'ROOM_AB',
        70: 'ROOM_AB',
        75: 'ROOM_C',
        80: 'ROOM_D',
      },
      2: {},
    };
    const checked: SysPerfFidMap<boolean> = {
      1: {
        65: true,
        70: true,
        75: true,
        80: true,
      },
      2: {},
    };

    const plan = buildSysPerfConfirmPlan({
      items: ITEMS,
      files: files.slice(0, 2),
      headersByFileId: {
        1: ['ROOM_AB', 'ROOM_C', 'ROOM_D'],
        2: ['ROOM_AB', 'ROOM_C', 'ROOM_D'],
      },
      match,
      checked,
    });

    expect(plan.all[1]).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          col_index: 0,
          original_name: 'ROOM_AB',
          standard_name: stdName(item(65)),
        }),
      ]),
    );
    expect(plan.all[2]).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ original_name: 'ROOM_AB', _itemN: 65 }),
      ]),
    );
    expect(plan.duplicateWarnings).toEqual(
      expect.arrayContaining([
        {
          fileIndex: 0,
          originalName: 'ROOM_AB',
          itemNames: ['Room A', 'Room B'],
        },
        {
          fileIndex: 1,
          originalName: 'ROOM_AB',
          itemNames: ['Room A', 'Room B'],
        },
      ]),
    );
    expect(plan.roomAverageWarnings).toEqual([
      { fileIndex: 0 },
      { fileIndex: 1 },
    ]);

    const requests = buildSysPerfConfirmRequests({
      files: [
        { file_id: 1, sheets: [{ sheet_name: 'Sheet 1' }] },
        { file_id: 2, sheets: [{ sheet_name: 'Sheet 2' }] },
        { file_id: 3, sheets: [{ sheet_name: 'Sheet 3' }] },
      ],
      all: plan.all,
    });
    expect(requests).toHaveLength(2);
    expect(requests[0]).toEqual(
      expect.objectContaining({
        fileId: 1,
        sheetName: 'Sheet 1',
        fileIndex: 0,
      }),
    );
    expect(requests[0].mappings[0]).toEqual({
      col_index: 0,
      original_name: 'ROOM_AB',
      standard_name: stdName(item(65)),
    });

    const notice = buildSysPerfConfirmWarningNotice({
      plan,
      fileLabel: ({ fileNumber }) => `file-${fileNumber}`,
      roomAverageWarning: ({ fileNumber }) => `room-${fileNumber}`,
    });
    expect(notice.dupes[0]).toEqual({
      file: 'file-1',
      orig: 'ROOM_AB',
      items: 'Room A, Room B',
    });
    expect(notice.roomWarn).toEqual(['room-1', 'room-2']);
  });

  it('keeps match success rules for calculated, average, and room average rows', () => {
    expect(
      isSysPerfMatchSuccessful({
        item: item(30),
        items: ITEMS,
        checked: {},
        avgMode: {},
        fileIds: [1],
      }),
    ).toBe(true);

    expect(
      isSysPerfMatchSuccessful({
        item: item(10),
        items: ITEMS,
        checked: { 1: { 10: true } },
        avgMode: { 10: 'direct' },
        fileIds: [1],
      }),
    ).toBe(true);

    expect(
      isSysPerfMatchSuccessful({
        item: item(10),
        items: ITEMS,
        checked: { 1: { 11: true } },
        avgMode: { 10: 'avg' },
        fileIds: [1],
      }),
    ).toBe(true);

    const roomItem = item(64);
    expect(
      isSysPerfMatchSuccessful({
        item: roomItem,
        items: ITEMS,
        checked: { 1: { 65: true, 70: true } },
        avgMode: {},
        fileIds: [1],
      }),
    ).toBe(true);
    expect(
      isSysPerfMatchSuccessful({
        item: roomItem,
        items: ITEMS,
        checked: { 1: { 65: true, 75: true } },
        avgMode: {},
        fileIds: [1],
      }),
    ).toBe(false);
  });
});
