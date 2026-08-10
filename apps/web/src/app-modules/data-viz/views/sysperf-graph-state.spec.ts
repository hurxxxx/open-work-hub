import { describe, expect, it } from 'vitest';

import {
  buildSysPerfGraphCheckedFiles,
  createSysPerfGraphAxisState,
  groupSysPerfGraphMissingItems,
  selectSysPerfGraphCheckedFiles,
  summarizeSysPerfGraphErrors,
  toSysPerfGraphDataCache,
  toggleSysPerfGraphFileChecked,
  toggleSysPerfGraphItemSelection,
  updateSysPerfGraphAxisField,
  updateSysPerfGraphAxisMapField,
} from './sysperf-graph-state';

describe('sysperf graph state', () => {
  it('initializes and toggles file and item selection state', () => {
    const files = [{ file_id: 1 }, { file_id: 2 }];
    const checked = buildSysPerfGraphCheckedFiles(files);

    expect(checked).toEqual({ 1: true, 2: true });
    expect(toggleSysPerfGraphFileChecked(checked, 2)).toEqual({
      1: true,
      2: false,
    });
    expect(toggleSysPerfGraphItemSelection([10], 20)).toEqual([10, 20]);
    expect(toggleSysPerfGraphItemSelection([10, 20], 10)).toEqual([20]);
  });

  it('selects checked files and summarizes loaded errors', () => {
    const files = [{ file_id: 1 }, { file_id: 2 }, { file_id: 3 }];
    const selected = selectSysPerfGraphCheckedFiles(files, {
      1: true,
      2: false,
      3: true,
    });

    expect(selected).toEqual([{ file_id: 1 }, { file_id: 3 }]);
    expect(
      summarizeSysPerfGraphErrors(selected, {
        1: { data: {}, units: {}, error: 'missing mapping' },
        3: { data: {}, units: {}, error: 'missing time' },
      }),
    ).toEqual({ allError: true, firstError: 'missing mapping' });
    expect(
      summarizeSysPerfGraphErrors(selected, { 1: { data: {}, units: {} } }),
    ).toEqual({
      allError: false,
      firstError: undefined,
    });
  });

  it('updates axis draft maps without mutating defaults', () => {
    const state = createSysPerfGraphAxisState();

    expect(state.axisX).toEqual({ mn: '', mx: '', dv: '10' });
    expect(updateSysPerfGraphAxisField(state.axisX, 'mn', '1')).toEqual({
      mn: '1',
      mx: '',
      dv: '10',
    });
    expect(updateSysPerfGraphAxisMapField({}, 65, 'mx', '100')).toEqual({
      65: { mn: '', mx: '100', dv: '10' },
    });
  });

  it('groups missing graph items by file index for localized messages', () => {
    expect(
      groupSysPerfGraphMissingItems([
        { fi: 1, nm: 'Ps', n: 10 },
        { fi: 1, nm: 'Ts', n: 11 },
        { fi: 2, nm: 'Pc', n: 12 },
      ]),
    ).toEqual([
      { fileIndex: 1, items: ['Ps (n=10)', 'Ts (n=11)'] },
      { fileIndex: 2, items: ['Pc (n=12)'] },
    ]);
  });

  it('normalizes graph-data responses into cache entries', () => {
    expect(toSysPerfGraphDataCache({ data: { Time: [0, 1] } })).toEqual({
      data: { Time: [0, 1] },
      units: {},
    });
  });
});
