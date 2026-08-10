import { useMemo } from 'react';

import {
  LegacyIssueDataGrid,
  type LegacyIssueGridColumn,
} from './LegacyIssueDataGrid';
import type { LegacyIssueReportGridColumn } from '../api/legacy-issue-assistant-report-api';

interface ReportGridRecord {
  id: string;
  values: Record<string, unknown>;
}

export function LegacyIssueReportDataGrid({
  columns,
  emptyLabel,
  loading,
  loadingLabel,
  layoutId,
  rows,
}: {
  columns: readonly LegacyIssueReportGridColumn[];
  emptyLabel: string;
  loading: boolean;
  loadingLabel: string;
  layoutId: string;
  rows: readonly Record<string, unknown>[];
}) {
  const normalizedColumns = useMemo(
    () => buildLegacyIssueReportGridColumns(columns, rows),
    [columns, rows],
  );
  const records = useMemo(
    () =>
      rows.map((values, index) => ({
        id: `report-row-${index}`,
        values,
      })),
    [rows],
  );

  return (
    <LegacyIssueDataGrid<ReportGridRecord>
      columns={normalizedColumns}
      emptyLabel={emptyLabel}
      getCellValue={(record, columnKey) =>
        formatLegacyIssueReportGridCell(record.values[columnKey])
      }
      layoutId={layoutId}
      loading={loading}
      loadingLabel={loadingLabel}
      readonlyColumnKeys={normalizedColumns.map((column) => column.key)}
      records={records}
    />
  );
}

export function buildLegacyIssueReportGridColumns(
  columns: readonly LegacyIssueReportGridColumn[],
  rows: readonly Record<string, unknown>[],
): LegacyIssueGridColumn[] {
  const declared = columns
    .map((column) => {
      const key = (column.key ?? column.name ?? '').trim();
      return {
        key,
        label: (column.label ?? column.name ?? key).trim(),
      };
    })
    .filter((column) => column.key);
  const columnKeys =
    declared.length > 0
      ? declared
      : Array.from(new Set(rows.flatMap((row) => Object.keys(row))), (key) => ({
          key,
          label: key,
        }));
  const seen = new Set<string>();
  return columnKeys
    .filter((column) => {
      if (seen.has(column.key)) return false;
      seen.add(column.key);
      return true;
    })
    .map((column) => ({
      key: column.key,
      title: column.label || column.key,
      width: estimateColumnWidth(column.key, column.label, rows),
    }));
}

export function formatLegacyIssueReportGridCell(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function estimateColumnWidth(
  key: string,
  label: string,
  rows: readonly Record<string, unknown>[],
): number {
  const sampleLength = rows
    .slice(0, 20)
    .reduce(
      (longest, row) =>
        Math.max(
          longest,
          formatLegacyIssueReportGridCell(row[key])?.length ?? 0,
        ),
      Math.max(key.length, label.length),
    );
  return Math.max(120, Math.min(360, 28 + sampleLength * 8));
}
