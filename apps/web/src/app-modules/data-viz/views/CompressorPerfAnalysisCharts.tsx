import { useMemo, useState } from 'react';
import type { Data, Layout } from 'plotly.js';
import Plot from 'react-plotly.js';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import type { PerfAnalysisResult, PerfAverage } from '../api/dataviz-api';
import {
  COMPRESSOR_PERF_CHART_PALETTE,
  DATA_VIZ_PLOT_COLORS,
} from './data-viz-colors';

const CHART_FIELDS = [
  'rpm',
  'pd',
  'ps',
  'pc',
  'cooling_cap_a',
  'cooling_cap_f',
  'power_kw',
  'vol_eff',
  'cop_sc',
  'torque',
  'heat_balance',
] as const;

const EXCAVATOR_GROUP_PREFIX = '굴삭기'; // i18n-exempt-line: legacy test group prefix

const CHART_PALETTE = COMPRESSOR_PERF_CHART_PALETTE;

export interface CompressorPerfAnalysisChartsProps {
  analysis: PerfAnalysisResult;
  capacity?: string;
}

export function CompressorPerfAnalysisCharts({
  analysis,
  capacity,
}: CompressorPerfAnalysisChartsProps) {
  const { t } = useTranslation('apps');
  const [excludedFamilies, setExcludedFamilies] = useState<string[]>([]);
  const isFixed155 = capacity === '155cc';
  const [excludeExcavator, setExcludeExcavator] = useState(false);
  const [excludeES, setExcludeES] = useState(false);

  const compFamilies = useMemo(() => {
    const set = new Set<string>();
    for (const row of analysis.comp_averages) {
      const family = String(row.comp_type ?? '').match(/^[A-Za-z]+/)?.[0];
      if (family) set.add(family);
    }
    return Array.from(set).sort();
  }, [analysis]);

  const toggleFamily = (family: string) =>
    setExcludedFamilies((previous) =>
      previous.includes(family)
        ? previous.filter((item) => item !== family)
        : [...previous, family],
    );

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="app-text-caption text-app-ink/65">
          {t('ai.dataViz.perf.chartFilters')}
        </span>
        {isFixed155 ? (
          <>
            <button
              type="button"
              onClick={() => setExcludeExcavator((value) => !value)}
              style={{ fontSize: '12px' }}
              className={cn(
                'rounded-full border px-2.5 py-0.5 leading-tight transition-colors',
                excludeExcavator
                  ? 'border-app-accent bg-app-accent text-app-accent-fg'
                  : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
              )}
            >
              {t('ai.dataViz.perf.excludeExcavator')}
            </button>
            <button
              type="button"
              onClick={() => setExcludeES((value) => !value)}
              style={{ fontSize: '12px' }}
              className={cn(
                'rounded-full border px-2.5 py-0.5 leading-tight transition-colors',
                excludeES
                  ? 'border-app-accent bg-app-accent text-app-accent-fg'
                  : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
              )}
            >
              {t('ai.dataViz.perf.excludeES')}
            </button>
          </>
        ) : compFamilies.length === 0 ? (
          <span style={{ fontSize: '12px' }} className="text-app-ink/45">
            {t('ai.dataViz.perf.noModelsToExclude')}
          </span>
        ) : (
          compFamilies.map((family) => (
            <button
              key={family}
              type="button"
              onClick={() => toggleFamily(family)}
              style={{ fontSize: '12px' }}
              className={cn(
                'rounded-full border px-2.5 py-0.5 leading-tight transition-colors',
                excludedFamilies.includes(family)
                  ? 'border-app-accent bg-app-accent text-app-accent-fg'
                  : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
              )}
            >
              {t('ai.dataViz.perf.excludeFamily', { family })}
            </button>
          ))
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {CHART_FIELDS.map((field) => (
          <AnalysisChart
            key={field}
            field={field}
            analysis={analysis}
            excludedFamilies={excludedFamilies}
            excludeExcavator={excludeExcavator}
            excludeES={excludeES}
          />
        ))}
      </div>
    </>
  );
}

function AnalysisChart({
  field,
  analysis,
  excludedFamilies = [],
  excludeExcavator = false,
  excludeES = false,
}: {
  field: (typeof CHART_FIELDS)[number];
  analysis: PerfAnalysisResult;
  excludedFamilies?: string[];
  excludeExcavator?: boolean;
  excludeES?: boolean;
}) {
  const { t } = useTranslation('apps');
  const isExcludedCompType = (compType: string): boolean => {
    const family = String(compType || '').match(/^[A-Za-z]+/)?.[0] ?? '';
    return family !== '' && excludedFamilies.includes(family);
  };
  const isExcludedGroup = (testGroup: unknown): boolean => {
    const name = String(testGroup ?? '').trim();
    if (excludeExcavator && name.startsWith(EXCAVATOR_GROUP_PREFIX)) {
      return true;
    }
    if (excludeES && name.startsWith('ES')) return true;
    return false;
  };

  const esGroups = Array.from(
    new Set([
      ...analysis.averages.map((item) => item.test_group),
      ...analysis.comp_averages.map((item) => item.test_group),
      ...analysis.latest.map((item) => item.test_group),
    ]),
  )
    .filter((group) => !isExcludedGroup(group))
    .sort();
  if (esGroups.length === 0) return null;

  const traces: Data[] = [
    {
      type: 'bar',
      name: t('ai.dataViz.perf.overallAverage'),
      x: esGroups,
      y: esGroups.map(
        (group) =>
          analysis.averages.find((item) => item.test_group === group)?.[
            field
          ] ?? null,
      ),
      marker: { color: CHART_PALETTE[0] },
    } as Data,
  ];

  const byComponent = new Map<string, PerfAverage[]>();
  for (const row of analysis.comp_averages) {
    const key = String(row.comp_type || t('ai.dataViz.perf.other'));
    if (isExcludedCompType(key)) continue;
    byComponent.set(key, [...(byComponent.get(key) ?? []), row]);
  }
  let paletteIdx = 1;
  for (const [component, rows] of byComponent) {
    traces.push({
      type: 'bar',
      name: component,
      x: esGroups,
      y: esGroups.map(
        (group) =>
          rows.find((item) => item.test_group === group)?.[field] ?? null,
      ),
      marker: {
        color: CHART_PALETTE[paletteIdx % CHART_PALETTE.length],
      },
    } as Data);
    paletteIdx += 1;
  }

  const latestBySerial = new Map<
    string,
    PerfAnalysisResult['latest'][number][]
  >();
  for (const row of analysis.latest) {
    const key = String(row.serial_no || '');
    if (!key) continue;
    if (isExcludedCompType(String(row.comp_type || ''))) continue;
    const existing = latestBySerial.get(key);
    if (existing) existing.push(row);
    else latestBySerial.set(key, [row]);
  }
  const latestSerials = Array.from(latestBySerial.entries()).slice(0, 5);
  for (const [serial, rows] of latestSerials) {
    traces.push({
      type: 'bar',
      name: `#${serial}`,
      x: esGroups,
      y: esGroups.map(
        (group) =>
          rows.find((item) => item.test_group === group)?.[field] ?? null,
      ),
      marker: {
        color: CHART_PALETTE[paletteIdx % CHART_PALETTE.length],
      },
    } as Data);
    paletteIdx += 1;
  }

  const layout: Partial<Layout> = {
    height: 220,
    margin: { t: 44, r: 12, b: 28, l: 48 },
    barmode: 'group',
    bargap: 0.35,
    bargroupgap: 0.08,
    showlegend: true,
    legend: {
      orientation: 'h',
      x: 0,
      y: 1.02,
      xanchor: 'left',
      yanchor: 'bottom',
      font: { size: 10, color: DATA_VIZ_PLOT_COLORS.axisText },
      bgcolor: DATA_VIZ_PLOT_COLORS.transparent,
    },
    plot_bgcolor: DATA_VIZ_PLOT_COLORS.plot,
    paper_bgcolor: DATA_VIZ_PLOT_COLORS.paper,
    xaxis: {
      tickfont: { size: 10, color: DATA_VIZ_PLOT_COLORS.axisText },
      showgrid: false,
      zeroline: false,
    },
    yaxis: {
      tickformat: ',~r',
      tickfont: { size: 10, color: DATA_VIZ_PLOT_COLORS.mutedAxisText },
      gridcolor: DATA_VIZ_PLOT_COLORS.lightGrid,
      zerolinecolor: DATA_VIZ_PLOT_COLORS.lightGrid,
      showline: false,
      automargin: true,
    },
  };

  return (
    <div className="rounded-2xl border border-app-border bg-app-surface">
      <div className="app-text-body-sm px-3 pt-2 font-bold text-app-ink">
        {t(`ai.dataViz.perf.metric.${field}`)}
      </div>
      <Plot
        data={traces}
        layout={layout}
        useResizeHandler
        style={{ width: '100%', height: '220px' }}
        config={{ displaylogo: false, responsive: true }}
      />
    </div>
  );
}
