import { describe, expect, it } from 'vitest';

import {
  applyGridColumnOrder,
  applyGridView,
  buildLegacyIssueGridRowOffsets,
  coerceLegacyIssuePasteCellValue,
  createLegacyIssueTextCell,
  createLegacyIssueGridTheme,
  getLegacyIssueGridRowHeight,
  getGridScrollPreferenceFromVisibleRegion,
  getLegacyIssueContextRowIndexes,
  getRequiredMissingColumnKeysForBlankRowDraft,
  isLegacyIssueGridColumnLayoutEqual,
  isLegacyIssueGridCellChanged,
  isLegacyIssueGridRowLayoutEqual,
  moveVisibleGridColumn,
  normalizeLegacyIssueGridDisplayData,
  normalizeGridScrollPreference,
  normalizeGridSortPreferences,
  resolveLegacyIssueGridColumnOrderState,
  resolveLegacyIssueGridHiddenColumnKeys,
  resolveLegacyIssueGridPersonalizedColumnOrder,
  resolveLegacyIssueVisibleGridColumns,
  toggleGridFilterSelectedValues,
} from './LegacyIssueDataGrid';

describe('legacy issue grid changed cells', () => {
  it('marks both unsaved local edits and persisted draft changes', () => {
    expect(
      isLegacyIssueGridCellChanged({
        changedCellKeys: new Set(),
        columnKey: 'problem',
        dirtyCells: { 'record-1:problem': 'before' },
        recordId: 'record-1',
      }),
    ).toBe(true);
    expect(
      isLegacyIssueGridCellChanged({
        changedCellKeys: new Set(['record-1:problem']),
        columnKey: 'problem',
        dirtyCells: {},
        recordId: 'record-1',
      }),
    ).toBe(true);
  });
});

type Row = {
  group?: string | null;
  id: string;
  item?: string | null;
};

const columns = [
  { key: 'group', title: 'Group', width: 120 },
  { key: 'item', title: 'Item', width: 120 },
];

function getCellValue(row: Row, columnKey: string) {
  return row[columnKey as keyof Row] ?? null;
}

describe('applyGridView', () => {
  it('sorts by multiple columns in priority order', () => {
    const rows: Row[] = [
      { id: 'b-2', group: 'B', item: '2' },
      { id: 'a-2', group: 'A', item: '2' },
      { id: 'a-1', group: 'A', item: '1' },
      { id: 'b-1', group: 'B', item: '1' },
    ];

    const result = applyGridView({
      columns,
      filters: {},
      getCellValue,
      records: rows,
      sorts: [
        { columnKey: 'group', direction: 'asc' },
        { columnKey: 'item', direction: 'desc' },
      ],
    });

    expect(result.map((row) => row.id)).toEqual(['a-2', 'a-1', 'b-2', 'b-1']);
  });

  it('places empty values according to the active sort rule', () => {
    const rows: Row[] = [
      { id: 'empty', item: null },
      { id: 'two', item: '2' },
      { id: 'one', item: '1' },
    ];

    const result = applyGridView({
      columns,
      filters: {},
      getCellValue,
      records: rows,
      sorts: [{ columnKey: 'item', direction: 'asc', emptyPlacement: 'last' }],
    });

    expect(result.map((row) => row.id)).toEqual(['one', 'two', 'empty']);
  });
});

describe('legacy issue grid sort preferences', () => {
  it('keeps valid persisted sort rules and drops malformed entries', () => {
    expect(
      normalizeGridSortPreferences([
        { columnKey: 'group', direction: 'asc' },
        {
          columnKey: 'item',
          direction: 'desc',
          emptyPlacement: 'last',
        },
        { columnKey: 'ignored', direction: 'sideways' },
        { columnKey: '', direction: 'asc' },
        null,
      ]),
    ).toEqual([
      { columnKey: 'group', direction: 'asc' },
      { columnKey: 'item', direction: 'desc', emptyPlacement: 'last' },
    ]);
  });
});

