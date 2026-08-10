import type { Layout } from 'plotly.js';

import type { DurabilityColSeries } from '../api/dataviz-api';
import { DATA_VIZ_PLOT_COLORS } from './data-viz-colors';

export const FONT = '현대하모니, Malgun Gothic, sans-serif';
export const FONT_SIZE_AXIS = 14;
export const LINE_WIDTH = 2.5;

export type AxisKey = 'xaxis' | 'yaxis' | 'yaxis2' | 'yaxis3';

export function niceRange(dataMin: number | null, dataMax: number | null) {
  if (dataMin == null || dataMax == null || dataMin === dataMax) {
    return { min: 0, max: 100, step: 10 };
  }
  const span = dataMax - dataMin;
  const rawStep = span / 10;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const nice = [1, 2, 2.5, 5, 10];
  let step = nice[nice.length - 1] * mag;
  for (let i = 0; i < nice.length; i++) {
    if (nice[i] * mag >= rawStep) {
      step = nice[i] * mag;
      break;
    }
  }
  let min = Math.floor(dataMin / step) * step;
  let max = Math.ceil(dataMax / step) * step;
  if (dataMin >= 0) min = 0;
  if (min === max) max = min + step * 10;
  step = (max - min) / 10;
  return { min, max, step };
}

export function autoYRange(
  data: Record<string, DurabilityColSeries>,
  cols: string[],
): [number, number] | null {
  let min = Infinity;
  let max = -Infinity;
  cols.forEach((col) => {
    const series = data[col]?.y;
    if (!series) return;
    series.forEach((value) => {
      if (value == null) return;
      if (value < min) min = value;
      if (value > max) max = value;
    });
  });
  if (min === Infinity) return null;
  return [min, max];
}

export function makeYAxis(
  label: string,
  range: [number, number] | null,
  isRight: boolean,
): Partial<Layout['yaxis']> {
  const axis: Record<string, unknown> = {
    title: { text: label, font: { size: FONT_SIZE_AXIS, family: FONT } },
    gridcolor: isRight
      ? DATA_VIZ_PLOT_COLORS.transparent
      : DATA_VIZ_PLOT_COLORS.grid,
    tickfont: { size: FONT_SIZE_AXIS, family: FONT },
    automargin: true,
  };
  if (isRight) {
    axis.side = 'right';
    axis.overlaying = 'y';
  }
  if (range) {
    const nice = niceRange(range[0], range[1]);
    const pad = (nice.max - nice.min) * 0.02;
    axis.range = [nice.min - pad, nice.max + pad];
    axis.autorange = false;
    const hasDecimal = nice.step % 1 !== 0;
    const values: number[] = [];
    const labels: string[] = [];
    for (
      let value = nice.min;
      value <= nice.max + nice.step * 0.001;
      value += nice.step
    ) {
      values.push(value);
      labels.push(hasDecimal ? value.toFixed(1) : String(Math.round(value)));
    }
    axis.tickmode = 'array';
    axis.tickvals = values;
    axis.ticktext = labels;
  }
  return axis as Partial<Layout['yaxis']>;
}

export function calcXAxis(maxHr: number) {
  if (maxHr < 1) {
    const minutes = maxHr * 60;
    const rawStep = minutes / 10;
    let step = rawStep <= 5 ? 5 : Math.ceil(rawStep / 10) * 10;
    if (minutes <= 10) step = 1;
    return { unit: 'min', dtick: step, label: 'Time (min)', factor: 60 }; // i18n-exempt-line: plot axis label
  }
  const rawStep = maxHr / 10;
  let step = rawStep <= 5 ? 5 : Math.ceil(rawStep / 10) * 10;
  if (maxHr <= 10) step = 1;
  return { unit: 'hr', dtick: step, label: 'Time (hr)', factor: 1 }; // i18n-exempt-line: plot axis label
}

export function buildAxisPatch(
  min: number,
  max: number,
  div: number,
): Record<string, unknown> {
  const step = (max - min) / div;
  const pad = (max - min) * 0.02;
  const hasDecimal = step % 1 !== 0;
  const values: number[] = [];
  const labels: string[] = [];
  for (let i = 0; i <= div; i++) {
    const value = min + step * i;
    values.push(value);
    labels.push(hasDecimal ? value.toFixed(1) : String(Math.round(value)));
  }
  return {
    range: [min - pad, max + pad],
    tickmode: 'array',
    tickvals: values,
    ticktext: labels,
    autorange: false,
  };
}
