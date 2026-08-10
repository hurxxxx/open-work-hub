import type { Data, Layout } from 'plotly.js';

import { MEASURE_ITEMS, type MeasureItem } from './sysperf-items';
import { DATA_VIZ_PLOT_COLORS, SYSPERF_GRAPH_COLORS } from './data-viz-colors';

export type SysPerfGraphSeries = (number | null)[];

export interface SysPerfGraphDataCache {
  data: Record<string, SysPerfGraphSeries>;
  units: Record<string, string>;
  error?: string;
}

export interface SysPerfGraphAxisSetting {
  mn: string;
  mx: string;
  dv: string;
}

export interface SysPerfGraphResolvedAxisRange {
  range: [number, number];
  dtick: number;
  autorange: false;
}

export interface SysPerfGraphFileRef {
  file_id: number;
}

export interface SysPerfGraphAxisInfo {
  idx: number;
  item: MeasureItem;
  unit: string;
  yIdx: number;
  color: string;
}

export interface SysPerfGraphMissingItem {
  fi: number;
  nm: string;
  n: number;
}

export interface SysPerfGraphPlotModel {
  traces: Data[];
  layout: Partial<Layout>;
  axisInfo: SysPerfGraphAxisInfo[];
  missing: SysPerfGraphMissingItem[];
}

export interface SysPerfCompareGraphModel {
  traces: Data[];
  layout: Partial<Layout>;
  item: MeasureItem | null;
}

export interface SysPerfGraphLabels {
  axisTitle: (args: { index: number; name: string; unit: string }) => string;
  traceFileSuffix: (args: { index: number }) => string;
  fileLabel: (args: { index: number }) => string;
  comparePlotTitle: (args: { name: string }) => string;
  timeAxisTitle: string;
}

const COLORS = SYSPERF_GRAPH_COLORS;

export const SYS_PERF_GRAPH_DEFAULT_AXIS_SETTING: SysPerfGraphAxisSetting = {
  mn: '',
  mx: '',
  dv: '10',
};

export function stdKey(item: MeasureItem): string {
  return `${item.n}_${item.nm}`;
}

export function unitOf(
  item: MeasureItem,
  items: MeasureItem[] = MEASURE_ITEMS,
  fallbackUnit: string,
): string {
  if (item.u) return item.u;
  const parent = items.find(
    (m) => m.cs && m.n < item.n && m.n + (m.cs || 0) > item.n,
  );
  return parent?.u || fallbackUnit;
}

export function augmentSysPerfGraphData(
  data: Record<string, SysPerfGraphSeries>,
  items: MeasureItem[] = MEASURE_ITEMS,
): Record<string, SysPerfGraphSeries> {
  const out: Record<string, SysPerfGraphSeries> = { ...data };
  items.forEach((item) => {
    if (!item.avg || !item.grp) return;
    const key = stdKey(item);
    if (out[key] && out[key].some((v) => v !== null)) return;
    const subs = items.filter((m) => m.sub === item.grp);
    const subData = subs
      .map((s) => out[stdKey(s)])
      .filter((d): d is SysPerfGraphSeries => !!d && d.length > 0);
    if (!subData.length) return;
    const len = subData[0].length;
    const avg: SysPerfGraphSeries = [];
    for (let i = 0; i < len; i++) {
      let sum = 0;
      let cnt = 0;
      subData.forEach((sd) => {
        const v = sd[i];
        if (v !== null && v !== undefined) {
          sum += v;
          cnt++;
        }
      });
      avg.push(cnt > 0 ? sum / cnt : null);
    }
    out[key] = avg;
  });
  return out;
}

export function createSysPerfGraphDefaultAxisSetting(): SysPerfGraphAxisSetting {
  return { ...SYS_PERF_GRAPH_DEFAULT_AXIS_SETTING };
}

export function resolveSysPerfGraphAxisRange(
  setting: SysPerfGraphAxisSetting | undefined,
): SysPerfGraphResolvedAxisRange | null {
  if (!setting || setting.mn === '' || setting.mx === '') return null;
  const min = Number.parseFloat(setting.mn);
  const max = Number.parseFloat(setting.mx);
  const divide = Number.parseInt(setting.dv, 10);
  if (
    !Number.isFinite(min) ||
    !Number.isFinite(max) ||
    !Number.isFinite(divide) ||
    max <= min ||
    divide <= 0
  ) {
    return null;
  }
  return {
    range: [min, max] as [number, number],
    dtick: (max - min) / divide,
    autorange: false,
  };
}

