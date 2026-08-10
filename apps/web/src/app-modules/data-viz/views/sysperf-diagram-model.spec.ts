import { describe, expect, it } from 'vitest';

import type { SysPerfRefrigerantPropRow } from '../api/dataviz-api';
import {
  SYS_PERF_KGFCM2_TO_KPA,
  SYS_PERF_TS_AXIS_DEFAULTS,
  buildDiagramTableRows,
  buildMatchWarnings,
  buildPhPlotModel,
  buildTsPlotModel,
  normalizeSysPerfTsAxis,
  resolveCycleEnthalpy,
  resolveCycleEntropy,
  type SysPerfDiagramCycleCacheEntry,
  type SysPerfDiagramPlotLabels,
} from './sysperf-diagram';

function prop(
  patch: Partial<SysPerfRefrigerantPropRow>,
): SysPerfRefrigerantPropRow {
  return {
    temperature: null,
    sat_pressure_kgcm2: null,
    sat_pressure_kpa: null,
    sat_pressure_bar: null,
    liq_enthalpy: null,
    vap_enthalpy: null,
    liq_entropy: null,
    vap_entropy: null,
    liq_specific_vol: null,
    vap_specific_vol: null,
    ...patch,
  };
}

function cycle(
  patch: Partial<SysPerfDiagramCycleCacheEntry>,
): SysPerfDiagramCycleCacheEntry {
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

const props = [
  prop({
    temperature: 0,
    sat_pressure_kpa: 100,
    liq_enthalpy: 100,
    vap_enthalpy: 200,
    liq_entropy: 1,
    vap_entropy: 2,
  }),
  prop({
    temperature: 10,
    sat_pressure_kpa: 200,
    liq_enthalpy: 110,
    vap_enthalpy: 220,
    liq_entropy: 1.2,
    vap_entropy: 2.4,
  }),
];

const labels: SysPerfDiagramPlotLabels = {
  saturationCurve: 'saturation',
  criticalPoint: 'critical',
  cycleFileName: ({ index, time }) => `cycle-${index}-${time.toFixed(1)}`,
  axes: {
    enthalpy: 'enthalpy',
    pressure: 'pressure',
    entropy: 'entropy',
    temperature: 'temperature',
  },
  phTitle: ({ refrigerant }) => `ph-${refrigerant}`,
  tsTitle: ({ refrigerant }) => `ts-${refrigerant}`,
};

describe('sysperf diagram model', () => {
  it('normalizes invalid T-S axis settings back to safe defaults', () => {
    expect(
      normalizeSysPerfTsAxis({
        xMin: Number.NaN,
        xMax: Number.NaN,
        xTick: 0,
        yMin: 10,
        yMax: 10,
        yTick: Number.POSITIVE_INFINITY,
      }),
    ).toEqual(SYS_PERF_TS_AXIS_DEFAULTS);
  });

  it('prefers server enthalpy and entropy before client interpolation', () => {
    const entry = cycle({
      cycle: {
        'Comp In Pressure': 1,
        'Comp In Temperature': 5,
      },
      enthalpy: { 'Comp In Enthalpy': 123 },
      entropy: { 'Comp In Entropy': 4.5 },
    });

    expect(resolveCycleEnthalpy(entry, props, 'Comp In')).toBe(123);
    expect(resolveCycleEntropy(entry, props, 'Comp In')).toBe(4.5);
  });

  it('falls back to refrigerant property interpolation when server values are missing', () => {
    const entry = cycle({
      cycle: {
        'Comp In Pressure': 1,
        'Comp In Temperature': 5,
        'Comp Out Pressure': 3,
        'Comp Out Temperature': 5,
      },
    });

    expect(resolveCycleEnthalpy(entry, props, 'Comp In')).toBe(210);
    expect(resolveCycleEntropy(entry, props, 'Comp Out')).toBe(1.1);
  });

  it('builds eight table rows with formatted values, fallback notes, and SH/SC fields', () => {
    const rows = buildDiagramTableRows({
      cached: cycle({
        cycle: {
          'Comp In Pressure': 1.234,
          'Comp In Temperature': 12.34,
          'TXV In Pressure': 2,
          'TXV In Temperature': 6,
          'TXV Out Pressure': 1.2,
          'TXV Out Temperature': 4,
          'Evap In Pressure': 1.1,
          'Evap In Temperature': 5,
        },
        enthalpy: { 'Comp In Enthalpy': 123.45 },
        mappings: {
          'Comp In Pressure': 'AltP',
          'Comp In Temperature': 'AltT',
        },
        sh_sc: {
          'Comp In SH': 5.44,
          'TXV In SC': 3.21,
        },
        isenthalpic_notes: ['TXV Out inherited', 'HVAC In inherited'],
        warnings: {
          'Comp In': ['server warning'],
        },
      }),
      props: [],
      fallbackNote: ({ expected, actual }) => `fallback ${expected}/${actual}`,
      txvIsenthalpic: 'txv isenthalpic',
      hvacInherits: 'hvac inherits',
    });

    expect(rows).toHaveLength(8);
    expect(rows[0]).toEqual(
      expect.objectContaining({
        no: 1,
        label: 'Comp In',
        p: '1.23',
        t: '12.3',
        h: '123.5',
        sh: '5.4',
      }),
    );
    expect(rows[0].notes).toEqual([
      'fallback Ps/AltP',
      'fallback Ts/AltT',
      'server warning',
    ]);
    expect(rows[4].sc).toBe('3.2');
    expect(rows[5].notes).toContain('txv isenthalpic');
    expect(rows[6].notes).toContain('hvac inherits');
  });

  it('reports compressor pressure match warnings per file', () => {
    const warnings = buildMatchWarnings({
      fileCount: 2,
      cache: {
        0: cycle({
          cycle: {
            'Comp In Pressure': 9,
            'Comp Out Pressure': 10,
          },
        }),
        1: cycle({
          cycle: {
            'Comp In Pressure': 1,
            'Comp Out Pressure': 10,
          },
        }),
      },
      formatWarning: ({ index, inPressure, outPressure }) =>
        `${index}:${inPressure}/${outPressure}`,
    });

    expect(warnings).toEqual(['1:9.00/10.00']);
  });

  it('builds P-H plot traces with kPa background conversion and closed cycles', () => {
    const model = buildPhPlotModel({
      ph: {
        status: 'ok',
        has_coolprop: true,
        refrigerant: 'R',
        saturation: { h: [100], p: [SYS_PERF_KGFCM2_TO_KPA] },
        isotherms: [],
        isentropes: [],
        isoquality: [{ h: [1], p: [SYS_PERF_KGFCM2_TO_KPA] }],
        isochor: [],
        critical: { T: null, P: null, h: null },
      },
      cache: {
        0: cycle({
          cycle: {
            'Comp In Pressure': 2,
            'Comp In Temperature': 5,
          },
          enthalpy: { 'Comp In Enthalpy': 210 },
        }),
      },
      fileCount: 1,
      props,
      refrigerant: 'R',
      labels,
    });

    expect((model.traces[0].y as number[])[0]).toBe(1);
    const cycleTrace = model.traces.find(
      (trace) => trace.name === 'cycle-1-30.0',
    );
    expect(cycleTrace?.x).toEqual([210, 210]);
    expect(cycleTrace?.y).toEqual([2, 2]);
    expect(model.layout.title).toEqual(
      expect.objectContaining({ text: 'ph-R' }),
    );
  });

  it('builds T-S plot traces with supplied axis ranges and closed cycles', () => {
    const model = buildTsPlotModel({
      ts: {
        status: 'ok',
        has_coolprop: true,
        refrigerant: 'R',
        saturation: { s: [1], t: [10] },
        isobars: [],
        isenthalps: [],
        critical: { T: null, s: null, P: null },
      },
      cache: {
        0: cycle({
          cycle: {
            'Comp In Temperature': 12,
          },
          entropy: { 'Comp In Entropy': 1.5 },
        }),
      },
      fileCount: 1,
      props,
      refrigerant: 'R',
      axis: {
        xMin: 0,
        xMax: 3,
        xTick: 0.5,
        yMin: -20,
        yMax: 120,
        yTick: 20,
      },
      labels,
    });

    const cycleTrace = model.traces.find(
      (trace) => trace.name === 'cycle-1-30.0',
    );
    expect(cycleTrace?.x).toEqual([1.5, 1.5]);
    expect(cycleTrace?.y).toEqual([12, 12]);
    expect(model.layout.xaxis).toEqual(
      expect.objectContaining({ range: [0, 3] }),
    );
    expect(model.layout.yaxis).toEqual(expect.objectContaining({ dtick: 20 }));
  });
});