describe('legacy issue grid scroll preferences', () => {
  it('normalizes persisted scroll offsets', () => {
    expect(
      normalizeGridScrollPreference({
        columnIndex: 2.8,
        rowIndex: 4.2,
        scrollLeft: 120.5,
        scrollTop: 240.5,
      }),
    ).toEqual({
      columnIndex: 2,
      rowIndex: 4,
      scrollLeft: 121,
      scrollTop: 241,
    });
    expect(normalizeGridScrollPreference({ scrollLeft: -1 })).toBeNull();
  });

  it('derives pixel offsets from the visible grid region', () => {
    expect(
      getGridScrollPreferenceFromVisibleRegion({
        columns: [
          { key: 'a', title: 'A', width: 40 },
          { key: 'b', title: 'B', width: 80 },
        ],
        range: { height: 20, width: 4, x: 1, y: 3 },
        rowStartOffset: 90,
        tx: -8,
        ty: -12,
      }),
    ).toEqual({
      columnIndex: 1,
      rowIndex: 3,
      scrollLeft: 48,
      scrollTop: 102,
    });
  });
});

describe('legacy issue grid automatic row height', () => {
  it('renders multiline text as wrapped lines while preserving its copy value', () => {
    expect(createLegacyIssueTextCell('first\nsecond', false)).toMatchObject({
      allowWrapping: true,
      copyData: 'first\nsecond',
      data: 'first\nsecond',
      displayData: 'first\nsecond',
    });
    expect(createLegacyIssueTextCell('single line', false)).toMatchObject({
      allowWrapping: true,
      displayData: 'single line',
    });
  });

  it('marks date cells for native date editing and coerces pasted dates', () => {
    const cell = createLegacyIssueTextCell('2026-07-20', false, {
      inputKind: 'date',
      inputLabel: '접수일',
    });

    expect(cell).toMatchObject({
      legacyIssueInputKind: 'date',
      legacyIssueInputLabel: '접수일',
    });
    expect(coerceLegacyIssuePasteCellValue('2026.7.24', cell)).toMatchObject({
      copyData: '2026-07-24',
      data: '2026-07-24',
      displayData: '2026-07-24',
    });
    expect(coerceLegacyIssuePasteCellValue('', cell)).toMatchObject({
      data: '',
      displayData: '',
    });
    expect(coerceLegacyIssuePasteCellValue('2026-02-30', cell)).toBe(cell);
  });

  it('preserves line breaks for display and normalizes Windows line endings', () => {
    expect(
      normalizeLegacyIssueGridDisplayData('first\r\nsecond\rthird\tvalue'),
    ).toBe('first\nsecond\nthird value');
  });

  it('grows to the tallest multiline cell and keeps one-line rows compact', () => {
    const row = {
      cause: 'single line',
      symptom: 'first\nsecond\nthird',
    };
    expect(
      getLegacyIssueGridRowHeight({
        columns: [
          { key: 'cause', title: 'Cause', width: 120 },
          { key: 'symptom', title: 'Symptom', width: 120 },
        ],
        getCellValue: (columnKey) => row[columnKey as keyof typeof row] ?? null,
      }),
    ).toBe(66);
    expect(
      getLegacyIssueGridRowHeight({
        columns: [{ key: 'cause', title: 'Cause', width: 120 }],
        getCellValue: (columnKey) => row[columnKey as keyof typeof row] ?? null,
      }),
    ).toBe(30);
  });

  it('wraps long text based on the visible column width', () => {
    const value =
      '긴 설명을 입력하면 현재 열 너비에 맞춰 자동으로 줄바꿈합니다';
    const getCellValue = () => value;

    const narrowHeight = getLegacyIssueGridRowHeight({
      columns: [{ key: 'notes', title: 'Notes', width: 100 }],
      getCellValue,
    });
    const wideHeight = getLegacyIssueGridRowHeight({
      columns: [{ key: 'notes', title: 'Notes', width: 600 }],
      getCellValue,
    });

    expect(narrowHeight).toBeGreaterThan(wideHeight);
    expect(wideHeight).toBe(30);
  });

  it('accounts for word-boundary wrapping instead of only total text width', () => {
    expect(
      getLegacyIssueGridRowHeight({
        columns: [{ key: 'notes', title: 'Notes', width: 98 }],
        getCellValue: () => '1234567890 abcdefghij',
      }),
    ).toBe(48);
  });

  it('caps exceptionally tall rows and builds variable-height scroll offsets', () => {
    expect(
      getLegacyIssueGridRowHeight({
        columns: [{ key: 'notes', title: 'Notes', width: 120 }],
        getCellValue: () =>
          Array.from({ length: 100 }, () => 'line').join('\n'),
      }),
    ).toBe(228);
    expect(buildLegacyIssueGridRowOffsets([30, 48, 66])).toEqual([
      0, 30, 78, 144,
    ]);
    expect(
      getGridScrollPreferenceFromVisibleRegion({
        columns: [{ width: 80 }],
        range: { x: 0, y: 2 },
        rowStartOffset: 78,
        tx: 0,
        ty: -6,
      }),
    ).toMatchObject({
      rowIndex: 2,
      scrollTop: 84,
    });
  });
});

