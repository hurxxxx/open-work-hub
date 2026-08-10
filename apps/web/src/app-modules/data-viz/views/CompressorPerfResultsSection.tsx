import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Loader2, RefreshCw, Trash2 } from 'lucide-react';
import { EmptyState } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import type {
  PerfCategory,
  PerfRefrigerant,
  PerfRow,
} from '../api/dataviz-api';
import {
  formatPerfNumber,
  formatPerfValue,
  groupPerfRowsBySerial,
} from './compressor-perf-table-model';
import { COMPRESSOR_PERF_TABLE_CLASSES } from './data-viz-colors';

type FieldKey =
  | 'test_group'
  | 'comp_type'
  | 'serial_no'
  | 'test_date'
  | 'car_model'
  | 'engine_spec'
  | 'remarks'
  | 'source_file'
  | 'rpm'
  | 'pd'
  | 'td'
  | 'ps'
  | 'ts'
  | 'pc'
  | 'mass_flow'
  | 'vol_eff'
  | 'ocr'
  | 'cooling_cap_a'
  | 'cooling_cap_f'
  | 'power_kw'
  | 'cop_sc'
  | 'heat_balance'
  | 'torque';

type ResultColumnKey = FieldKey | 'index' | 'delete';

const VARIABLE_COLUMNS: Array<{
  key: ResultColumnKey;
  i18nKey: string;
}> = [
  { key: 'index', i18nKey: 'No' },
  { key: 'comp_type', i18nKey: 'componentModel' },
  { key: 'test_group', i18nKey: 'testGroup' },
  { key: 'serial_no', i18nKey: 'serialNo' },
  { key: 'car_model', i18nKey: 'carModel' },
  { key: 'engine_spec', i18nKey: 'engineSpec' },
  { key: 'rpm', i18nKey: 'rpm' },
  { key: 'pd', i18nKey: 'pd' },
  { key: 'td', i18nKey: 'td' },
  { key: 'ps', i18nKey: 'ps' },
  { key: 'ts', i18nKey: 'ts' },
  { key: 'pc', i18nKey: 'pc' },
  { key: 'mass_flow', i18nKey: 'massFlow' },
  { key: 'vol_eff', i18nKey: 'volEff' },
  { key: 'ocr', i18nKey: 'ocr' },
  { key: 'cooling_cap_a', i18nKey: 'capA' },
  { key: 'power_kw', i18nKey: 'power' },
  { key: 'cop_sc', i18nKey: 'cop' },
  { key: 'torque', i18nKey: 'torque' },
  { key: 'cooling_cap_f', i18nKey: 'capF' },
  { key: 'heat_balance', i18nKey: 'heatBal' },
  { key: 'test_date', i18nKey: 'testDate' },
  { key: 'remarks', i18nKey: 'remarks' },
  { key: 'delete', i18nKey: 'actions' },
];

const ELECTRIC_COLUMNS: Array<{
  key: ResultColumnKey;
  i18nKey: string;
}> = [
  { key: 'index', i18nKey: 'No' },
  { key: 'comp_type', i18nKey: 'componentModel' },
  { key: 'test_group', i18nKey: 'testGroup' },
  { key: 'serial_no', i18nKey: 'serialNo' },
  { key: 'rpm', i18nKey: 'rpm' },
  { key: 'pd', i18nKey: 'pd' },
  { key: 'ps', i18nKey: 'ps' },
  { key: 'td', i18nKey: 'td' },
  { key: 'ts', i18nKey: 'ts' },
  { key: 'cooling_cap_a', i18nKey: 'coolingCapacity' },
  { key: 'power_kw', i18nKey: 'power' },
  { key: 'cop_sc', i18nKey: 'copSc' },
  { key: 'vol_eff', i18nKey: 'volEff' },
  { key: 'mass_flow', i18nKey: 'refMassFlow' },
  { key: 'test_date', i18nKey: 'testDate' },
  { key: 'remarks', i18nKey: 'remarks' },
  { key: 'delete', i18nKey: 'actions' },
];

