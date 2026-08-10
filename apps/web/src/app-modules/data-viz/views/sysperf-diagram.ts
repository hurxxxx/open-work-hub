import type { Data, Layout } from 'plotly.js';

import type {
  SysPerfCycleData,
  SysPerfPhDiagram,
  SysPerfRefrigerantPropRow,
  SysPerfTsDiagram,
} from '../api/dataviz-api';
import {
  DATA_VIZ_PLOT_COLORS,
  SYSPERF_DIAGRAM_COLORS,
} from './data-viz-colors';

export const SYS_PERF_KGFCM2_TO_KPA = 98.0665;

export const SYS_PERF_DIAGRAM_POINTS = [
  { key: 'Comp In', label: 'Comp In', stdP: 'Ps', stdT: 'Ts' }, // i18n-exempt-line: thermodynamic point label
  { key: 'Comp Out', label: 'Comp Out', stdP: 'PEO', stdT: 'TD' }, // i18n-exempt-line: thermodynamic point label
  { key: 'Condenser In', label: 'Condenser In', stdP: 'PCI', stdT: 'TCI' }, // i18n-exempt-line: thermodynamic point label
  { key: 'Condenser Out', label: 'Condenser Out', stdP: 'PCO', stdT: 'TCO' }, // i18n-exempt-line: thermodynamic point label
  { key: 'TXV In', label: 'TXV In', stdP: 'PEI', stdT: 'TEI' }, // i18n-exempt-line: thermodynamic point label
  { key: 'TXV Out', label: 'TXV Out', stdP: 'PEO', stdT: 'TEO' }, // i18n-exempt-line: thermodynamic point label
  { key: 'Evap In', label: 'HVAC In', stdP: 'PEI', stdT: 'E/TEI' }, // i18n-exempt-line: thermodynamic point label
  { key: 'Evap Out', label: 'HVAC Out', stdP: 'PEO', stdT: 'E/TEO' }, // i18n-exempt-line: thermodynamic point label
] as const;

export const SYS_PERF_DIAGRAM_POINT_ORDER = SYS_PERF_DIAGRAM_POINTS.map(
  (p) => p.key,
);

export const SYS_PERF_TS_AXIS_DEFAULTS = {
  xMin: 0.5,
  xMax: 2.0,
  xTick: 0.1,
  yMin: -30,
  yMax: 150,
  yTick: 10,
};

export type SysPerfTsAxis = typeof SYS_PERF_TS_AXIS_DEFAULTS;

export type SysPerfDiagramCycleCacheEntry = SysPerfCycleData & { time: number };

export interface SysPerfDiagramTableRow {
  no: number;
  label: string;
  p: string;
  t: string;
  h: string;
  sh: string;
  sc: string;
  notes: string[];
}

export interface SysPerfDiagramPlotModel {
  traces: Data[];
  layout: Partial<Layout>;
}

export interface SysPerfDiagramPlotLabels {
  saturationCurve: string;
  criticalPoint: string;
  cycleFileName: (args: { index: number; time: number }) => string;
  axes: {
    enthalpy: string;
    pressure: string;
    entropy: string;
    temperature: string;
  };
  phTitle: (args: { refrigerant: string }) => string;
  tsTitle: (args: { refrigerant: string }) => string;
}

const DIAGRAM_FONT = "'Pretendard', 'Malgun Gothic', sans-serif";
const CYCLE_COLORS = SYSPERF_DIAGRAM_COLORS.cycle;

export function normalizeSysPerfTsAxis(axis: SysPerfTsAxis): SysPerfTsAxis {
  const out = { ...axis };
  if (!Number.isFinite(out.xMin)) out.xMin = SYS_PERF_TS_AXIS_DEFAULTS.xMin;
  if (!Number.isFinite(out.xMax)) out.xMax = SYS_PERF_TS_AXIS_DEFAULTS.xMax;
  if (!Number.isFinite(out.yMin)) out.yMin = SYS_PERF_TS_AXIS_DEFAULTS.yMin;
  if (!Number.isFinite(out.yMax)) out.yMax = SYS_PERF_TS_AXIS_DEFAULTS.yMax;
  if (out.xMin >= out.xMax) {
    out.xMin = SYS_PERF_TS_AXIS_DEFAULTS.xMin;
    out.xMax = SYS_PERF_TS_AXIS_DEFAULTS.xMax;
  }
  if (out.yMin >= out.yMax) {
    out.yMin = SYS_PERF_TS_AXIS_DEFAULTS.yMin;
    out.yMax = SYS_PERF_TS_AXIS_DEFAULTS.yMax;
  }
  if (!Number.isFinite(out.xTick) || !(out.xTick > 0)) {
    out.xTick = SYS_PERF_TS_AXIS_DEFAULTS.xTick;
  }
  if (!Number.isFinite(out.yTick) || !(out.yTick > 0)) {
    out.yTick = SYS_PERF_TS_AXIS_DEFAULTS.yTick;
  }
  return out;
}

