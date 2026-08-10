import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table';
import { useState, type KeyboardEvent, type ReactNode } from 'react';

import type { DataTableColumn, Density } from '../types';
import { cn } from '../utils/cn';
import { Skeleton } from './skeleton';
import {
  getDataTableRowPadding,
  getDataTableSortIndicator,
  isDataTableRowSelected,
  shouldActivateDataTableRowKey,
} from './data-table-model';

export interface DataTableProps<TData extends object> {
  columns: DataTableColumn<TData>[];
  rows: TData[];
  density?: Density;
  emptyState?: ReactNode;
  loading?: boolean;
  loadingLabel?: string;
  selection?: {
    selectedRowId?: string;
    onRowClick?: (row: TData) => void;
    getRowId?: (row: TData) => string;
  };
}

export interface DataTableToolbarProps {
  title: string;
  meta?: string;
  actions?: ReactNode;
}

export function DataTableToolbar({
  title,
  meta,
  actions,
}: DataTableToolbarProps) {
  return (
    <div className="mb-2 flex items-center justify-between gap-3 max-[720px]:flex-col max-[720px]:items-start">
      <div className="grid gap-0.5">
        <strong className="text-[length:var(--ui-text-body-sm)] text-[var(--ui-color-ink)]">
          {title}
        </strong>
        {meta ? (
          <span className="text-[length:var(--ui-text-caption)] text-[var(--ui-color-ink-subtle)]">
            {meta}
          </span>
        ) : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}

export function DataTable<TData extends object>({
  columns,
  rows,
  density = 'dense',
  emptyState,
  loading = false,
  loadingLabel,
  selection,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const rowPadding = getDataTableRowPadding(density);

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: selection?.getRowId,
  });
  const headersByColumnId = new Map(
    table.getFlatHeaders().map((header) => [header.column.id, header]),
  );

  if (loading) {
    return (
      <output
        aria-label={loadingLabel}
        className="grid gap-2 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-ui-surface-raised p-4"
      >
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </output>
    );
  }

  if (!rows.length) {
    return (
      <div className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-ui-surface-raised p-4">
        {emptyState ?? null}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-ui-surface-raised">
      <div className="grid gap-3 p-3 min-[721px]:hidden">
        {table.getRowModel().rows.map((row) => {
          const isSelected = isDataTableRowSelected(row.original, selection);
          const handleRowAction = () => selection?.onRowClick?.(row.original);
          const rowInteractionProps = selection?.onRowClick
            ? {
                onClick: handleRowAction,
                onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
                  if (!shouldActivateDataTableRowKey(event.key)) return;
                  event.preventDefault();
                  handleRowAction();
                },
                role: 'button' as const,
                tabIndex: 0,
              }
            : {};

          return (
            <div
              key={row.id}
              className={cn(
                'grid gap-3 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-ui-surface-raised px-3 py-2.5',
                selection?.onRowClick
                  ? 'cursor-pointer active:scale-[0.995]'
                  : '',
                isSelected
                  ? 'border-[var(--ui-color-border-strong)] bg-ui-accent-weak'
                  : '',
              )}
              {...rowInteractionProps}
            >
              {row.getVisibleCells().map((cell) => {
                const header = headersByColumnId.get(cell.column.id);

                return (
                  <div key={cell.id} className="grid gap-1.5">
                    <span className="text-[length:var(--ui-text-overline)] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                      {header
                        ? flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )
                        : cell.column.id}
                    </span>
                    <div className="text-[length:var(--ui-text-body-sm)] text-[var(--ui-color-ink)]">
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      <div className="hidden overflow-x-auto min-[721px]:block">
        <table className="w-full border-collapse">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr
                key={headerGroup.id}
                className="border-b border-b-[var(--ui-color-border)] bg-ui-surface-subtle"
              >
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className={cn(
                      rowPadding,
                      'text-left text-[length:var(--ui-text-overline)] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]',
                    )}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                    {getDataTableSortIndicator(header.column.getIsSorted())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => {
              const isSelected = isDataTableRowSelected(
                row.original,
                selection,
              );

              return (
                <tr
                  key={row.id}
                  className={cn(
                    'border-b border-b-[var(--ui-color-border)] last:border-b-0',
                    selection?.onRowClick
                      ? 'cursor-pointer hover:bg-ui-surface-subtle'
                      : '',
                    isSelected ? 'bg-ui-accent-weak' : '',
                  )}
                  onClick={() => selection?.onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className={cn(
                        rowPadding,
                        'align-top text-[var(--ui-color-ink)]',
                      )}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
