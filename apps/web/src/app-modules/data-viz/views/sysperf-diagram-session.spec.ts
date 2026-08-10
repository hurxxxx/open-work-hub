import { describe, expect, it } from 'vitest';

import { SYS_PERF_TS_AXIS_DEFAULTS } from './sysperf-diagram';
import {
  buildSysPerfDiagramBulkTimes,
  canApplySysPerfDiagramTsAxis,
  loadSysPerfDiagramBulkTime,
  loadSysPerfDiagramTimes,
  loadSysPerfDiagramTsAxis,
  saveSysPerfDiagramTime,
  saveSysPerfDiagramTsAxis,
  sysPerfDiagramTimeKey,
  updateSysPerfDiagramTsAxisDraft,
  type SysPerfDiagramStorage,
} from './sysperf-diagram-session';

function memoryStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  const storage: SysPerfDiagramStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
  return {
    storage,
    get: (key: string) => values.get(key),
  };
}

describe('sysperf diagram session', () => {
  it('loads per-file times from storage with safe defaults', () => {
    const { storage } = memoryStorage({
      [sysPerfDiagramTimeKey(0)]: '12.5',
      [sysPerfDiagramTimeKey(1)]: 'not-a-number',
    });

    expect(loadSysPerfDiagramTimes({ storage, fileCount: 3 })).toEqual({
      0: '12.5',
      1: '30',
      2: '30',
    });
  });

  it('saves a single time only when the input is numeric', () => {
    const state = memoryStorage();

    expect(saveSysPerfDiagramTime(state.storage, 1, '44.2')).toBe(true);
    expect(state.get(sysPerfDiagramTimeKey(1))).toBe('44.2');

    expect(saveSysPerfDiagramTime(state.storage, 1, 'bad')).toBe(false);
    expect(state.get(sysPerfDiagramTimeKey(1))).toBe('44.2');
  });

  it('builds and persists bulk times only for non-negative numeric input', () => {
    const state = memoryStorage();

    expect(
      buildSysPerfDiagramBulkTimes({
        storage: state.storage,
        fileCount: 2,
        value: '18.5',
      }),
    ).toEqual({ 0: '18.5', 1: '18.5' });
    expect(state.get(sysPerfDiagramTimeKey(0))).toBe('18.5');
    expect(state.get(sysPerfDiagramTimeKey(1))).toBe('18.5');
    expect(loadSysPerfDiagramBulkTime(state.storage)).toBe('18.5');

    expect(
      buildSysPerfDiagramBulkTimes({
        storage: state.storage,
        fileCount: 2,
        value: '-1',
      }),
    ).toBeNull();
  });

  it('loads and normalizes T-S axis settings from storage', () => {
    const { storage } = memoryStorage({
      sp_ts_xMin: '3',
      sp_ts_xMax: '2',
      sp_ts_xTick: '0',
      sp_ts_yMin: '-20',
      sp_ts_yMax: '100',
      sp_ts_yTick: 'bad',
    });

    expect(loadSysPerfDiagramTsAxis(storage)).toEqual({
      ...SYS_PERF_TS_AXIS_DEFAULTS,
      yMin: -20,
      yMax: 100,
    });
  });

  it('saves axis settings and rejects invalid draft axes before apply', () => {
    const state = memoryStorage();
    const axis = {
      xMin: 0.4,
      xMax: 2.4,
      xTick: 0.2,
      yMin: -40,
      yMax: 160,
      yTick: 20,
    };

    saveSysPerfDiagramTsAxis(state.storage, axis);
    expect(state.get('sp_ts_xMin')).toBe('0.4');
    expect(state.get('sp_ts_yTick')).toBe('20');
    expect(canApplySysPerfDiagramTsAxis(axis)).toBe(true);
    expect(
      canApplySysPerfDiagramTsAxis({
        ...axis,
        xMax: Number.NaN,
      }),
    ).toBe(false);
    expect(
      canApplySysPerfDiagramTsAxis({
        ...axis,
        yTick: 0,
      }),
    ).toBe(false);
  });

  it('updates T-S axis drafts only for finite numeric input', () => {
    const axis = {
      ...SYS_PERF_TS_AXIS_DEFAULTS,
      xMin: 0.4,
    };

    expect(
      updateSysPerfDiagramTsAxisDraft({
        axis,
        key: 'xMin',
        value: '0.8',
      }),
    ).toEqual({
      ...axis,
      xMin: 0.8,
    });
    expect(
      updateSysPerfDiagramTsAxisDraft({
        axis,
        key: 'xMin',
        value: '',
      }),
    ).toBe(axis);
    expect(
      updateSysPerfDiagramTsAxisDraft({
        axis,
        key: 'xMin',
        value: 'NaN',
      }),
    ).toBe(axis);
  });
});