export function interpolateEnthalpy(
  props: SysPerfRefrigerantPropRow[],
  temperature: number | null | undefined,
  pressureKpa: number,
): number | null {
  if (!props.length || temperature == null) return null;
  let pCrit = 0;
  props.forEach((p) => {
    if ((p.sat_pressure_kpa || 0) > pCrit) pCrit = p.sat_pressure_kpa || 0;
  });
  let below: SysPerfRefrigerantPropRow | null = null;
  let above: SysPerfRefrigerantPropRow | null = null;
  for (const p of props) {
    if (p.temperature == null) continue;
    if (p.temperature <= temperature) below = p;
    if (p.temperature >= temperature && above === null) above = p;
  }
  if (!below && !above) return null;
  if (!below) below = above;
  if (!above) above = below;
  if (!below || !above) return null;
  const bt = below.temperature ?? 0;
  const at = above.temperature ?? 0;
  const frac = at !== bt ? (temperature - bt) / (at - bt) : 0;
  const satPb = below.sat_pressure_kpa || 0;
  const satPa = above.sat_pressure_kpa || 0;
  const satP = satPb + frac * (satPa - satPb);
  let useLiquid: boolean;
  if (pressureKpa >= pCrit * 0.99) useLiquid = false;
  else if (pressureKpa > satP) useLiquid = true;
  else useLiquid = false;
  if (useLiquid) {
    const hB = below.liq_enthalpy || 0;
    const hA = above.liq_enthalpy || 0;
    return hB + frac * (hA - hB);
  }
  const hB = below.vap_enthalpy || 0;
  const hA = above.vap_enthalpy || 0;
  return hB + frac * (hA - hB);
}

export function interpolateEntropy(
  props: SysPerfRefrigerantPropRow[],
  temperature: number | null | undefined,
  pressureKpa: number,
): number | null {
  if (!props.length || temperature == null) return null;
  let below: SysPerfRefrigerantPropRow | null = null;
  let above: SysPerfRefrigerantPropRow | null = null;
  for (const p of props) {
    if (p.temperature == null) continue;
    if (p.temperature <= temperature) below = p;
    if (p.temperature >= temperature && above === null) above = p;
  }
  if (!below && !above) return null;
  if (!below) return above?.vap_entropy ?? null;
  if (!above) return below.vap_entropy ?? null;
  if (below.temperature === above.temperature) return below.vap_entropy ?? null;
  const frac =
    (temperature - (below.temperature ?? 0)) /
    ((above.temperature ?? 0) - (below.temperature ?? 0));
  const satP =
    (below.sat_pressure_kpa || 0) +
    frac * ((above.sat_pressure_kpa || 0) - (below.sat_pressure_kpa || 0));
  if (pressureKpa > satP * 1.1) {
    return (
      (below.liq_entropy || 0) +
      frac * ((above.liq_entropy || 0) - (below.liq_entropy || 0))
    );
  }
  return (
    (below.vap_entropy || 0) +
    frac * ((above.vap_entropy || 0) - (below.vap_entropy || 0))
  );
}

export function resolveCycleEnthalpy(
  cycleData: SysPerfDiagramCycleCacheEntry,
  props: SysPerfRefrigerantPropRow[],
  pointKey: string,
): number | null {
  const hServer = cycleData.enthalpy?.[`${pointKey} Enthalpy`];
  if (hServer != null) return hServer;
  const pVal = cycleData.cycle?.[`${pointKey} Pressure`];
  const tVal = cycleData.cycle?.[`${pointKey} Temperature`];
  if (pVal != null && tVal != null) {
    return interpolateEnthalpy(props, tVal, pVal * SYS_PERF_KGFCM2_TO_KPA);
  }
  return null;
}