export function buildSysPerfGraphPlotModel({
  selected,
  files,
  cache,
  appliedX,
  appliedY,
  labels,
  fallbackUnit,
  items = MEASURE_ITEMS,
}: {
  selected: number[];
  files: SysPerfGraphFileRef[];
  cache: Record<number, SysPerfGraphDataCache>;
  appliedX: SysPerfGraphAxisSetting;
  appliedY: Record<number, SysPerfGraphAxisSetting>;
  labels: SysPerfGraphLabels;
  fallbackUnit: string;
  items?: MeasureItem[];
}): SysPerfGraphPlotModel {
  const traces: Data[] = [];
  const axisInfo: SysPerfGraphAxisInfo[] = [];
  const missing: SysPerfGraphMissingItem[] = [];
  const yAxes: Record<string, object> = {};
  let traceCount = 0;

  selected.forEach((itemN, idx) => {
    const item = items.find((m) => m.n === itemN);
    if (!item) return;
    const unit = unitOf(item, items, fallbackUnit);
    const yIdx = idx + 1;
    const yName = yIdx === 1 ? 'yaxis' : `yaxis${yIdx}`;
    const yRef = yIdx === 1 ? 'y' : `y${yIdx}`;
    const firstColor = COLORS[traceCount % COLORS.length];
    const range = resolveSysPerfGraphAxisRange(appliedY[itemN]);
    yAxes[yName] = {
      title: {
        text: labels.axisTitle({ index: yIdx, name: item.nm, unit }),
        font: { size: 12, color: firstColor },
        standoff: 6,
      },
      tickfont: { color: firstColor, size: 11 },
      side: 'right',
      overlaying: yIdx > 1 ? 'y' : undefined,
      showgrid: yIdx === 1,
      gridcolor: DATA_VIZ_PLOT_COLORS.graphGrid,
      gridwidth: 1,
      ...(range ?? { autorange: true }),
    };
    axisInfo.push({ idx, item, unit, yIdx, color: firstColor });

    files.forEach((file, fi) => {
      const gd = cache[file.file_id];
      if (!gd || gd.error) return;
      const data = augmentSysPerfGraphData(gd.data, items);
      const arr = data[stdKey(item)] || data[item.nm];
      if (!arr) {
        missing.push({ fi: fi + 1, nm: item.nm, n: item.n });
        return;
      }
      const color = COLORS[traceCount % COLORS.length];
      traceCount++;
      traces.push({
        x: data.Time || data['0_Time'] || [],
        y: arr,
        type: 'scattergl',
        mode: 'lines',
        name:
          item.nm +
          (files.length > 1 ? labels.traceFileSuffix({ index: fi + 1 }) : ''),
        yaxis: yRef,
        line: { color, width: 1.5 },
      } as Data);
    });
  });

  const nAxes = Object.keys(yAxes).length;
  const axisGap = 0.065;
  const domLeft = 0.03;
  let domRight = 1 - axisGap * Math.max(0, nAxes - 1) - 0.04;
  if (domRight < 0.5) domRight = 0.5;
  const xRange = resolveSysPerfGraphAxisRange(appliedX);
  const layout: Record<string, unknown> = {
    xaxis: {
      title: { text: labels.timeAxisTitle, font: { size: 13 } },
      gridcolor: DATA_VIZ_PLOT_COLORS.graphGrid,
      gridwidth: 1,
      domain: [domLeft, domRight],
      ...(xRange ?? { autorange: true }),
    },
    margin: { l: 30, r: 40, t: 20, b: 50 },
    paper_bgcolor: DATA_VIZ_PLOT_COLORS.transparent,
    plot_bgcolor: DATA_VIZ_PLOT_COLORS.transparent,
    hovermode: 'x unified',
    legend: { font: { size: 12 }, orientation: 'h', y: -0.15 },
    autosize: true,
  };
  Object.keys(yAxes).forEach((key, i) => {
    const ax = yAxes[key] as Record<string, unknown>;
    if (i === 0) {
      ax.anchor = 'x';
    } else {
      ax.anchor = 'free';
      ax.position = Math.min(1, domRight + i * axisGap);
    }
    layout[key] = ax;
  });
  return {
    traces,
    layout: layout as unknown as Partial<Layout>,
    axisInfo,
    missing,
  };
}

export function buildSysPerfCompareGraphModel({
  itemNumber,
  files,
  cache,
  labels,
  items = MEASURE_ITEMS,
}: {
  itemNumber: number | null;
  files: SysPerfGraphFileRef[];
  cache: Record<number, SysPerfGraphDataCache>;
  labels: SysPerfGraphLabels;
  items?: MeasureItem[];
}): SysPerfCompareGraphModel {
  if (itemNumber == null) return { traces: [], layout: {}, item: null };
  const item = items.find((m) => m.n === itemNumber) ?? null;
  if (!item) return { traces: [], layout: {}, item: null };
  const traces: Data[] = [];
  files.forEach((file, i) => {
    const gd = cache[file.file_id];
    if (!gd || gd.error) return;
    const data = augmentSysPerfGraphData(gd.data, items);
    const arr = data[stdKey(item)] || data[item.nm];
    if (!arr) return;
    traces.push({
      x: data.Time || data['0_Time'] || [],
      y: arr,
      type: 'scattergl',
      mode: 'lines',
      name: labels.fileLabel({ index: i + 1 }),
      line: { color: COLORS[i % COLORS.length], width: 2 },
    } as Data);
  });
  return {
    traces,
    item,
    layout: {
      title: {
        text: labels.comparePlotTitle({ name: item.nm }),
        font: { size: 15 },
      },
      xaxis: {
        title: { text: labels.timeAxisTitle },
        gridcolor: DATA_VIZ_PLOT_COLORS.compareGrid,
      },
      yaxis: {
        title: { text: item.nm + (item.u ? ` (${item.u})` : '') },
        gridcolor: DATA_VIZ_PLOT_COLORS.compareGrid,
      },
      margin: { l: 60, r: 20, t: 40, b: 50 },
      paper_bgcolor: DATA_VIZ_PLOT_COLORS.transparent,
      plot_bgcolor: DATA_VIZ_PLOT_COLORS.transparent,
      legend: { font: { size: 12 } },
      autosize: true,
    },
  };
}
