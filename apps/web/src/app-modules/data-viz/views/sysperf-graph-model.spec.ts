import { describe, expect, it } from 'vitest';

import type { MeasureItem } from './sysperf-items';
import {
  augmentSysPerfGraphData,
  buildSysPerfCompareGraphModel,
  buildSysPerfGraphPlotModel,
  resolveSysPerfGraphAxisRange,
  stdKey,
  unitOf,
  type SysPerfGraphDataCache,
  type SysPerfGraphLabels,
} from './sysperf-graph';

const items: MeasureItem[] = [
  { n: 10, c: 'Pressure', nm: 'Parent', u: 'kgf/cm2', cs: 3, kw: [] },
  { n: 11, nm: 'Child A', u: '', kw: [], sub: 'avg' },
  { n: 12, nm: 'Child B', u: '', kw: [], sub: 'avg' },
  { n: 13, nm: 'Average', u: '', kw: [], avg: true, grp: 'avg' },
  { n: 20, nm: 'Loose', u: '', kw: [] },
];

const labels: SysPerfGraphLabels = {
  axisTitle: ({ index, name, unit }) => `${index}:${name}:${unit}`,
  traceFileSuffix: ({ index }) => ` (${index})`,
  fileLabel: ({ index }) => `file-${index}`,
  comparePlotTitle: ({ name }) => `compare ${name}`,
  timeAxisTitle: 'Time (min)',
};

function cache(data: Record<string, (number | null)[]>): SysPerfGraphDataCache {
  return { data, units: {} };
}

describe('sysperf graph model', () => {
  it('builds standard keys and inherits units from category parent rows', () => {
    expect(stdKey(items[1])).toBe('11_Child A');
    expect(unitOf(items[1], items, 'Other')).toBe('kgf/cm2');
    expect(unitOf(items[4], items, 'Other')).toBe('Other');
  });

  it('augments missing average rows from child series without overwriting existing values', () => {
    const augmented = augmentSysPerfGraphData(
      {
        [stdKey(items[1])]: [1, 2, null],
        [stdKey(items[2])]: [3, null, 5],
      },
      items,
    );

    expect(augmented[stdKey(items[3])]).toEqual([2, 2, 5]);

    const existing = augmentSysPerfGraphData(
      {
        [stdKey(items[1])]: [1, 2],
        [stdKey(items[3])]: [10, null],
      },
      items,
    );
    expect(existing[stdKey(items[3])]).toEqual([10, null]);
  });

  it('builds multi-axis selected graph traces, axis ranges, and missing item metadata', () => {
    const model = buildSysPerfGraphPlotModel({
      selected: [11, 13, 20],
      files: [{ file_id: 1 }, { file_id: 2 }],
      cache: {
        1: cache({
          Time: [0, 1],
          [stdKey(items[1])]: [1, 2],
          [stdKey(items[2])]: [3, 4],
        }),
        2: cache({
          Time: [0, 1],
          [stdKey(items[1])]: [5, 6],
          [stdKey(items[2])]: [7, 8],
        }),
      },
      appliedX: { mn: '0', mx: '10', dv: '5' },
      appliedY: { 11: { mn: '1', mx: '11', dv: '5' } },
      labels,
      fallbackUnit: 'Other',
      items,
    });

    expect(model.traces.map((trace) => trace.name)).toEqual([
      'Child A (1)',
      'Child A (2)',
      'Average (1)',
      'Average (2)',
    ]);
    expect(model.missing).toEqual([
      { fi: 1, nm: 'Loose', n: 20 },
      { fi: 2, nm: 'Loose', n: 20 },
    ]);
    expect(model.axisInfo.map((axis) => axis.unit)).toEqual([
      'kgf/cm2',
      'Other',
      'Other',
    ]);
    expect(model.layout.xaxis).toEqual(
      expect.objectContaining({ range: [0, 10], dtick: 2, autorange: false }),
    );
    expect(model.layout.yaxis).toEqual(
      expect.objectContaining({ range: [1, 11], dtick: 2, autorange: false }),
    );
    expect(model.layout.yaxis2).toEqual(
      expect.objectContaining({ anchor: 'free', overlaying: 'y' }),
    );
  });

  it('ignores invalid axis ranges instead of passing NaN to Plotly', () => {
    expect(
      resolveSysPerfGraphAxisRange({ mn: '10', mx: '1', dv: '5' }),
    ).toBeNull();
    expect(
      resolveSysPerfGraphAxisRange({ mn: 'a', mx: '10', dv: '5' }),
    ).toBeNull();
    expect(
      resolveSysPerfGraphAxisRange({ mn: '1', mx: '10', dv: '0' }),
    ).toBeNull();
    expect(
      resolveSysPerfGraphAxisRange({ mn: '1', mx: '11', dv: '5' }),
    ).toEqual({
      range: [1, 11],
      dtick: 2,
      autorange: false,
    });
  });

  it('builds compare graph traces across files using standard key fallback', () => {
    const model = buildSysPerfCompareGraphModel({
      itemNumber: 11,
      files: [{ file_id: 1 }, { file_id: 2 }],
      cache: {
        1: cache({ Time: [0], [stdKey(items[1])]: [1] }),
        2: cache({ Time: [0], 'Child A': [2] }),
      },
      labels,
      items,
    });

    expect(model.item?.nm).toBe('Child A');
    expect(model.traces.map((trace) => trace.name)).toEqual([
      'file-1',
      'file-2',
    ]);
    expect(model.traces.map((trace) => trace.y)).toEqual([[1], [2]]);
    expect(model.layout.title).toEqual(
      expect.objectContaining({ text: 'compare Child A' }),
    );
  });
});
