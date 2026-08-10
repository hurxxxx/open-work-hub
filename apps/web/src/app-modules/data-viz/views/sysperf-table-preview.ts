export interface SysPerfSheetPreview {
  columns: string[];
  data: Record<string, (number | null)[]>;
  total_rows: number;
}

export interface SysPerfSheetPreviewCell {
  column: string;
  value: string;
}

export interface SysPerfSheetPreviewRow {
  index: number;
  cells: SysPerfSheetPreviewCell[];
}

export function formatSysPerfPreviewValue(
  value: number | null | undefined,
): string {
  if (value == null || !Number.isFinite(value)) return '';
  return String(Number(value.toFixed(3)));
}

export function countSysPerfPreviewRows(preview: SysPerfSheetPreview): number {
  return Math.min(
    preview.total_rows,
    ...preview.columns.map((column) => preview.data[column]?.length ?? 0),
  );
}

export function buildSysPerfSheetPreviewRows(
  preview: SysPerfSheetPreview,
): SysPerfSheetPreviewRow[] {
  const rowCount = countSysPerfPreviewRows(preview);
  return Array.from({ length: rowCount }).map((_, rowIndex) => ({
    index: rowIndex + 1,
    cells: preview.columns.map((column) => ({
      column,
      value: formatSysPerfPreviewValue(preview.data[column]?.[rowIndex]),
    })),
  }));
}
