import { describe, expect, it } from 'vitest';

import type { PerfAverage, PerfRow } from '../api/dataviz-api';
import {
  formatPerfNumber,
  formatPerfValue,
  groupPerfAverages,
  groupPerfRowsBySerial,
  testGroupFamily,
  testGroupOrder,
} from './compressor-perf-table-model';

function row(patch: Partial<PerfRow>): PerfRow {
  return {
    test_group: '',
    comp_type: '',
    serial_no: '',
    test_date: '',
    car_model: '',
    engine_spec: '',
    remarks: '',
    source_file: '',
    rpm: null,
    pd: null,
    td: null,
    ps: null,
    ts: null,
    pc: null,
    mass_flow: null,
    vol_eff: null,
    ocr: null,
    cooling_cap_a: null,
    cooling_cap_f: null,
    power_kw: null,
    cop_sc: null,
    heat_balance: null,
    torque: null,
    ...patch,
  };
}

function average(patch: Partial<PerfAverage>): PerfAverage {
  return {
    test_group: '',
    count: 0,
    ...patch,
  };
}

describe('compressor perf table model', () => {
  it('orders test groups by family then numeric suffix', () => {
    expect(testGroupFamily('ES 12')).toBe('ES');
    expect(testGroupOrder('ES 12')).toBe(12);
    expect(testGroupOrder('Benchmark')).toBe(9999);
  });

  it('groups raw rows by serial, sorts newest serial group first, and marks group ends', () => {
    const grouped = groupPerfRowsBySerial([
      row({ serial_no: 'A', test_group: 'ES 2', test_date: '2026-01-01' }),
      row({ serial_no: 'B', test_group: 'ES 3', test_date: '2026-02-01' }),
      row({ serial_no: 'A', test_group: 'ES 1', test_date: '2026-01-02' }),
    ]);

    expect(grouped.map((item) => item.row.serial_no)).toEqual(['B', 'A', 'A']);
    expect(grouped.map((item) => item.row.test_group)).toEqual([
      'ES 3',
      'ES 1',
      'ES 2',
    ]);
    expect(grouped.map((item) => item.isGroupEnd)).toEqual([true, false, true]);
  });

  it('groups averages by the selected display dimension and sorts each group by test group', () => {
    const grouped = groupPerfAverages(
      [
        average({ comp_type: 'P2', test_group: 'ES 2', count: 1 }),
        average({ comp_type: 'P1', test_group: 'ES 3', count: 1 }),
        average({ comp_type: 'P2', test_group: 'ES 1', count: 1 }),
      ],
      { showComponent: true },
    );

    expect(
      grouped.map(
        (item) =>
          `${item.groupIndex}:${item.row.comp_type}:${item.row.test_group}`,
      ),
    ).toEqual(['0:P2:ES 1', '0:P2:ES 2', '1:P1:ES 3']);
    expect(grouped.map((item) => item.isGroupEnd)).toEqual([false, true, true]);
  });

  it('formats empty values and metric decimals consistently', () => {
    expect(formatPerfValue(null)).toBe('-');
    expect(formatPerfValue('')).toBe('-');
    expect(formatPerfValue(3)).toBe('3');
    expect(formatPerfValue(3.456)).toBe('3.46');
    expect(formatPerfNumber(1234.5, 'rpm')).toBe('1235');
    expect(formatPerfNumber(12.34, 'td')).toBe('12.3');
    expect(formatPerfNumber(12, 'mass_flow')).toBe('12.00');
    expect(formatPerfNumber(12.345, 'unknown')).toBe('12.35');
  });
});