export function resolveCycleEntropy(
  cycleData: SysPerfDiagramCycleCacheEntry,
  props: SysPerfRefrigerantPropRow[],
  pointKey: string,
): number | null {
  const sServer = cycleData.entropy?.[`${pointKey} Entropy`];
  if (sServer != null) return sServer;
  const pVal = cycleData.cycle?.[`${pointKey} Pressure`];
  const tVal = cycleData.cycle?.[`${pointKey} Temperature`];
  if (pVal != null && tVal != null) {
    return interpolateEntropy(props, tVal, pVal * SYS_PERF_KGFCM2_TO_KPA);
  }
  return null;
}

export function buildDiagramTableRows({
  cached,
  props,
  fallbackNote,
  txvIsenthalpic,
  hvacInherits,
}: {
  cached: SysPerfDiagramCycleCacheEntry | undefined;
  props: SysPerfRefrigerantPropRow[];
  fallbackNote: (args: { expected: string; actual: string }) => string;
  txvIsenthalpic: string;
  hvacInherits: string;
}): SysPerfDiagramTableRow[] {
  return SYS_PERF_DIAGRAM_POINTS.map((pt, idx) => {
    if (!cached?.cycle) {
      return {
        no: idx + 1,
        label: pt.label,
        p: '',
        t: '',
        h: '',
        sh: '',
        sc: '',
        notes: [],
      };
    }
    const pVal = cached.cycle[`${pt.key} Pressure`];
    const tVal = cached.cycle[`${pt.key} Temperature`];
    const hVal = resolveCycleEnthalpy(cached, props, pt.key);
    const pOrig = (cached.mappings || {})[`${pt.key} Pressure`] || '';
    const tOrig = (cached.mappings || {})[`${pt.key} Temperature`] || '';
    const notes: string[] = [];
    if (
      pOrig &&
      pt.stdP &&
      pOrig.toLowerCase().trim() !== pt.stdP.toLowerCase().trim()
    ) {
      notes.push(fallbackNote({ expected: pt.stdP, actual: pOrig }));
    }
    if (
      tOrig &&
      pt.stdT &&
      pOrig !== tOrig &&
      tOrig.toLowerCase().trim() !== pt.stdT.toLowerCase().trim()
    ) {
      notes.push(fallbackNote({ expected: pt.stdT, actual: tOrig }));
    }
    const isoNotes = cached.isenthalpic_notes || [];
    if (
      pt.key === 'TXV Out' &&
      isoNotes.some((n) => n.indexOf('TXV Out') === 0)
    ) {
      notes.push(txvIsenthalpic);
    }
    if (
      pt.key === 'Evap In' &&
      isoNotes.some((n) => n.indexOf('HVAC In') === 0)
    ) {
      notes.push(hvacInherits);
    }
    ((cached.warnings && cached.warnings[pt.key]) || []).forEach((w) =>
      notes.push(w),
    );
    const shsc = cached.sh_sc || {};
    return {
      no: idx + 1,
      label: pt.label,
      p: pVal != null ? pVal.toFixed(2) : '',
      t: tVal != null ? tVal.toFixed(1) : '',
      h: hVal != null ? hVal.toFixed(1) : '',
      sh:
        pt.key === 'Comp In' && shsc['Comp In SH'] != null
          ? shsc['Comp In SH'].toFixed(1)
          : '',
      sc:
        pt.key === 'TXV In' && shsc['TXV In SC'] != null
          ? shsc['TXV In SC'].toFixed(1)
          : '',
      notes,
    };
  });
}

export function buildMatchWarnings({
  fileCount,
  cache,
  formatWarning,
}: {
  fileCount: number;
  cache: Record<number, SysPerfDiagramCycleCacheEntry>;
  formatWarning: (args: {
    index: number;
    inPressure: string;
    outPressure: string;
  }) => string;
}): string[] {
  const out: string[] = [];
  Array.from({ length: fileCount }).forEach((_, i) => {
    const c = cache[i];
    if (!c?.cycle) return;
    const inP = c.cycle['Comp In Pressure'];
    const outP = c.cycle['Comp Out Pressure'];
    if (inP != null && outP != null && inP >= outP * 0.9) {
      out.push(
        formatWarning({
          index: i + 1,
          inPressure: inP.toFixed(2),
          outPressure: outP.toFixed(2),
        }),
      );
    }
  });
  return out;
}

