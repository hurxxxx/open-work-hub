export type LegacyIssueRevisionCompareCellView = {
  changed: boolean;
  field_key: string;
  field_label: string;
  left_value: string | null;
  right_value: string | null;
};

export type LegacyIssueRevisionCompareRowView = {
  cells: LegacyIssueRevisionCompareCellView[];
  label: string;
  stable_record_id: string;
  status: string;
};

export type LegacyIssueRevisionCompareRevisionView = {
  revision_no: number | null;
  status: string;
};

export type LegacyIssueRevisionCompareView = {
  left_revision?: LegacyIssueRevisionCompareRevisionView;
  right_revision?: LegacyIssueRevisionCompareRevisionView;
  rows: LegacyIssueRevisionCompareRowView[];
};

export type LegacyIssueRevisionCompareGridSide = 'left' | 'right';

export type LegacyIssueRevisionCompareGridHighlight =
  | 'added'
  | 'modified'
  | 'removed';

export type LegacyIssueRevisionCompareGridColumn = {
  fieldKey: string;
  title: string;
  width: number;
};

export type LegacyIssueRevisionCompareGridRow = {
  cellsByFieldKey: Record<string, LegacyIssueRevisionCompareCellView>;
  label: string;
  stableRecordId: string;
  status: string;
};

export type LegacyIssueRevisionCompareGridChange = {
  changedFieldCount: number;
  columnIndex: number;
  fieldLabel: string;
  fieldKey: string;
  kind: 'cell' | 'row';
  label: string;
  rowIndex: number;
  stableRecordId: string;
  status: string;
};

export type LegacyIssueRevisionCompareGridModel = {
  changedCellCount: number;
  changes: LegacyIssueRevisionCompareGridChange[];
  columns: LegacyIssueRevisionCompareGridColumn[];
  rows: LegacyIssueRevisionCompareGridRow[];
};

export type LegacyIssueRevisionCompareGridScrollOffset = {
  scrollLeft: number;
  scrollTop: number;
};

export const LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY = '__legacy_issue_row__';

export function buildLegacyIssueRevisionCompareGridModel(
  compareResult: LegacyIssueRevisionCompareView,
): LegacyIssueRevisionCompareGridModel {
  const columns: LegacyIssueRevisionCompareGridColumn[] = [
    {
      fieldKey: LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY,
      title: '',
      width: 220,
    },
  ];
  const seenFieldKeys = new Set<string>([LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY]);
  const rows = compareResult.rows.map((row) => {
    const cellsByFieldKey: Record<string, LegacyIssueRevisionCompareCellView> =
      {};
    for (const cell of row.cells) {
      cellsByFieldKey[cell.field_key] = cell;
      if (!seenFieldKeys.has(cell.field_key)) {
        seenFieldKeys.add(cell.field_key);
        columns.push({
          fieldKey: cell.field_key,
          title: cell.field_label,
          width: compareGridColumnWidth(cell.field_label),
        });
      }
    }
    return {
      cellsByFieldKey,
      label: row.label,
      stableRecordId: row.stable_record_id,
      status: row.status,
    };
  });

  const fieldColumnIndex = new Map(
    columns.map((column, index) => [column.fieldKey, index]),
  );
  const changes: LegacyIssueRevisionCompareGridChange[] = [];
  for (const [rowIndex, row] of compareResult.rows.entries()) {
    if (row.status === 'added' || row.status === 'removed') {
      changes.push({
        changedFieldCount: row.cells.filter((cell) => cell.changed).length,
        columnIndex: 0,
        fieldLabel: '',
        fieldKey: LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY,
        kind: 'row',
        label: row.label,
        rowIndex,
        stableRecordId: row.stable_record_id,
        status: row.status,
      });
      continue;
    }
    for (const cell of row.cells) {
      if (!cell.changed) continue;
      const columnIndex = fieldColumnIndex.get(cell.field_key);
      if (columnIndex === undefined) continue;
      changes.push({
        changedFieldCount: 1,
        columnIndex,
        fieldLabel: cell.field_label,
        fieldKey: cell.field_key,
        kind: 'cell',
        label: row.label,
        rowIndex,
        stableRecordId: row.stable_record_id,
        status: row.status,
      });
    }
  }

  return {
    changedCellCount: changes.length,
    changes,
    columns,
    rows,
  };
}

export function getLegacyIssueRevisionCompareGridCellValue({
  column,
  row,
  side,
}: {
  column: LegacyIssueRevisionCompareGridColumn;
  row: LegacyIssueRevisionCompareGridRow;
  side: LegacyIssueRevisionCompareGridSide;
}): string | null {
  if (column.fieldKey === LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY) {
    return row.label;
  }
  const cell = row.cellsByFieldKey[column.fieldKey];
  if (!cell) return null;
  return side === 'left' ? cell.left_value : cell.right_value;
}

export function getLegacyIssueRevisionCompareGridHighlight({
  column,
  row,
  side,
}: {
  column: LegacyIssueRevisionCompareGridColumn;
  row: LegacyIssueRevisionCompareGridRow;
  side: LegacyIssueRevisionCompareGridSide;
}): LegacyIssueRevisionCompareGridHighlight | null {
  if (row.status === 'added') {
    return side === 'right' ? 'added' : null;
  }
  if (row.status === 'removed') {
    return side === 'left' ? 'removed' : null;
  }
  if (column.fieldKey === LEGACY_ISSUE_COMPARE_ROW_FIELD_KEY) {
    return null;
  }
  const cell = row.cellsByFieldKey[column.fieldKey];
  if (row.status === 'modified' && cell?.changed) {
    return 'modified';
  }
  return null;
}

export function getLegacyIssueRevisionCompareGridScrollOffset({
  columns,
  frozenColumnCount = 0,
  range,
  rowHeight,
  tx,
  ty,
}: {
  columns: readonly Pick<LegacyIssueRevisionCompareGridColumn, 'width'>[];
  frozenColumnCount?: number;
  range: { x: number; y: number };
  rowHeight: number;
  tx: number;
  ty: number;
}): LegacyIssueRevisionCompareGridScrollOffset {
  const columnIndex = Math.max(0, Math.floor(range.x));
  const rowIndex = Math.max(0, Math.floor(range.y));
  const columnOffset = columns
    .slice(0, columnIndex)
    .reduce((total, column) => total + column.width, 0);
  const frozenColumnOffset = columns
    .slice(0, Math.max(0, Math.min(frozenColumnCount, columns.length)))
    .reduce((total, column) => total + column.width, 0);
  return {
    scrollLeft: Math.max(0, Math.round(columnOffset - frozenColumnOffset - tx)),
    scrollTop: Math.max(0, Math.round(rowIndex * rowHeight - ty)),
  };
}

function compareGridColumnWidth(label: string): number {
  return Math.min(320, Math.max(140, label.length * 12 + 56));
}