describe('legacy issue grid column layout', () => {
  it('retains column order state when a parent passes an equal new array', () => {
    const current = ['a', 'b', 'c'];

    expect(
      resolveLegacyIssueGridColumnOrderState(current, ['a', 'b', 'c']),
    ).toBe(current);
    expect(
      resolveLegacyIssueGridColumnOrderState(current, ['a', 'c', 'b']),
    ).toEqual(['a', 'c', 'b']);
  });

  it('suppresses duplicate visible-column layout notifications', () => {
    const current = {
      columnKeys: ['a', 'c'],
      layoutId: 'legacy-grid',
    };

    expect(
      isLegacyIssueGridColumnLayoutEqual(current, {
        columnKeys: ['a', 'c'],
        layoutId: 'legacy-grid',
      }),
    ).toBe(true);
    expect(
      isLegacyIssueGridColumnLayoutEqual(current, {
        columnKeys: ['a', 'c'],
        layoutId: 'other-grid',
      }),
    ).toBe(false);
    expect(
      isLegacyIssueGridColumnLayoutEqual(current, {
        columnKeys: ['c', 'a'],
        layoutId: 'legacy-grid',
      }),
    ).toBe(false);
  });

  it('applies saved column order and inserts new columns near their default position', () => {
    const result = applyGridColumnOrder(
      [
        { key: 'a', title: 'A', width: 120 },
        { key: 'b', title: 'B', width: 120 },
        { key: 'c', title: 'C', width: 120 },
      ],
      ['c', 'missing', 'a'],
    );

    expect(result.map((column) => column.key)).toEqual(['c', 'a', 'b']);
  });

  it('keeps a personal order and appends newly available columns at the end', () => {
    expect(
      resolveLegacyIssueGridPersonalizedColumnOrder({
        columns: [
          { key: 'a', title: 'A', width: 120 },
          { key: 'b', title: 'B', width: 120 },
          { key: 'c', title: 'C', width: 120 },
        ],
        defaultColumnOrder: ['c', 'b', 'a'],
        personalizedColumnOrder: ['b', 'a'],
      }),
    ).toEqual(['b', 'a', 'c']);
  });

  it('ignores unavailable hidden keys and always leaves one column visible', () => {
    expect(
      resolveLegacyIssueGridHiddenColumnKeys(
        [
          { key: 'a', title: 'A', width: 120 },
          { key: 'b', title: 'B', width: 120 },
        ],
        ['missing', 'a', 'b', 'a'],
      ),
    ).toEqual(['b']);
  });

  it('inserts a new column between its saved neighboring columns', () => {
    const result = applyGridColumnOrder(
      [
        { key: 'master_status', title: 'Master Status', width: 120 },
        { key: 'legacy_issue', title: 'Legacy Issue', width: 120 },
        { key: 'design_check_sheet', title: 'Design Check Sheet', width: 120 },
      ],
      ['master_status', 'design_check_sheet'],
    );

    expect(result.map((column) => column.key)).toEqual([
      'master_status',
      'legacy_issue',
      'design_check_sheet',
    ]);
  });

  it('moves only visible columns while preserving hidden column slots', () => {
    const allColumns = [
      { key: 'a', title: 'A', width: 120 },
      { key: 'b', title: 'B', width: 120 },
      { key: 'c', title: 'C', width: 120 },
      { key: 'd', title: 'D', width: 120 },
    ];
    const result = moveVisibleGridColumn({
      columns: allColumns,
      currentOrder: ['a', 'b', 'c', 'd'],
      fromVisibleIndex: 2,
      toVisibleIndex: 0,
      visibleColumns: [allColumns[0], allColumns[2], allColumns[3]],
    });

    expect(result).toEqual(['d', 'b', 'a', 'c']);
  });

  it('exports the ordered visible columns and omits hidden columns', () => {
    const ordered = applyGridColumnOrder(
      [
        { key: 'a', title: 'A', width: 120 },
        { key: 'b', title: 'B', width: 120 },
        { key: 'c', title: 'C', width: 120 },
      ],
      ['c', 'a', 'b'],
    );

    expect(
      resolveLegacyIssueVisibleGridColumns({
        columns: ordered,
        hiddenColumnKeys: new Set(['a']),
      }).map((column) => column.key),
    ).toEqual(['c', 'b']);
  });
});