export function buildPhPlotModel({
  ph,
  cache,
  fileCount,
  props,
  refrigerant,
  labels,
}: {
  ph: SysPerfPhDiagram | null;
  cache: Record<number, SysPerfDiagramCycleCacheEntry>;
  fileCount: number;
  props: SysPerfRefrigerantPropRow[];
  refrigerant: string;
  labels: SysPerfDiagramPlotLabels;
}): SysPerfDiagramPlotModel {
  const toKgf = (p: number) => p / SYS_PERF_KGFCM2_TO_KPA;
  const traces: Data[] = [];
  if (ph) {
    for (const iso of (ph.isoquality ?? []) as { h: number[]; p: number[] }[]) {
      traces.push({
        x: iso.h,
        y: iso.p.map(toKgf),
        type: 'scatter',
        mode: 'lines',
        line: {
          color: SYSPERF_DIAGRAM_COLORS.isoquality,
          width: 0.7,
          dash: 'dot',
        },
        showlegend: false,
        hoverinfo: 'skip',
      } as Data);
    }
    for (const iso of ph.isotherms ?? []) {
      traces.push({
        x: iso.h,
        y: iso.p.map(toKgf),
        type: 'scatter',
        mode: 'lines',
        line: { color: SYSPERF_DIAGRAM_COLORS.isotherm, width: 0.8 },
        showlegend: false,
        hoverinfo: 'skip',
      } as Data);
    }
    for (const iso of ph.isentropes ?? []) {
      traces.push({
        x: iso.h,
        y: iso.p.map(toKgf),
        type: 'scatter',
        mode: 'lines',
        line: {
          color: SYSPERF_DIAGRAM_COLORS.isentrope,
          width: 0.7,
          dash: 'dot',
        },
        showlegend: false,
        hoverinfo: 'skip',
      } as Data);
    }
    for (const iso of (ph.isochor ?? []) as { h: number[]; p: number[] }[]) {
      traces.push({
        x: iso.h,
        y: iso.p.map(toKgf),
        type: 'scatter',
        mode: 'lines',
        line: {
          color: SYSPERF_DIAGRAM_COLORS.isochor,
          width: 0.6,
          dash: 'dashdot',
        },
        showlegend: false,
        hoverinfo: 'skip',
      } as Data);
    }
    if (ph.saturation?.h?.length) {
      traces.push({
        x: ph.saturation.h,
        y: ph.saturation.p.map(toKgf),
        type: 'scatter',
        mode: 'lines',
        name: labels.saturationCurve,
        line: { color: SYSPERF_DIAGRAM_COLORS.saturation, width: 2.5 },
      } as Data);
    }
    if (ph.critical?.P && ph.critical?.h) {
      traces.push({
        x: [ph.critical.h],
        y: [toKgf(ph.critical.P)],
        type: 'scatter',
        mode: 'markers',
        name: labels.criticalPoint,
        marker: {
          size: 12,
          color: SYSPERF_DIAGRAM_COLORS.saturation,
          symbol: 'star',
        },
      } as Data);
    }
  }

  Array.from({ length: fileCount }).forEach((_, i) => {
    const c = cache[i];
    if (!c?.cycle) return;
    const hs: number[] = [];
    const ps: number[] = [];
    const pointLabels: string[] = [];
    const nums: number[] = [];
    SYS_PERF_DIAGRAM_POINT_ORDER.forEach((pt, idx) => {
      const pVal = c.cycle[`${pt} Pressure`];
      if (pVal == null) return;
      const h = resolveCycleEnthalpy(c, props, pt);
      if (h == null) return;
      hs.push(h);
      ps.push(pVal);
      pointLabels.push(SYS_PERF_DIAGRAM_POINTS[idx].label);
      nums.push(idx + 1);
    });
    if (!hs.length) return;
    hs.push(hs[0]);
    ps.push(ps[0]);
    pointLabels.push(pointLabels[0]);
    nums.push(nums[0]);
    const col = CYCLE_COLORS[i % CYCLE_COLORS.length];
    traces.push({
      x: hs,
      y: ps,
      type: 'scatter',
      mode: 'lines+markers',
      name: labels.cycleFileName({ index: i + 1, time: c.time ?? 30 }),
      line: { color: col, width: 2.5 },
      marker: {
        size: 12,
        color: col,
        line: { color: SYSPERF_DIAGRAM_COLORS.markerOutline, width: 2 },
      },
      text: pointLabels.map((label, idx) => `${nums[idx]}. ${label}`),
      hovertemplate:
        '<b>%{text}</b><br>h=%{x:.1f} kJ/kg<br>P=%{y:.2f} kgf/cm²<extra></extra>',
    } as Data);
    traces.push({
      x: hs.slice(0, -1),
      y: ps.slice(0, -1),
      type: 'scatter',
      mode: 'text',
      text: nums.slice(0, -1).map((n) => `<b>${n}</b>`),
      textposition: 'top center',
      textfont: { size: 14, color: col, family: 'Arial Black' },
      showlegend: false,
      hoverinfo: 'skip',
    } as Data);
  });

  const yTickVals = [0.5, 1, 2, 3, 5, 7, 10, 20, 30, 50];
  const layout = {
    xaxis: {
      title: { text: labels.axes.enthalpy, font: { size: 16 } },
      range: [150, 500],
      gridcolor: DATA_VIZ_PLOT_COLORS.phGrid,
      gridwidth: 1,
      zeroline: false,
      showline: true,
      mirror: true,
      dtick: 50,
      minor: {
        dtick: 10,
        showgrid: true,
        gridcolor: DATA_VIZ_PLOT_COLORS.phMinorGrid,
        griddash: 'dot',
      },
    },
    yaxis: {
      title: { text: labels.axes.pressure, font: { size: 16 } },
      type: 'log',
      range: [Math.log10(0.5), Math.log10(50)],
      tickmode: 'array',
      tickvals: yTickVals,
      ticktext: yTickVals.map(String),
      gridcolor: DATA_VIZ_PLOT_COLORS.phPressureGrid,
      gridwidth: 1,
      zeroline: false,
      showline: true,
      mirror: true,
      minor: {
        showgrid: true,
        gridcolor: DATA_VIZ_PLOT_COLORS.phPressureMinorGrid,
        griddash: 'dot',
      },
    },
    margin: { l: 70, r: 20, t: 44, b: 60 },
    paper_bgcolor: DATA_VIZ_PLOT_COLORS.transparent,
    plot_bgcolor: DATA_VIZ_PLOT_COLORS.warmPlot,
    hovermode: 'closest',
    legend: {
      font: { size: 12 },
      x: 0.02,
      y: 0.02,
      bgcolor: DATA_VIZ_PLOT_COLORS.legendBg,
    },
    title: { text: labels.phTitle({ refrigerant }), font: { size: 16 } },
    autosize: true,
  } as unknown as Partial<Layout>;
  return { traces, layout };
}

