import { normalizeDateInputText } from '@/src/components/date/date-input-model';

export type LegacyIssuePasteColumn = {
  inputKind?: 'date';
  key: string;
};

export type LegacyIssuePasteEdit<TRecord> = {
  columnKey: string;
  record: TRecord;
  value: string | null;
};

export type LegacyIssuePasteCreate = {
  rowIndex: number;
  values: Record<string, string | null>;
};

export type LegacyIssuePastePlan<TRecord> = {
  creates: LegacyIssuePasteCreate[];
  edits: Array<LegacyIssuePasteEdit<TRecord>>;
};

export function buildLegacyIssuePastePlan<TRecord>({
  getCellValue,
  blankRowCount,
  readonlyColumnKeys,
  target,
  values,
  visibleColumns,
  visibleRecords,
}: {
  getCellValue: (
    record: TRecord,
    columnKey: string,
  ) => string | null | undefined;
  blankRowCount: number;
  readonlyColumnKeys: ReadonlySet<string>;
  target: readonly [number, number];
  values: readonly (readonly string[])[];
  visibleColumns: readonly LegacyIssuePasteColumn[];
  visibleRecords: readonly TRecord[];
}): LegacyIssuePastePlan<TRecord> {
  const [targetColumnIndex, targetRowIndex] = target;
  const startVisibleColumnIndex = Math.max(targetColumnIndex, 0);
  const edits: Array<LegacyIssuePasteEdit<TRecord>> = [];
  const creates: LegacyIssuePasteCreate[] = [];

  values.forEach((rowValues, rowOffset) => {
    const rowIndex = targetRowIndex + rowOffset;
    if (rowIndex < 0) return;
    if (rowIndex < blankRowCount) {
      const create = buildCreatePlanForBlankRow({
        blankRowCount,
        readonlyColumnKeys,
        rowIndex,
        rowValues,
        startVisibleColumnIndex,
        visibleColumns,
      });
      if (create) creates.push(create);
      return;
    }
    const record = visibleRecords[rowIndex - blankRowCount];
    if (!record) return;
    rowValues.forEach((rawValue, columnOffset) => {
      const column = visibleColumns[startVisibleColumnIndex + columnOffset];
      if (!column || readonlyColumnKeys.has(column.key)) return;
      const value = normalizeLegacyIssuePasteValue(rawValue, column);
      if (value === undefined) return;
      const previous = normalizePasteGridValue(
        getCellValue(record, column.key),
      );
      const next = normalizePasteGridValue(value);
      if (previous === next) return;
      edits.push({ columnKey: column.key, record, value });
    });
  });

  return {
    creates,
    edits,
  };
}

export function expandLegacyIssuePasteValuesForSelection({
  selection,
  target,
  values,
}: {
  selection: { height: number; width: number; x: number; y: number } | null;
  target: readonly [number, number];
  values: readonly (readonly string[])[];
}): readonly (readonly string[])[] {
  const firstValue = values[0]?.[0];
  if (firstValue === undefined) return values;
  if (values.length !== 1 || values[0]?.length !== 1) return values;
  if (!selection) return values;
  if (selection.x !== target[0] || selection.y !== target[1]) return values;
  const width = Math.max(1, Math.floor(selection.width));
  const height = Math.max(1, Math.floor(selection.height));
  if (width === 1 && height === 1) return values;
  return Array.from({ length: height }, () =>
    Array.from({ length: width }, () => firstValue),
  );
}

function buildCreatePlanForBlankRow({
  blankRowCount,
  readonlyColumnKeys,
  rowIndex,
  rowValues,
  startVisibleColumnIndex,
  visibleColumns,
}: {
  blankRowCount: number;
  readonlyColumnKeys: ReadonlySet<string>;
  rowIndex: number;
  rowValues: readonly string[];
  startVisibleColumnIndex: number;
  visibleColumns: readonly LegacyIssuePasteColumn[];
}): LegacyIssuePasteCreate | null {
  if (blankRowCount <= 0) return null;
  if (rowIndex >= blankRowCount) return null;
  const nextValues: Record<string, string | null> = {};
  rowValues.forEach((rawValue, columnOffset) => {
    const column = visibleColumns[startVisibleColumnIndex + columnOffset];
    if (!column || readonlyColumnKeys.has(column.key)) return;
    const value = normalizeLegacyIssuePasteValue(rawValue, column);
    if (value === undefined) return;
    nextValues[column.key] = value;
  });
  return Object.keys(nextValues).length > 0
    ? {
        rowIndex,
        values: nextValues,
      }
    : null;
}

export function normalizeLegacyIssuePasteValue(
  value: string,
  column: LegacyIssuePasteColumn,
): string | null | undefined {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (column.inputKind !== 'date') return value;
  return normalizeLegacyIssueDateInput(trimmed);
}

export function normalizeLegacyIssueDateInput(
  value: string,
): string | null | undefined {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!/^(?:\d{8}|\d{4}\s*(?:[-/.]|\s|\uB144))/.test(trimmed)) {
    return undefined;
  }
  const normalized = normalizeDateInputText(trimmed, 'iso', 'ko-KR');
  return normalized === null ? undefined : normalized || null;
}

function normalizePasteGridValue(value: string | null | undefined): string {
  return value ?? '';
}