describe('legacy issue grid row layout', () => {
  it('compares the visible row order and whether a view is applied', () => {
    const current = {
      recordIds: ['record-2', 'record-1'],
      layoutId: 'legacy-grid',
      viewApplied: true,
    };

    expect(isLegacyIssueGridRowLayoutEqual(current, { ...current })).toBe(true);
    expect(
      isLegacyIssueGridRowLayoutEqual(current, {
        ...current,
        recordIds: ['record-1', 'record-2'],
      }),
    ).toBe(false);
    expect(
      isLegacyIssueGridRowLayoutEqual(current, {
        ...current,
        viewApplied: false,
      }),
    ).toBe(false);
  });
});

describe('legacy issue grid context row selection', () => {
  it('uses every selected row when the context row is part of a row selection', () => {
    expect(
      getLegacyIssueContextRowIndexes({
        rowCount: 10,
        rowIndex: 3,
        selection: {
          rows: { toArray: () => [2, 3, 4] },
        },
      }),
    ).toEqual([2, 3, 4]);
  });

  it('uses the clicked row when the context row is outside the row selection', () => {
    expect(
      getLegacyIssueContextRowIndexes({
        rowCount: 10,
        rowIndex: 6,
        selection: {
          rows: { toArray: () => [2, 3, 4] },
        },
      }),
    ).toEqual([6]);
  });

  it('uses every row in the selected cell range when right-clicking inside it', () => {
    expect(
      getLegacyIssueContextRowIndexes({
        rowCount: 10,
        rowIndex: 2,
        selection: {
          current: {
            range: { x: 1, y: 1, width: 3, height: 4 },
          },
        },
      }),
    ).toEqual([1, 2, 3, 4]);
  });
});

describe('legacy issue grid blank row required fields', () => {
  const requiredColumnKeys = new Set(['region_zone']);

  it('does not mark untouched blank rows as missing required values', () => {
    expect(
      getRequiredMissingColumnKeysForBlankRowDraft({
        requiredColumnKeys,
        values: {},
      }),
    ).toEqual([]);
  });

  it('marks required values only after the blank row has data', () => {
    expect(
      getRequiredMissingColumnKeysForBlankRowDraft({
        requiredColumnKeys,
        values: { symptom: '소음' },
      }),
    ).toEqual(['region_zone']);
  });

  it('clears the missing marker once the required value is present', () => {
    expect(
      getRequiredMissingColumnKeysForBlankRowDraft({
        requiredColumnKeys,
        values: { region_zone: '북미', symptom: '소음' },
      }),
    ).toEqual([]);
  });
});

describe('legacy issue grid filter value selection', () => {
  it('clears every value when all values are selected', () => {
    expect(
      toggleGridFilterSelectedValues({
        allValues: ['A', 'B', 'C'],
        filteredValues: ['A', 'B', 'C'],
        selectedValues: null,
      }),
    ).toEqual([]);
  });

  it('toggles only searched values from the selected set', () => {
    expect(
      toggleGridFilterSelectedValues({
        allValues: ['A', 'B', 'C', 'D'],
        filteredValues: ['B', 'C'],
        selectedValues: null,
      }),
    ).toEqual(['A', 'D']);
  });

  it('selects every searched value when the search subset is partial', () => {
    expect(
      toggleGridFilterSelectedValues({
        allValues: ['A', 'B', 'C', 'D'],
        filteredValues: ['B', 'C'],
        selectedValues: ['A', 'B'],
      }),
    ).toEqual(['A', 'B', 'C']);
  });
});

describe('legacy issue grid theme', () => {
  it('uses the app ink color for two-level group headers', () => {
    document.documentElement.style.setProperty(
      '--color-app-ink',
      'rgb(229, 231, 235)',
    );

    const theme = createLegacyIssueGridTheme();

    expect(theme.theme.textHeader).toBe('rgb(229, 231, 235)');
    expect(theme.theme.textGroupHeader).toBe('rgb(229, 231, 235)');
  });
});
