import { describe, expect, it } from 'vitest';

import {
  buildLegacyIssuePastePlan,
  expandLegacyIssuePasteValuesForSelection,
  normalizeLegacyIssueDateInput,
} from './legacy-issue-grid-paste-model';

type Row = {
  a?: string | null;
  b?: string | null;
  c?: string | null;
  id: string;
};

const columns = [{ key: 'a' }, { key: 'b' }, { key: 'c' }];
const rows: Row[] = [
  { id: 'row-1', a: 'A1', b: 'B1', c: 'C1' },
  { id: 'row-2', a: 'A2', b: 'B2', c: 'C2' },
];

function getCellValue(row: Row, columnKey: string) {
  return row[columnKey as keyof Row] ?? '';
}

describe('buildLegacyIssuePastePlan', () => {
  it('maps Excel-style tabular data from the target cell into visible rows and columns', () => {
    const plan = buildLegacyIssuePastePlan({
      getCellValue,
      blankRowCount: 0,
      readonlyColumnKeys: new Set<string>(),
      target: [0, 0],
      values: [
        ['A1-new', 'B1-new'],
        ['A2-new', 'B2-new'],
      ],
      visibleColumns: columns,
      visibleRecords: rows,
    });

    expect(plan.creates).toEqual([]);
    expect(
      plan.edits.map((edit) => ({
        columnKey: edit.columnKey,
        recordId: edit.record.id,
        value: edit.value,
      })),
    ).toEqual([
      { columnKey: 'a', recordId: 'row-1', value: 'A1-new' },
      { columnKey: 'b', recordId: 'row-1', value: 'B1-new' },
      { columnKey: 'a', recordId: 'row-2', value: 'A2-new' },
      { columnKey: 'b', recordId: 'row-2', value: 'B2-new' },
    ]);
  });

  it('skips readonly columns while preserving the pasted matrix positions', () => {
    const plan = buildLegacyIssuePastePlan({
      getCellValue,
      blankRowCount: 0,
      readonlyColumnKeys: new Set(['b']),
      target: [0, 0],
      values: [['A1-new', 'B1-new', 'C1-new']],
      visibleColumns: columns,
      visibleRecords: rows,
    });

    expect(
      plan.edits.map((edit) => ({
        columnKey: edit.columnKey,
        value: edit.value,
      })),
    ).toEqual([
      { columnKey: 'a', value: 'A1-new' },
      { columnKey: 'c', value: 'C1-new' },
    ]);
  });

  it('treats the first grid column as the first editable data column', () => {
    const plan = buildLegacyIssuePastePlan({
      getCellValue,
      blankRowCount: 0,
      readonlyColumnKeys: new Set<string>(),
      target: [0, 0],
      values: [['from-first-column']],
      visibleColumns: columns,
      visibleRecords: rows,
    });

    expect(plan.edits).toMatchObject([
      { columnKey: 'a', record: rows[0], value: 'from-first-column' },
    ]);
  });

  it('turns blank pasted cells into null updates and skips unchanged cells', () => {
    const plan = buildLegacyIssuePastePlan({
      getCellValue,
      blankRowCount: 0,
      readonlyColumnKeys: new Set<string>(),
      target: [0, 0],
      values: [['A1', '   ']],
      visibleColumns: columns,
      visibleRecords: rows,
    });

    expect(plan.edits).toMatchObject([
      { columnKey: 'b', record: rows[0], value: null },
    ]);
  });

  it('normalizes date-cell paste values and supports clearing them to null', () => {
    const dateRows = [
      { id: 'row-1', received_date: '2026-07-20' },
      { id: 'row-2', received_date: '2026-07-21' },
    ];
    const plan = buildLegacyIssuePastePlan({
      getCellValue: (row, columnKey) =>
        row[columnKey as keyof (typeof dateRows)[number]],
      blankRowCount: 0,
      readonlyColumnKeys: new Set<string>(),
      target: [0, 0],
      values: [['2026.7.24'], ['']],
      visibleColumns: [{ key: 'received_date', inputKind: 'date' }],
      visibleRecords: dateRows,
    });

    expect(plan.edits).toMatchObject([
      {
        columnKey: 'received_date',
        record: dateRows[0],
        value: '2026-07-24',
      },
      {
        columnKey: 'received_date',
        record: dateRows[1],
        value: null,
      },
    ]);
  });

  it('does not apply an invalid date pasted into a date cell', () => {
    const plan = buildLegacyIssuePastePlan({
      getCellValue,
      blankRowCount: 0,
      readonlyColumnKeys: new Set<string>(),
      target: [0, 0],
      values: [['2026-02-30']],
      visibleColumns: [{ key: 'a', inputKind: 'date' }],
      visibleRecords: rows,
    });

    expect(plan).toEqual({ creates: [], edits: [] });
  });

  it('creates records from the configured top blank rows', () => {
    const plan = buildLegacyIssuePastePlan({
      getCellValue,
      blankRowCount: 2,
      readonlyColumnKeys: new Set<string>(),
      target: [0, 0],
      values: [
        ['new A1', 'new B1'],
        ['new A2', 'new B2'],
      ],
      visibleColumns: columns,
      visibleRecords: rows,
    });

    expect(plan.creates).toEqual([
      {
        rowIndex: 0,
        values: {
          a: 'new A1',
          b: 'new B1',
        },
      },
      {
        rowIndex: 1,
        values: {
          a: 'new A2',
          b: 'new B2',
        },
      },
    ]);
    expect(plan.edits).toEqual([]);
  });

  it('uses null to clear an existing blank-row date draft', () => {
    const plan = buildLegacyIssuePastePlan({
      getCellValue,
      blankRowCount: 1,
      readonlyColumnKeys: new Set<string>(),
      target: [0, 0],
      values: [['']],
      visibleColumns: [{ key: 'received_date', inputKind: 'date' }],
      visibleRecords: rows,
    });

    expect(plan.creates).toEqual([
      {
        rowIndex: 0,
        values: { received_date: null },
      },
    ]);
  });

  it('edits visible records after the top blank rows', () => {
    const plan = buildLegacyIssuePastePlan({
      getCellValue,
      blankRowCount: 1,
      readonlyColumnKeys: new Set<string>(),
      target: [0, 1],
      values: [['A1-new']],
      visibleColumns: columns,
      visibleRecords: rows,
    });

    expect(plan.creates).toEqual([]);
    expect(plan.edits).toMatchObject([
      { columnKey: 'a', record: rows[0], value: 'A1-new' },
    ]);
  });

  it('expands a single copied cell across the selected paste range', () => {
    expect(
      expandLegacyIssuePasteValuesForSelection({
        selection: { x: 1, y: 0, width: 2, height: 3 },
        target: [1, 0],
        values: [['북미']],
      }),
    ).toEqual([
      ['북미', '북미'],
      ['북미', '북미'],
      ['북미', '북미'],
    ]);
  });

  it('keeps tabular pasted data unchanged even when a larger range is selected', () => {
    const values = [
      ['A1-new', 'B1-new'],
      ['A2-new', 'B2-new'],
    ];

    expect(
      expandLegacyIssuePasteValuesForSelection({
        selection: { x: 1, y: 0, width: 4, height: 4 },
        target: [1, 0],
        values,
      }),
    ).toBe(values);
  });
});

describe('normalizeLegacyIssueDateInput', () => {
  it('normalizes unambiguous date values without timezone conversion', () => {
    expect(normalizeLegacyIssueDateInput('2026-07-24')).toBe('2026-07-24');
    expect(normalizeLegacyIssueDateInput('20260724')).toBe('2026-07-24');
    expect(normalizeLegacyIssueDateInput('2026.7.24')).toBe('2026-07-24');
    expect(normalizeLegacyIssueDateInput('2026/7/24')).toBe('2026-07-24');
  });

  it('allows blank values and rejects invalid or ambiguous dates', () => {
    expect(normalizeLegacyIssueDateInput('  ')).toBeNull();
    expect(normalizeLegacyIssueDateInput('2026-02-30')).toBeUndefined();
    expect(normalizeLegacyIssueDateInput('07/24/2026')).toBeUndefined();
    expect(normalizeLegacyIssueDateInput('07/2026')).toBeUndefined();
  });
});
