import { describe, expect, it } from 'vitest';

import {
  autoYRange,
  buildAxisPatch,
  calcXAxis,
  niceRange,
} from './comp-reliability-axis';

describe('comp reliability axis model', () => {
  it('creates a stable default range for missing or flat data', () => {
    expect(niceRange(null, 10)).toEqual({ min: 0, max: 100, step: 10 });
    expect(niceRange(7, 7)).toEqual({ min: 0, max: 100, step: 10 });
  });

  it('snaps positive data ranges to zero-based nice ticks', () => {
    expect(niceRange(12, 87)).toEqual({ min: 0, max: 90, step: 9 });
  });

  it('switches x axis units from minutes to hours around one hour', () => {
    expect(calcXAxis(0.5)).toEqual({
      unit: 'min',
      dtick: 5,
      label: 'Time (min)',
      factor: 60,
    });
    expect(calcXAxis(2)).toEqual({
      unit: 'hr',
      dtick: 1,
      label: 'Time (hr)',
      factor: 1,
    });
  });

  it('builds manual axis patch ticks from min, max, and division count', () => {
    expect(buildAxisPatch(0, 10, 5)).toEqual({
      range: [-0.2, 10.2],
      tickmode: 'array',
      tickvals: [0, 2, 4, 6, 8, 10],
      ticktext: ['0', '2', '4', '6', '8', '10'],
      autorange: false,
    });
  });

  it('finds y range across selected columns while ignoring null points', () => {
    expect(
      autoYRange(
        {
          a: { x: [0, 1, 2], y: [null, 3, 9] },
          b: { x: [0, 1], y: [-2, null] },
          c: { x: [0], y: [100] },
        },
        ['a', 'b'],
      ),
    ).toEqual([-2, 9]);
  });
});
