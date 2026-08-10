import { describe, expect, it } from 'vitest';

import type {
  SysPerfCycleData,
  SysPerfPhDiagram,
  SysPerfRefrigerantPropRow,
  SysPerfTsDiagram,
} from '../api/dataviz-api';
import type { UsableSysPerfUploadedFile } from './sysperf-files';
import {
  buildFailedSysPerfDiagramCycleData,
  buildSysPerfDiagramCycleCache,
  findBlockingSysPerfDiagramCycleError,
  findSysPerfRefrigerantId,
  loadSysPerfDiagramRefrigerants,
  loadSysPerfDiagramRun,
  parseSysPerfDiagramTime,
  type SysPerfDiagramCycleResult,
  type SysPerfDiagramLoaderDeps,
} from './sysperf-diagram-loader';

function cycle(patch: Partial<SysPerfCycleData> = {}): SysPerfCycleData {
  return {
    status: 'ok',
    time: 30,
    row_index: 1,
    cycle: {},
    enthalpy: {},
    entropy: {},
    sh_sc: {},
    mappings: {},
    isenthalpic_notes: [],
    warnings: {},
    ...patch,
  };
}

function file(id: number, sheetName: string): UsableSysPerfUploadedFile {
  return {
    filename: `file-${id}.xlsx`,
    file_id: id,
    sheets: [{ sheet_name: sheetName, headers: [], header_numeric_counts: {} }],
  } as UsableSysPerfUploadedFile;
}

const props: SysPerfRefrigerantPropRow[] = [
  {
    temperature: 0,
    sat_pressure_kgcm2: null,
    sat_pressure_kpa: 100,
    sat_pressure_bar: null,
    liq_enthalpy: 10,
    vap_enthalpy: 20,
    liq_entropy: 1,
    vap_entropy: 2,
    liq_specific_vol: null,
    vap_specific_vol: null,
  },
];

const ph: SysPerfPhDiagram = {
  status: 'ok',
  has_coolprop: true,
  refrigerant: 'R-134a',
  saturation: { h: [], p: [] },
  isotherms: [],
  isentropes: [],
  isoquality: [],
  isochor: [],
  critical: { T: null, P: null, h: null },
};

const ts: SysPerfTsDiagram = {
  status: 'ok',
  has_coolprop: true,
  refrigerant: 'R-134a',
  saturation: { s: [], t: [] },
  isobars: [],
  isenthalps: [],
  critical: { T: null, s: null, P: null },
};