export function buildTsPlotModel({
  ts,
  cache,
  fileCount,
  props,
  refrigerant,
  axis,
  labels,
}: {
  ts: SysPerfTsDiagram | null;
  cache: Record<number, SysPerfDiagramCycleCacheEntry>;
  fileCount: number;
  props: SysPerfRefrigerantPropRow[];
  refrigerant: string;
  axis: SysPerfTsAxis;
  labels: SysPerfDiagramPlotLabels;
}): SysPerfDiagramPlotModel {
  const traces: Data[] = [];
  if (ts) {
    for (const iso of ts.isobars ?? []) {
      traces.push({
        x: iso.s,
        y: iso.t,
        type: 'scatter',
        mode: 'lines',
        line: {
          color: SYSPERF_DIAGRAM_COLORS.isobar,
          width: 0.7,
          dash: 'dot',
        },
        showlegend: false,
        hoverinfo: 'skip',
      } as Data);
    }
    for (const iso of ts.isenthalps ?? []) {
      traces.push({
        x: iso.s,
        y: iso.t,
        type: 'scatter',
        mode: 'lines',
        line: {
          color: SYSPERF_DIAGRAM_COLORS.isenthalp,
          width: 0.6,
          dash: 'dashdot',
        },
        showlegend: false,
        hoverinfo: 'skip',
      } as Data);
    }
    if (ts.saturation?.s?.length) {
      traces.push({
        x: ts.saturation.s,
        y: ts.saturation.t,
        type: 'scatter',
        mode: 'lines',
        name: labels.saturationCurve,
        line: { color: SYSPERF_DIAGRAM_COLORS.saturation, width: 2.5 },
      } as Data);
    }
    if (ts.critical?.s != null && ts.critical?.T != null) {
      traces.push({
        x: [ts.critical.s],
        y: [ts.critical.T],
        type: 'scatter',
        mode: 'markers',
        name: labels.criticalPoint,
        marker: {
          size: 12,
          color: SYSPERF_DIAGRAM_COLORS.saturation,
          symbol: 'star',
        },
      } as Data);
    }
  }

  Array.from({ length: fileCount }).forEach((_, i) => {
    const c = cache[i];
    if (!c?.cycle) return;
    const sx: number[] = [];
    const ty: number[] = [];
    const pointLabels: string[] = [];
    const nums: number[] = [];
    SYS_PERF_DIAGRAM_POINT_ORDER.forEach((pt, idx) => {
      const s = resolveCycleEntropy(c, props, pt);
      const tc = c.cycle[`${pt} Temperature`];
      if (s == null || tc == null) return;
      sx.push(s);
      ty.push(tc);
      pointLabels.push(SYS_PERF_DIAGRAM_POINTS[idx].label);
      nums.push(idx + 1);
    });
    if (!sx.length) return;
    sx.push(sx[0]);
    ty.push(ty[0]);
    pointLabels.push(pointLabels[0]);
    nums.push(nums[0]);
    const col = CYCLE_COLORS[i % CYCLE_COLORS.length];
    traces.push({
      x: sx,
      y: ty,
      type: 'scatter',
      mode: 'lines+markers',
      name: labels.cycleFileName({ index: i + 1, time: c.time ?? 30 }),
      line: { color: col, width: 2.5 },
      marker: {
        size: 12,
        color: col,
        line: { color: SYSPERF_DIAGRAM_COLORS.markerOutline, width: 2 },
      },
      text: pointLabels.map((label, idx) => `${nums[idx]}. ${label}`),
      hovertemplate:
        '<b>%{text}</b><br>s=%{x:.3f} kJ/kg·K<br>T=%{y:.1f} ℃<extra></extra>',
    } as Data);
    traces.push({
      x: sx.slice(0, -1),
      y: ty.slice(0, -1),
      type: 'scatter',
      mode: 'text',
      text: nums.slice(0, -1).map((n) => `<b>${n}</b>`),
      textposition: 'top center',
      textfont: { size: 14, color: col, family: 'Arial Black' },
      showlegend: false,
      hoverinfo: 'skip',
    } as Data);
  });

  const layout = {
    title: {
      text: labels.tsTitle({ refrigerant }),
      font: { family: DIAGRAM_FONT, size: 16 },
    },
    xaxis: {
      title: { text: labels.axes.entropy, font: { size: 16 } },
      range: [axis.xMin, axis.xMax],
      dtick: axis.xTick,
      gridcolor: DATA_VIZ_PLOT_COLORS.tsGrid,
      gridwidth: 0.6,
      griddash: 'dot',
      zeroline: false,
      showline: true,
      mirror: true,
    },
    yaxis: {
      title: { text: labels.axes.temperature, font: { size: 16 } },
      range: [axis.yMin, axis.yMax],
      dtick: axis.yTick,
      gridcolor: DATA_VIZ_PLOT_COLORS.tsGrid,
      gridwidth: 0.6,
      griddash: 'dot',
      zeroline: false,
      showline: true,
      mirror: true,
    },
    margin: { l: 70, r: 20, t: 44, b: 60 },
    paper_bgcolor: DATA_VIZ_PLOT_COLORS.transparent,
    plot_bgcolor: DATA_VIZ_PLOT_COLORS.warmPlot,
    hovermode: 'closest',
    legend: {
      font: { family: DIAGRAM_FONT, size: 12 },
      x: 0.02,
      y: 0.98,
      bgcolor: DATA_VIZ_PLOT_COLORS.legendBgStrong,
    },
    autosize: true,
  } as unknown as Partial<Layout>;
  return { traces, layout };
}
