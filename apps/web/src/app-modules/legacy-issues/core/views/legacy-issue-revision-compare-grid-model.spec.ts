import { describe, expect, it } from 'vitest';

import {
  buildLegacyIssueRevisionCompareGridModel,
  getLegacyIssueRevisionCompareGridCellValue,
  getLegacyIssueRevisionCompareGridHighlight,
  getLegacyIssueRevisionCompareGridScrollOffset,
  LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY,
  type LegacyIssueRevisionCompareGridSide,
  type LegacyIssueRevisionCompareView,
} from './legacy-issue-revision-compare-grid-model';

const compareResult: LegacyIssueRevisionCompareView = {
  rows: [
    {
      cells: [
        {
          changed: false,
          field_key: 'symptom',
          field_label: 'Symptom',
          left_value: 'Noise',
          right_value: 'Noise',
        },
        {
          changed: true,
          field_key: 'primary_attachment',
          field_label: 'Attachment',
          left_value: 'old-evidence.pdf',
          right_value: 'new-evidence.pdf',
        },
      ],
      label: 'LI-001',
      stable_record_id: 'stable-1',
      status: 'modified',
    },
    {
      cells: [
        {
          changed: true,
          field_key: 'symptom',
          field_label: 'Symptom',
          left_value: null,
          right_value: 'Leak',
        },
        {
          changed: true,
          field_key: 'cause',
          field_label: 'Cause',
          left_value: null,
          right_value: 'Seal',
        },
      ],
      label: 'LI-002',
      stable_record_id: 'stable-2',
      status: 'added',
    },
    {
      cells: [
        {
          changed: true,
          field_key: 'symptom',
          field_label: 'Symptom',
          left_value: 'Rattle',
          right_value: null,
        },
        {
          changed: true,
          field_key: 'cause',
          field_label: 'Cause',
          left_value: 'Bracket',
          right_value: null,
        },
      ],
      label: 'LI-003',
      stable_record_id: 'stable-3',
      status: 'removed',
    },
  ],
};

describe('legacy issue revision compare grid model', () => {
  it('builds shared row and field columns for both compare panes', () => {
    const model = buildLegacyIssueRevisionCompareGridModel(compareResult);

    expect(model.columns.map((column) => column.fieldKey)).toEqual([
      LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY,
      'symptom',
      'primary_attachment',
      'cause',
    ]);
    expect(model.rows.map((row) => row.stableRecordId)).toEqual([
      'stable-1',
      'stable-2',
      'stable-3',
    ]);
  });

  it('orders change navigation by row while collapsing added and removed rows', () => {
    const model = buildLegacyIssueRevisionCompareGridModel(compareResult);

    expect(model.changedCellCount).toBe(3);
    expect(
      model.changes.map((change) => [
        change.kind,
        change.rowIndex,
        change.columnIndex,
        change.fieldKey,
        change.changedFieldCount,
      ]),
    ).toEqual([
      ['cell', 0, 2, 'primary_attachment', 1],
      ['row', 1, 0, LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY, 2],
      ['row', 2, 0, LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY, 2],
    ]);
    expect(model.changes[0]).toMatchObject({
      fieldLabel: 'Attachment',
      label: 'LI-001',
      status: 'modified',
    });
  });

  it('returns side-specific values and highlight states', () => {
    const model = buildLegacyIssueRevisionCompareGridModel(compareResult);
    const attachmentColumn = required(model.columns[2]);
    const causeColumn = required(model.columns[3]);
    const modifiedRow = required(model.rows[0]);
    const addedRow = required(model.rows[1]);
    const removedRow = required(model.rows[2]);

    expect(
      getLegacyIssueRevisionCompareGridCellValue({
        column: attachmentColumn,
        row: modifiedRow,
        side: 'left',
      }),
    ).toBe('old-evidence.pdf');
    expect(
      getLegacyIssueRevisionCompareGridCellValue({
        column: attachmentColumn,
        row: modifiedRow,
        side: 'right',
      }),
    ).toBe('new-evidence.pdf');
    expect(
      highlight(attachmentColumn.fieldKey, modifiedRow.status, 'left'),
    ).toBe('modified');
    expect(highlight(causeColumn.fieldKey, addedRow.status, 'right')).toBe(
      'added',
    );
    expect(highlight(causeColumn.fieldKey, addedRow.status, 'left')).toBeNull();
    expect(highlight(causeColumn.fieldKey, removedRow.status, 'left')).toBe(
      'removed',
    );
    expect(
      highlight(causeColumn.fieldKey, removedRow.status, 'right'),
    ).toBeNull();
  });

  it('derives pixel scroll offsets from visible region transforms', () => {
    const model = buildLegacyIssueRevisionCompareGridModel(compareResult);

    expect(
      getLegacyIssueRevisionCompareGridScrollOffset({
        columns: model.columns,
        frozenColumnCount: 1,
        range: { x: 2, y: 10 },
        rowHeight: 32,
        tx: -12,
        ty: -7,
      }),
    ).toEqual({
      scrollLeft: required(model.columns[1]).width + 12,
      scrollTop: 327,
    });
  });
});

function highlight(
  fieldKey: string,
  status: string,
  side: LegacyIssueRevisionCompareGridSide,
) {
  const model = buildLegacyIssueRevisionCompareGridModel(compareResult);
  const column = model.columns.find((item) => item.fieldKey === fieldKey);
  const row = model.rows.find((item) => item.status === status);
  if (!column || !row) return null;
  return getLegacyIssueRevisionCompareGridHighlight({ column, row, side });
}

function required<T>(value: T | undefined): T {
  if (value === undefined) {
    throw new Error('Expected test fixture value to exist.');
  }
  return value;
}
