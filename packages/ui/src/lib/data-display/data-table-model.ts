import type { Density } from '../types';

type DataTableSortState = false | 'asc' | 'desc';

interface DataTableSelectionLookup<TData> {
  selectedRowId?: string;
  getRowId?: (row: TData) => string;
}

export function getDataTableRowPadding(density: Density): string {
  return density === 'dense'
    ? 'px-3 py-1.5 text-[length:var(--ui-text-body-sm)]'
    : 'px-4 py-3 text-[length:var(--ui-text-body)]';
}

export function isDataTableRowSelected<TData>(
  row: TData,
  selection?: DataTableSelectionLookup<TData>,
): boolean {
  const rowId = selection?.getRowId?.(row);
  return Boolean(selection?.selectedRowId && rowId === selection.selectedRowId);
}

export function getDataTableSortIndicator(
  sortState: DataTableSortState,
): string {
  if (sortState === 'asc') return ' ↑';
  if (sortState === 'desc') return ' ↓';
  return '';
}

export function shouldActivateDataTableRowKey(key: string): boolean {
  return key === 'Enter' || key === ' ';
}
