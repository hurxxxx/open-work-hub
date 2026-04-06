import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table';
import { useState, type ReactNode } from 'react';

import type { DataTableColumn, Density } from '../types';
import { cn } from '../utils/cn';
import { EmptyState } from './empty-state';
import { Skeleton } from './skeleton';

export interface DataTableProps<TData extends object> {
  columns: DataTableColumn<TData>[];
  rows: TData[];
  density?: Density;
  emptyState?: ReactNode;
  loading?: boolean;
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
    <div className="mb-2.5 flex items-center justify-between gap-3 max-[720px]:flex-col max-[720px]:items-start">
      <div className="grid gap-1">
        <strong className="text-[0.9rem] text-[var(--ui-color-ink)]">{title}</strong>
        {meta ? (
          <span className="text-[0.74rem] text-[var(--ui-color-ink-subtle)]">{meta}</span>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function DataTable<TData extends object>({
  columns,
  rows,
  density = 'dense',
  emptyState,
  loading = false,
  selection,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const rowPadding =
    density === 'dense' ? 'px-3 py-2 text-[0.84rem]' : 'px-4 py-3 text-[0.86rem]';

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
      <div className="grid gap-2 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-raised)] p-4">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-raised)] p-4">
        {emptyState ?? (
          <EmptyState
            title="No results"
            description="검색 조건을 조정하거나 다른 저장된 뷰를 선택해보세요."
          />
        )}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-raised)]">
      <div className="grid gap-3 p-3 min-[721px]:hidden">
        {table.getRowModel().rows.map((row) => {
          const rowId = selection?.getRowId?.(row.original);
          const isSelected =
            selection?.selectedRowId && rowId === selection.selectedRowId;

          return (
            <article
              key={row.id}
              className={cn(
                'grid gap-3 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-white px-3 py-2.5',
                selection?.onRowClick ? 'cursor-pointer active:scale-[0.995]' : '',
                isSelected ? 'border-[var(--ui-color-border-strong)] bg-[var(--ui-color-accent-weak)]' : '',
              )}
              onClick={() => selection?.onRowClick?.(row.original)}
            >
              {row.getVisibleCells().map((cell) => {
                const header = headersByColumnId.get(cell.column.id);

                return (
                  <div key={cell.id} className="grid gap-1.5">
                    <span className="text-[0.62rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                      {header
                        ? flexRender(header.column.columnDef.header, header.getContext())
                        : cell.column.id}
                    </span>
                    <div className="text-[0.84rem] text-[var(--ui-color-ink)]">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </div>
                  </div>
                );
              })}
            </article>
          );
        })}
      </div>

      <div className="hidden overflow-x-auto min-[721px]:block">
        <table className="w-full border-collapse">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-b-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)]">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className={cn(
                      rowPadding,
                      'text-left text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]',
                    )}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc' ? ' ↑' : null}
                    {header.column.getIsSorted() === 'desc' ? ' ↓' : null}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => {
              const rowId = selection?.getRowId?.(row.original);
              const isSelected =
                selection?.selectedRowId && rowId === selection.selectedRowId;

              return (
                <tr
                  key={row.id}
                  className={cn(
                    'border-b border-b-[var(--ui-color-border)] last:border-b-0',
                    selection?.onRowClick ? 'cursor-pointer hover:bg-[var(--ui-color-surface-subtle)]' : '',
                    isSelected ? 'bg-[var(--ui-color-accent-weak)]' : '',
                  )}
                  onClick={() => selection?.onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className={cn(rowPadding, 'align-top text-[var(--ui-color-ink)]')}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
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
