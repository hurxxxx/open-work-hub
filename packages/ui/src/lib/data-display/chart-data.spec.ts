import { describe, expect, it } from 'vitest';

import type { ChartSeries } from '../types';
import { toCartesianData, toDonutChartData } from './chart-data';

const series: ChartSeries[] = [
  {
    key: 'planned',
    label: 'Planned',
    color: '#2563eb',
    data: [4, 6],
  },
  {
    key: 'done',
    label: 'Done',
    color: '#16a34a',
    data: [2],
  },
];

describe('chart data', () => {
  it('projects category and series values into cartesian rows', () => {
    expect(toCartesianData(['Mon', 'Tue'], series)).toEqual([
      {
        category: 'Mon',
        planned: 4,
        done: 2,
      },
      {
        category: 'Tue',
        planned: 6,
        done: 0,
      },
    ]);
  });

  it('projects donut rows from the first series and category colors', () => {
    expect(toDonutChartData(['Open', 'Closed', 'Blocked'], series)).toEqual([
      {
        name: 'Open',
        value: 4,
        color: '#2563eb',
      },
      {
        name: 'Closed',
        value: 6,
        color: '#16a34a',
      },
      {
        name: 'Blocked',
        value: 0,
        color: '#2563eb',
      },
    ]);
  });

  it('uses the accent token when donut data has no series', () => {
    expect(toDonutChartData(['Empty'], [])).toEqual([
      {
        name: 'Empty',
        value: 0,
        color: 'var(--ui-color-accent)',
      },
    ]);
  });
});