const UNIT_BY_KEY: Partial<Record<ResultColumnKey, string>> = {
  rpm: 'rpm',
  pd: 'kgf/cm²',
  td: '°C',
  ps: 'kgf/cm²',
  ts: '°C',
  pc: 'kgf/cm²',
  mass_flow: 'kg/h',
  vol_eff: '%',
  ocr: '%',
  cooling_cap_a: 'kcal/h',
  cooling_cap_f: 'kcal/h',
  power_kw: 'kW',
  cop_sc: '-',
  torque: 'N·m',
  heat_balance: '%',
};

const TEXT_FIELDS = new Set<ResultColumnKey>([
  'comp_type',
  'test_group',
  'serial_no',
  'car_model',
  'engine_spec',
  'test_date',
  'remarks',
  'source_file',
]);

export interface CompressorPerfResultsSectionProps {
  rows: PerfRow[];
  category: PerfCategory;
  refrigerant: PerfRefrigerant;
  capacity: string;
  loading: string | null;
  onRefresh: () => void | Promise<void>;
  onDownload: () => void | Promise<void>;
  onDelete: (rowId: string | undefined) => void | Promise<void>;
}

export function CompressorPerfResultsSection({
  rows,
  category,
  refrigerant,
  capacity,
  loading,
  onRefresh,
  onDownload,
  onDelete,
}: CompressorPerfResultsSectionProps) {
  const { t } = useTranslation('apps');
  const columns = category === 'electric' ? ELECTRIC_COLUMNS : VARIABLE_COLUMNS;

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          style={{ fontSize: '12px' }}
          className="inline-flex h-7 items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-2.5 text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
          onClick={() => void onRefresh()}
        >
          <RefreshCw size={13} />
          {t('ai.dataViz.perf.refresh')}
        </button>
        <button
          type="button"
          style={{ fontSize: '12px' }}
          className="inline-flex h-7 items-center gap-1.5 rounded-md border border-lime-300 bg-lime-100 px-2.5 text-lime-800 transition-colors hover:bg-lime-200"
          onClick={() => void onDownload()}
        >
          <Download size={13} />
          {t('ai.dataViz.perf.download')}
        </button>
      </div>
      <div
        style={{ fontSize: '12px' }}
        className="flex flex-wrap items-center gap-3 text-app-ink/65"
      >
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-sm bg-ui-warning/20 ring-1 ring-app-border" />
          {t('ai.dataViz.perf.legend.toleranceRefViolation')}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="font-semibold text-ui-danger">
            {t('ai.dataViz.perf.legend.textColor')}
          </span>
          {t('ai.dataViz.perf.legend.profileViolation')}
        </span>
      </div>
      <PerfDataTable
        rows={rows}
        columns={columns}
        loading={loading}
        onDelete={onDelete}
        category={category}
        refrigerant={refrigerant}
        capacity={capacity}
      />
    </section>
  );
}

