import { describe, expect, it } from 'vitest';

import {
  buildSysPerfSheetPreviewRows,
  countSysPerfPreviewRows,
  formatSysPerfPreviewValue,
  type SysPerfSheetPreview,
} from './sysperf-table-preview';

const preview: SysPerfSheetPreview = {
  columns: ['A', 'B'],
  data: {
    A: [1.23456, Number.NaN, null],
    B: [2, 3.3333],
  },
  total_rows: 5,
};

describe('sysperf table preview model', () => {
  it('keeps preview row count within total rows and loaded column lengths', () => {
    expect(countSysPerfPreviewRows(preview)).toBe(2);
    expect(
      countSysPerfPreviewRows({ columns: [], data: {}, total_rows: 4 }),
    ).toBe(4);
  });

  it('formats finite numbers compactly and blanks non-values', () => {
    expect(formatSysPerfPreviewValue(1.23456)).toBe('1.235');
    expect(formatSysPerfPreviewValue(1.2)).toBe('1.2');
    expect(formatSysPerfPreviewValue(null)).toBe('');
    expect(formatSysPerfPreviewValue(Number.POSITIVE_INFINITY)).toBe('');
  });

  it('builds rendered preview rows with one-based indexes and formatted cells', () => {
    expect(buildSysPerfSheetPreviewRows(preview)).toEqual([
      {
        index: 1,
        cells: [
          { column: 'A', value: '1.235' },
          { column: 'B', value: '2' },
        ],
      },
      {
        index: 2,
        cells: [
          { column: 'A', value: '' },
          { column: 'B', value: '3.333' },
        ],
      },
    ]);
  });
});
