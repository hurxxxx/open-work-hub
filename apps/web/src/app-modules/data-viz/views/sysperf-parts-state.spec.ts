import { describe, expect, it } from 'vitest';

import { DEFAULT_PART_TYPE, PART_CAT_ORDER } from './sysperf-parts';
import {
  emptyPartsState,
  partFields,
  partVal,
  type PartsState,
} from './sysperf-parts-state';

describe('sysperf parts state', () => {
  it('initializes every part category with empty default selection state', () => {
    const state = emptyPartsState();

    expect(Object.keys(state)).toEqual([...PART_CAT_ORDER]);
    PART_CAT_ORDER.forEach((key) => {
      expect(state[key]).toEqual({
        selected: '',
        direct: '',
        type: DEFAULT_PART_TYPE,
      });
    });
  });

  it('uses direct input before selected chip values', () => {
    const parts: Record<number, PartsState> = { 7: emptyPartsState() };
    parts[7].comp = {
      selected: 'Selected Comp',
      direct: 'Direct Comp',
      type: DEFAULT_PART_TYPE,
    };

    expect(partVal(parts, 7, 'comp')).toBe('Direct Comp');

    parts[7].comp.direct = '';
    expect(partVal(parts, 7, 'comp')).toBe('Selected Comp');
    expect(partVal(parts, 7, 'txv')).toBe('');
    expect(partVal(parts, 99, 'comp')).toBe('');
  });

  it('builds exactly the DB payload fields for the supported part categories', () => {
    const parts: Record<number, PartsState> = { 7: emptyPartsState() };
    parts[7].comp.direct = 'Comp A';
    parts[7].txv.selected = 'TXV B';

    const fields = partFields(parts, 7);

    expect(Object.keys(fields)).toEqual([...PART_CAT_ORDER]);
    expect(fields.comp).toBe('Comp A');
    expect(fields.txv).toBe('TXV B');
    expect(fields.condenser).toBe('');
  });
});