function PerfDataTable({
  rows,
  columns,
  loading,
  onDelete,
  category,
  refrigerant,
  capacity,
}: {
  rows: PerfRow[];
  columns: Array<{ key: ResultColumnKey; i18nKey: string }>;
  loading: string | null;
  onDelete: (rowId: string | undefined) => void | Promise<void>;
  category: PerfCategory;
  refrigerant: PerfRefrigerant;
  capacity: string;
}) {
  const { t } = useTranslation('apps');

  const groupedRows = useMemo(() => groupPerfRowsBySerial(rows), [rows]);

  if (loading === 'rows')
    return (
      <div className="flex h-32 items-center justify-center">
        <Loader2 size={20} className="animate-spin text-app-accent" />
      </div>
    );
  const title = t('ai.dataViz.perf.tableTitle', {
    capacity: capacity || t(`ai.dataViz.perf.categories.${category}`),
    category: t(`ai.dataViz.perf.categories.${category}`),
    refrigerant: t(`ai.dataViz.perf.refrigerants.${refrigerant}`),
  });
  if (rows.length === 0)
    return (
      <div className="flex flex-col gap-0 overflow-hidden rounded-2xl border border-app-border bg-app-surface">
        <div className="app-text-body-sm border-b border-app-border bg-app-surface-sidebar px-4 py-2 text-center font-bold text-app-ink">
          {title}
        </div>
        <div className="px-4 py-6 text-center">
          <EmptyState title={t('ai.dataViz.perf.emptyRows')} />
        </div>
      </div>
    );
  return (
    <div className="overflow-hidden rounded-2xl border border-app-border bg-app-surface">
      <div className="app-text-body-sm border-b border-app-border bg-app-surface-sidebar px-4 py-2 text-center font-bold text-app-ink">
        {title}
      </div>
      <div className="overflow-auto custom-scrollbar">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-app-surface-sidebar">
              {columns.map((column) => (
                <th
                  key={String(column.key)}
                  className="app-text-caption whitespace-nowrap border border-app-border px-2 py-1.5 text-center font-semibold text-app-ink"
                >
                  {column.i18nKey === 'No'
                    ? 'No'
                    : t(`ai.dataViz.perf.fields.${column.i18nKey}`)}
                </th>
              ))}
            </tr>
            <tr className="bg-app-surface italic">
              {columns.map((column) => (
                <th
                  key={`unit-${String(column.key)}`}
                  className="app-text-caption whitespace-nowrap border border-app-border px-2 py-1 text-center font-normal text-app-ink/55"
                >
                  {UNIT_BY_KEY[column.key] ?? ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groupedRows.map(({ row, groupIndex, isGroupEnd }, index) => {
              const bgClass =
                groupIndex % 2 === 1
                  ? COMPRESSOR_PERF_TABLE_CLASSES.groupAltBg
                  : 'bg-app-surface';
              const cellRowBorder = isGroupEnd
                ? COMPRESSOR_PERF_TABLE_CLASSES.groupEndBorder
                : 'border-b border-b-app-border [border-bottom-style:dashed]';
              return (
                <tr
                  key={
                    row.id ??
                    `${row.serial_no ?? ''}-${row.test_group ?? ''}-${index}`
                  }
                  className={cn(bgClass, 'hover:bg-app-surface-hover')}
                >
                  {columns.map((column) => {
                    if (column.key === 'index')
                      return (
                        <td
                          key={String(column.key)}
                          className={cn(
                            'app-text-caption px-2 py-1 text-center tabular-nums text-app-ink/55',
                            cellRowBorder,
                          )}
                        >
                          {index + 1}
                        </td>
                      );
                    if (column.key === 'delete') {
                      return (
                        <td
                          key={String(column.key)}
                          className={cn('px-2 py-1 text-center', cellRowBorder)}
                        >
                          <button
                            type="button"
                            className="rounded-md p-1 text-ui-danger transition-colors hover:bg-app-surface-hover"
                            onClick={() => void onDelete(row.id)}
                            aria-label={t('ai.dataViz.perf.fields.actions')}
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      );
                    }
                    const warnKind = row.warnings?.[column.key as string];
                    const isText = TEXT_FIELDS.has(column.key);
                    return (
                      <td
                        key={String(column.key)}
                        className={cn(
                          'app-text-caption whitespace-nowrap px-2 py-1 text-app-ink',
                          isText ? 'text-left' : 'text-right tabular-nums',
                          warnKind === 'tol'
                            ? 'font-semibold text-ui-danger'
                            : '',
                          warnKind === 'ref'
                            ? 'bg-ui-warning/20 font-semibold'
                            : '',
                          cellRowBorder,
                        )}
                      >
                        {isText
                          ? formatPerfValue(row[column.key])
                          : formatPerfNumber(
                              row[column.key],
                              String(column.key),
                            )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
