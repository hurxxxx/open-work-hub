import { useMemo } from 'react';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { EmptyState } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import type { PerfAnalysisResult, PerfAverage } from '../api/dataviz-api';
import { CompressorPerfAnalysisCharts } from './CompressorPerfAnalysisCharts';
import {
  formatPerfNumber,
  formatPerfValue,
  groupPerfAverages,
} from './compressor-perf-table-model';
import { COMPRESSOR_PERF_TABLE_CLASSES } from './data-viz-colors';

const ANALYSIS_FIELDS = [
  'rpm',
  'pd',
  'td',
  'ps',
  'ts',
  'pc',
  'mass_flow',
  'vol_eff',
  'ocr',
  'cooling_cap_a',
  'power_kw',
  'cop_sc',
  'torque',
  'cooling_cap_f',
  'heat_balance',
] as const;

export interface CompressorPerfAnalysisSectionProps {
  analysis: PerfAnalysisResult | null;
  loading: boolean;
  capacity?: string;
}

export function CompressorPerfAnalysisSection({
  analysis,
  loading,
  capacity,
}: CompressorPerfAnalysisSectionProps) {
  const { t } = useTranslation('apps');
  if (loading)
    return (
      <div className="flex h-32 items-center justify-center">
        <Loader2 size={20} className="animate-spin text-app-accent" />
      </div>
    );
  if (!analysis)
    return <EmptyState title={t('ai.dataViz.perf.selectFilters')} />;
  return (
    <div className="flex flex-col gap-4">
      <AverageTable
        title={t('ai.dataViz.perf.overallAverage')}
        rows={analysis.averages}
      />
      <AverageTable
        title={t('ai.dataViz.perf.componentAverage')}
        rows={analysis.comp_averages}
        showComponent
      />
      <AverageTable
        title={t('ai.dataViz.perf.latestUploads')}
        rows={analysis.latest as unknown as PerfAverage[]}
        showSerial
      />
      <CompressorPerfAnalysisCharts analysis={analysis} capacity={capacity} />
    </div>
  );
}

function AverageTable({
  title,
  rows,
  showComponent = false,
  showSerial = false,
}: {
  title: string;
  rows: PerfAverage[];
  showComponent?: boolean;
  showSerial?: boolean;
}) {
  const { t } = useTranslation('apps');

  const groupedRows = useMemo(
    () => groupPerfAverages(rows, { showComponent, showSerial }),
    [rows, showComponent, showSerial],
  );

  if (rows.length === 0) return null;
  return (
    <section className="overflow-hidden rounded-2xl border border-app-border bg-app-surface">
      <div className="app-text-body-sm border-b border-app-border bg-app-surface-sidebar px-3 py-2 font-semibold text-app-ink">
        {title}
      </div>
      <div className="overflow-auto custom-scrollbar">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-app-border">
              {showComponent && (
                <th className="app-text-caption px-2 py-1.5 text-center font-medium text-app-ink/65">
                  {t('ai.dataViz.perf.fields.componentModel')}
                </th>
              )}
              {showSerial && (
                <th className="app-text-caption px-2 py-1.5 text-center font-medium text-app-ink/65">
                  {t('ai.dataViz.perf.fields.serialNo')}
                </th>
              )}
              <th className="app-text-caption px-2 py-1.5 text-center font-medium text-app-ink/65">
                ES
              </th>
              <th className="app-text-caption px-2 py-1.5 text-center font-medium text-app-ink/65">
                n
              </th>
              {ANALYSIS_FIELDS.map((field) => (
                <th
                  key={field}
                  className="app-text-caption px-2 py-1.5 text-center font-medium text-app-ink/65"
                >
                  {t(`ai.dataViz.perf.metric.${field}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groupedRows.map(({ row, groupIndex, isGroupEnd }, index) => {
              const isLastRow = index === groupedRows.length - 1;
              const bgClass =
                groupIndex % 2 === 1
                  ? COMPRESSOR_PERF_TABLE_CLASSES.groupAltBg
                  : 'bg-app-surface';
              const cellRowBorder = isLastRow
                ? ''
                : isGroupEnd
                  ? COMPRESSOR_PERF_TABLE_CLASSES.groupEndBorder
                  : 'border-b border-b-app-border [border-bottom-style:dashed]';
              return (
                <tr
                  key={`${row.comp_type ?? ''}-${row.serial_no ?? ''}-${row.test_group}-${index}`}
                  className={bgClass}
                >
                  {showComponent && (
                    <td
                      className={cn(
                        'app-text-caption px-2 py-1 text-center text-app-ink',
                        cellRowBorder,
                      )}
                    >
                      {formatPerfValue(row.comp_type)}
                    </td>
                  )}
                  {showSerial && (
                    <td
                      className={cn(
                        'app-text-caption px-2 py-1 text-center text-app-ink',
                        cellRowBorder,
                      )}
                    >
                      {formatPerfValue(row.serial_no)}
                    </td>
                  )}
                  <td
                    className={cn(
                      'app-text-caption px-2 py-1 text-center text-app-ink',
                      cellRowBorder,
                    )}
                  >
                    {formatPerfValue(row.test_group)}
                  </td>
                  <td
                    className={cn(
                      'app-text-caption px-2 py-1 text-center tabular-nums text-app-ink',
                      cellRowBorder,
                    )}
                  >
                    {formatPerfValue(row.count)}
                  </td>
                  {ANALYSIS_FIELDS.map((field) => (
                    <td
                      key={field}
                      className={cn(
                        'app-text-caption px-2 py-1 text-center tabular-nums text-app-ink',
                        cellRowBorder,
                      )}
                    >
                      {formatPerfNumber(row[field], field)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
