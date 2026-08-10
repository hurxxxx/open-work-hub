// i18n-exempt-file: legacy durability Excel/API chart column keys and graph labels are data contracts.
import type { DurabilityGraphResponse } from '../api/dataviz-api';
import {
  COMP_RELIABILITY_ELEC_COLORS,
  COMP_RELIABILITY_FALLBACK_COLORS,
  COMP_RELIABILITY_SIMPLE_COLORS,
  COMP_RELIABILITY_VAR_COLORS,
} from './data-viz-colors';

export interface VarReliabilityGraphGroup {
  title: string;
  main: string[];
  sub: string[];
  yLabel: string;
  y2Label: string;
}

export const CHART_GROUPS_VAR: VarReliabilityGraphGroup[] = [
  {
    title: '압력',
    main: ['토출 압력'],
    sub: ['흡입 압력', 'Crank Case 압력'],
    yLabel: '토출압력 (kgf/cm2)',
    y2Label: '흡입, Crank case 압력 (kgf/cm2)',
  },
  {
    title: '온도',
    main: ['토출 온도', '표면 온도-1'],
    sub: ['흡입 온도'],
    yLabel: '토출, 표면온도 (℃)',
    y2Label: '흡입 온도 (℃)',
  },
  {
    title: '냉매유량',
    main: ['냉매 유량'],
    sub: ['Comp.Speed'],
    yLabel: '냉매유량 (kg/h)',
    y2Label: 'Comp.Speed (RPM)',
  },
  {
    title: '차압/ECV',
    main: ['Pc-Ps'],
    sub: ['ECV 전류'],
    yLabel: 'Pc-Ps (kgf/cm2)',
    y2Label: 'ECV 전류 (A)',
  },
  {
    title: 'SC/SH',
    main: ['TXV In SC Temp'],
    sub: ['Suction SH Temp'],
    yLabel: 'TXV SC (℃)',
    y2Label: 'Suction SH (℃)',
  },
];

export interface ElectricTrace {
  col: string;
  axis: 'y' | 'y2';
}

export interface ElectricGraphZoom {
  title: string;
  xMode: string;
  xParam: number[];
  yRange: [number, number];
  y2Range: [number, number];
}

export interface ElectricGraphConfig {
  title: string;
  xMode: string;
  xParam: number | number[];
  xUnit: 'min' | 'sec' | 'hr';
  traces: ElectricTrace[];
  yLabel: string;
  y2Label: string;
  yRange: [number, number];
  y2Range: [number, number];
  zoomGraphs?: ElectricGraphZoom[];
}

export interface ElectricGraphZoomResult {
  z: ElectricGraphZoom;
  resp: DurabilityGraphResponse | null;
}