describe('sysperf diagram loader', () => {
  it('finds refrigerant ids and preserves current time parsing behavior', () => {
    expect(
      findSysPerfRefrigerantId(
        [
          { id: 0, name: 'fallback' },
          { id: 7, name: 'R-134a' },
        ],
        'R-134a',
      ),
    ).toBe(7);
    expect(
      findSysPerfRefrigerantId([{ id: 0, name: 'R-134a' }], 'R-134a'),
    ).toBeNull();

    expect(parseSysPerfDiagramTime('12.5')).toEqual({
      requestTime: 12.5,
      cacheTime: 12.5,
    });
    expect(parseSysPerfDiagramTime('12abc')).toEqual({
      requestTime: 12,
      cacheTime: 12,
    });
    expect(parseSysPerfDiagramTime('bad')).toEqual({
      requestTime: null,
      cacheTime: 30,
    });
  });

  it('normalizes cycle cache and reports blocking errors only when every cycle fails', () => {
    const successWithoutServerTime = cycle({
      time: undefined as unknown as number,
    });
    const results: SysPerfDiagramCycleResult[] = [
      { fileIndex: 0, requestedTime: 12.5, data: successWithoutServerTime },
      { fileIndex: 1, requestedTime: 30, data: cycle({ error: 'bad data' }) },
    ];

    expect(buildSysPerfDiagramCycleCache(results)).toEqual({
      0: expect.objectContaining({ time: 12.5 }),
    });
    expect(findBlockingSysPerfDiagramCycleError(results)).toBeUndefined();
    expect(
      findBlockingSysPerfDiagramCycleError([
        {
          fileIndex: 0,
          requestedTime: 30,
          data: cycle({ error: 'first failed' }),
        },
        {
          fileIndex: 1,
          requestedTime: 30,
          data: cycle({ error: 'second failed' }),
        },
      ]),
    ).toBe('first failed');
  });

  it('normalizes rejected cycle requests into failed cycle data', () => {
    expect(
      buildFailedSysPerfDiagramCycleData({
        error: new Error('network down'),
        time: 12.5,
      }),
    ).toEqual({
      status: 'error',
      time: 12.5,
      row_index: -1,
      cycle: {},
      enthalpy: {},
      entropy: {},
      sh_sc: {},
      mappings: {},
      isenthalpic_notes: [],
      warnings: {},
      error: 'network down',
    });
    expect(
      buildFailedSysPerfDiagramCycleData({
        error: 'bad',
        time: 30,
      }).error,
    ).toBe('');
  });

  it('loads a diagram run without props when refrigerant id is missing', async () => {
    const refrigerantCalls: Parameters<
      SysPerfDiagramLoaderDeps['getRefrigerants']
    >[] = [];
    const propCalls: Parameters<
      SysPerfDiagramLoaderDeps['getRefrigerantProps']
    >[] = [];
    const cycleCalls: Parameters<SysPerfDiagramLoaderDeps['getCycleData']>[] =
      [];
    const phCalls: Parameters<SysPerfDiagramLoaderDeps['getPhDiagram']>[] = [];
    const tsCalls: Parameters<SysPerfDiagramLoaderDeps['getTsDiagram']>[] = [];
    const deps: SysPerfDiagramLoaderDeps = {
      getRefrigerants: async (...args) => {
        refrigerantCalls.push(args);
        return { data: [] };
      },
      getRefrigerantProps: async (...args) => {
        propCalls.push(args);
        return { data: props };
      },
      getCycleData: async (...args) => {
        cycleCalls.push(args);
        return cycle({ time: undefined as unknown as number });
      },
      getPhDiagram: async (...args) => {
        phCalls.push(args);
        return ph;
      },
      getTsDiagram: async (...args) => {
        tsCalls.push(args);
        return ts;
      },
    };

    const result = await loadSysPerfDiagramRun({
      token: 'token',
      workspaceSlug: 'workspace',
      files: [file(1, 'Sheet A')],
      times: { 0: 'bad' },
      refrigerant: 'R-404A',
      refrigerants: [{ id: 7, name: 'R-134a' }],
      deps,
    });

    expect(propCalls).toHaveLength(0);
    expect(cycleCalls[0]).toEqual([
      'token',
      'workspace',
      1,
      'Sheet A',
      null,
      'R-404A',
    ]);
    expect(phCalls[0]).toEqual(['token', 'workspace', 'R-404A', null]);
    expect(tsCalls[0]).toEqual(['token', 'workspace', 'R-404A', null]);
    expect(result.props).toEqual([]);
    expect(result.cache[0]).toEqual(expect.objectContaining({ time: 30 }));
    expect(result.cycleError).toBeUndefined();
  });

  it('keeps successful cycle results when one file cycle request rejects', async () => {
    const cycleCalls: Parameters<SysPerfDiagramLoaderDeps['getCycleData']>[] =
      [];
    const deps: SysPerfDiagramLoaderDeps = {
      getRefrigerants: async () => ({ data: [] }),
      getRefrigerantProps: async () => ({ data: props }),
      getCycleData: async (...args) => {
        cycleCalls.push(args);
        if (args[2] === 2) throw new Error('second failed');
        return cycle({ time: 11 });
      },
      getPhDiagram: async () => ph,
      getTsDiagram: async () => ts,
    };

    const result = await loadSysPerfDiagramRun({
      token: 'token',
      workspaceSlug: 'workspace',
      files: [file(1, 'Sheet A'), file(2, 'Sheet B')],
      times: { 0: '10', 1: '20' },
      refrigerant: 'R-134a',
      refrigerants: [{ id: 7, name: 'R-134a' }],
      deps,
    });

    expect(cycleCalls.map((call) => call.slice(2, 6))).toEqual([
      [1, 'Sheet A', 10, 'R-134a'],
      [2, 'Sheet B', 20, 'R-134a'],
    ]);
    expect(result.cache).toEqual({
      0: expect.objectContaining({ time: 11 }),
    });
    expect(result.cycleError).toBeUndefined();
    expect(result.ph).toBe(ph);
    expect(result.ts).toBe(ts);
  });

  it('reports a blocking error when every cycle request rejects', async () => {
    const deps: SysPerfDiagramLoaderDeps = {
      getRefrigerants: async () => ({ data: [] }),
      getRefrigerantProps: async () => ({ data: props }),
      getCycleData: async () => {
        throw new Error('network down');
      },
      getPhDiagram: async () => ph,
      getTsDiagram: async () => ts,
    };

    await expect(
      loadSysPerfDiagramRun({
        token: 'token',
        workspaceSlug: 'workspace',
        files: [file(1, 'Sheet A'), file(2, 'Sheet B')],
        times: {},
        refrigerant: 'R-134a',
        refrigerants: [{ id: 7, name: 'R-134a' }],
        deps,
      }),
    ).resolves.toEqual(
      expect.objectContaining({
        cache: {},
        cycleError: 'network down',
      }),
    );
  });

  it('loads refrigerant options and ignores blank or failed rows', async () => {
    const calls: Parameters<SysPerfDiagramLoaderDeps['getRefrigerants']>[] = [];
    const deps: SysPerfDiagramLoaderDeps = {
      getRefrigerants: async (...args) => {
        calls.push(args);
        return {
          data: [
            { id: 1, name: 'R-134a', formula: '' },
            { id: 2, name: '', formula: '' },
          ],
        };
      },
      getRefrigerantProps: async () => ({ data: props }),
      getCycleData: async () => cycle(),
      getPhDiagram: async () => ph,
      getTsDiagram: async () => ts,
    };

    await expect(
      loadSysPerfDiagramRefrigerants({
        token: 'token',
        workspaceSlug: 'workspace',
        deps,
      }),
    ).resolves.toEqual([{ id: 1, name: 'R-134a' }]);
    expect(calls[0]).toEqual(['token', 'workspace']);

    await expect(
      loadSysPerfDiagramRefrigerants({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: {
          ...deps,
          getRefrigerants: async () => {
            throw new Error('network');
          },
        },
      }),
    ).resolves.toEqual([]);
  });
});
