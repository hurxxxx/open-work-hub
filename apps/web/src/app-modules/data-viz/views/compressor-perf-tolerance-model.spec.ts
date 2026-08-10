import { describe, expect, it } from 'vitest';

import type { ProfileTolCell, ToleranceAllResponse } from '../api/dataviz-api';
import {
  formatProfileToleranceCell,
  nonEmptyProfileToleranceGroups,
  numberOrNull,
  profileToleranceGroups,
  profileToleranceRowCount,
  sortToleranceCapModelKeys,
  toleranceEsOrder,
} from './compressor-perf-tolerance-model';

function cell(patch: Partial<ProfileTolCell>): ProfileTolCell {
  return {
    ref: null,
    sign: '±',
    tol: null,
    lower: null,
    ...patch,
  };
}

describe('compressor perf tolerance model', () => {
  it('parses numeric input without leaking invalid values', () => {
    expect(numberOrNull('')).toBeNull();
    expect(numberOrNull('   ')).toBeNull();
    expect(numberOrNull('12.5')).toBe(12.5);
    expect(numberOrNull('not-a-number')).toBeNull();
  });

  it('builds stable profile group names from generated and saved rows', () => {
    expect(
      profileToleranceGroups(
        'ES',
        {
          ES10: { rpm: cell({ ref: 10 }) },
          GM2: { rpm: cell({ ref: 2 }) },
          GM1: { rpm: cell({ ref: 1 }) },
        },
        2,
      ),
    ).toEqual(['ES1', 'ES2', 'ES10', 'GM1', 'GM2']);

    expect(profileToleranceGroups('', {}, 2)).toEqual(['ES1', 'ES2']);
    expect(
      profileToleranceRowCount({ ES1: {}, ES2: {}, ES3: {}, ES4: {} }),
    ).toBe(4);
  });

  it('filters empty saved profile groups and orders them numerically', () => {
    expect(
      nonEmptyProfileToleranceGroups({
        ES10: { rpm: cell({ ref: 10 }) },
        ES2: {},
        ES1: { rpm: cell({ tol: 1 }) },
      }),
    ).toEqual(['ES1', 'ES10']);
  });

  it('formats profile tolerance cells for symmetric and one-sided tolerances', () => {
    expect(formatProfileToleranceCell(undefined)).toBe('-');
    expect(formatProfileToleranceCell(cell({ ref: 1200 }))).toBe('1200');
    expect(formatProfileToleranceCell(cell({ ref: 1200, tol: 50 }))).toBe(
      '1200 ± 50',
    );
    expect(
      formatProfileToleranceCell(cell({ ref: 1200, sign: '+', tol: 50 })),
    ).toBe('1200 + 50');
    expect(
      formatProfileToleranceCell(
        cell({ ref: 1200, sign: '편측', tol: 50, lower: 30 }),
      ),
    ).toBe('1200 +50/-30');
  });

  it('sorts uploaded tolerance review keys by capacity then model and ES order', () => {
    const data: ToleranceAllResponse = {
      cap_models: {
        b: { capacity: '200cc', model: 'B' },
        c: { capacity: '100cc', model: 'C' },
        a: { capacity: '100cc', model: 'A' },
      },
      models: {},
    };

    expect(sortToleranceCapModelKeys(data)).toEqual(['a', 'c', 'b']);
    expect(
      ['ES 10', 'ES 2', 'Manual'].sort(
        (a, b) => toleranceEsOrder(a) - toleranceEsOrder(b),
      ),
    ).toEqual(['ES 2', 'ES 10', 'Manual']);
  });
});