export const ELEC_GRAPH_CONFIG: Record<string, ElectricGraphConfig> = {
  고온연속: {
    title: '고온연속',
    xMode: 'last_min',
    xParam: 210,
    xUnit: 'min',
    traces: [
      { col: '토출 압력', axis: 'y' },
      { col: '흡입 압력', axis: 'y' },
      { col: 'Comp.Speed', axis: 'y' },
      { col: '챔버 온도', axis: 'y2' },
    ],
    yLabel: 'Pressure (kPa), REV',
    y2Label: 'Temp (℃)',
    yRange: [0, 3500],
    y2Range: [0, 140],
  },
  저온연속: {
    title: '저온연속',
    xMode: 'last_min',
    xParam: 260,
    xUnit: 'min',
    traces: [
      { col: '토출 압력', axis: 'y' },
      { col: '흡입 압력', axis: 'y' },
      { col: 'Comp.Speed', axis: 'y' },
      { col: '챔버 온도', axis: 'y2' },
    ],
    yLabel: 'Pressure (kPa), REV',
    y2Label: 'Temp (℃)',
    yRange: [0, 3500],
    y2Range: [-30, 40],
  },
  고차압기동: {
    title: '고차압기동',
    xMode: 'rpm_drop',
    xParam: [180, 120],
    xUnit: 'sec',
    traces: [
      { col: '토출 압력', axis: 'y' },
      { col: '흡입 압력', axis: 'y' },
      { col: 'Comp.Speed', axis: 'y2' },
    ],
    yLabel: 'Pressure (kPa)',
    y2Label: 'REV',
    yRange: [0, 2500],
    y2Range: [0, 3500],
  },
  'RPM RAMP RATE': {
    title: 'RPM RAMP RATE',
    xMode: 'rpm_reach',
    xParam: [5000, 60, 120],
    xUnit: 'sec',
    traces: [
      { col: '토출 압력', axis: 'y' },
      { col: '흡입 압력', axis: 'y' },
      { col: 'Comp.Speed', axis: 'y2' },
      { col: '챔버 온도', axis: 'y2' },
    ],
    yLabel: 'Pressure (kPa)',
    y2Label: 'Temp (℃), REV/100',
    yRange: [0, 1600],
    y2Range: [0, 80],
    zoomGraphs: [
      {
        title: 'RPM 증가 구간',
        xMode: 'pd_rise',
        xParam: [1000, 4, 1],
        yRange: [0, 1600],
        y2Range: [0, 80],
      },
      {
        title: 'RPM 감소 구간',
        xMode: 'pd_fall',
        xParam: [400, 4, 1],
        yRange: [0, 1600],
        y2Range: [0, 80],
      },
    ],
  },
  '온도 Cycle': {
    title: '온도 Cycle',
    xMode: 'range_sec',
    xParam: [0, 12],
    xUnit: 'sec',
    traces: [
      { col: '토출 압력', axis: 'y' },
      { col: '흡입 압력', axis: 'y' },
      { col: 'Comp.Speed', axis: 'y2' },
      { col: '챔버 온도', axis: 'y2' },
    ],
    yLabel: 'Pressure (kPa)',
    y2Label: 'Temp (℃), REV/100',
    yRange: [0, 1800],
    y2Range: [-40, 140],
  },
  '인버터 저전압 ON/OFF': {
    title: '인버터 저전압 ON/OFF',
    xMode: 'last_hr',
    xParam: 72,
    xUnit: 'hr',
    traces: [
      { col: '토출 압력', axis: 'y' },
      { col: '흡입 압력', axis: 'y' },
      { col: '토출 온도', axis: 'y2' },
      { col: '흡입 온도', axis: 'y2' },
    ],
    yLabel: 'Pressure (kPa)',
    y2Label: 'Temp (℃)',
    yRange: [0, 1600],
    y2Range: [0, 160],
  },
};

export const SIMPLE_FIELDS = [
  'pd',
  'ps',
  'crank',
  'td',
  'ts',
  'surface',
  'rpm',
] as const;

export type SimpleField = (typeof SIMPLE_FIELDS)[number];

export const SIMPLE_COLORS = COMP_RELIABILITY_SIMPLE_COLORS;

export const SIMPLE_LABELS: Record<SimpleField, string> = {
  pd: '토출압력',
  ps: '흡입압력',
  crank: 'Crank 압력',
  td: '토출온도',
  ts: '흡입온도',
  surface: '표면온도',
  rpm: 'RPM',
};

const COL_COLORS_VAR = COMP_RELIABILITY_VAR_COLORS;
const COL_COLORS_ELEC = COMP_RELIABILITY_ELEC_COLORS;
const FALLBACK_COLORS = COMP_RELIABILITY_FALLBACK_COLORS;

export function varReliabilityColor(column: string, index: number): string {
  return (
    COL_COLORS_VAR[column] || FALLBACK_COLORS[index % FALLBACK_COLORS.length]
  );
}

export function electricReliabilityColor(
  column: string,
  index: number,
): string {
  return (
    COL_COLORS_ELEC[column] || FALLBACK_COLORS[index % FALLBACK_COLORS.length]
  );
}
