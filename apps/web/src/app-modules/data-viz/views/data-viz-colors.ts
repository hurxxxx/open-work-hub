// i18n-exempt-file: domain data labels are lookup keys for chart color maps.
import type { PartType } from './sysperf-parts';
import type { SimpleField } from './comp-reliability-graph-config';

export const DATA_VIZ_PLOT_COLORS = {
  transparent: 'rgba(0,0,0,0)',
  white: '#ffffff',
  paper: '#ffffff',
  plot: '#ffffff',
  warmPlot: '#FFFEF8',
  grid: '#e0e0e0',
  graphGrid: '#b8c2cf',
  compareGrid: 'rgba(128,128,128,0.15)',
  lightGrid: '#e5e7eb',
  axisText: '#374151',
  mutedAxisText: '#6b7280',
  phGrid: '#e8ecf2',
  phMinorGrid: '#f0f3f7',
  phPressureGrid: '#c8d1de',
  phPressureMinorGrid: '#eef1f5',
  tsGrid: '#d4d4d4',
  legendBg: 'rgba(255,255,255,0.8)',
  legendBgStrong: 'rgba(255,255,255,0.85)',
} as const;

export const SYSPERF_GRAPH_COLORS = [
  '#4a90d9',
  '#e74c3c',
  '#27ae60',
  '#f39c12',
  '#9b59b6',
  '#1abc9c',
  '#e67e22',
  '#3498db',
  '#e91e63',
  '#00bcd4',
  '#795548',
  '#607d8b',
] as const;

export const SYSPERF_CATEGORY_COLORS: Record<string, string> = {
  목표: '#4472C4',
  시간: '#3B5BDB',
  '냉매측\n압력': '#5B7FA5',
  '냉매측\n온도': '#7A9BBD',
  공기측: '#6B8E7B',
  기타: '#8B8B9E',
};

export const SYSPERF_MATCH_GRID_COLORS = {
  border: '1px solid #bbb',
  outerBorder: '1px solid #999',
  inputBorder: '1px solid #aaa',
  primaryHeader: '#4472C4',
  secondaryHeader: '#5B9BD5',
  fileHeader: '#2E75B6',
  categoryFallback: '#555',
  text: '#1a1a2e',
  mutedText: '#666',
  subtleText: '#888',
  disabledText: '#999',
  row: '#FAFAF5',
  calculatedBg: '#FFF3E0',
  calculatedText: '#E65100',
  subAverageBg: '#FFF4E6',
  successBg: '#E8F0E8',
  noDataBg: '#FDE8E8',
  direct: '#27ae60',
  average: '#e67e22',
  danger: '#e74c3c',
  white: '#fff',
} as const;

export const SYSPERF_MATCH_TABLE_COLORS = {
  active: '#4472C4',
  inactiveBg: '#e8edf5',
  text: '#1a1a2e',
  white: '#fff',
} as const;

export const SYSPERF_PARTS_UI_COLORS = {
  noneBorder: '1px dashed #94a3b8',
  noneBg: '#f1f5f9',
  noneText: '#64748b',
  chipBorder: '1px solid #dce3ef',
  chipBg: '#fff',
  selectedBg: '#4a90d9',
  labelFallbackBg: '#f1f5f9',
  labelFallbackFg: '#374151',
  labelFallbackBorder: '#cbd5e1',
  inactiveBorder: '#eee',
  white: '#fff',
} as const;

export const SYSPERF_PARTS_CATALOG_COLORS = {
  chipBg: '#dbeafe',
  chipText: '#1e40af',
  chipBorder: '1px solid #93c5fd',
  deleteText: '#7b1f1f',
  noneBg: '#f1f5f9',
  noneText: '#64748b',
  noneBorder: '1px dashed #94a3b8',
} as const;

export const SYSPERF_PART_LABEL_COLORS: Record<
  string,
  { bg: string; fg: string; bd: string }
> = {
  내부가변: { bg: '#dbeafe', fg: '#1e40af', bd: '#93c5fd' },
  외부가변: { bg: '#d1fae5', fg: '#065f46', bd: '#6ee7b7' },
  전동: { bg: '#ffedd5', fg: '#c2410c', bd: '#fdba74' },
  경쟁사: { bg: '#ede9fe', fg: '#6b21a8', bd: '#c4b5fd' },
};

export const SYSPERF_PART_TYPE_COLORS: Record<PartType, string> = {
  양산: '#27ae60',
  개발: '#e67e22',
  경쟁사: '#9b59b6',
};

export const SYSPERF_BASE_CAR_BADGE_COLORS = {
  hyundai: { background: '#dbeafe', color: '#1e40af' },
  kia: { background: '#dcfce7', color: '#166534' },
  defaultBrand: { background: '#ede9fe', color: '#5b21b6' },
  firstEra: { background: '#fef3c7', color: '#92400e' },
  secondEra: { background: '#d1fae5', color: '#065f46' },
} as const;

export const COMP_RELIABILITY_SIMPLE_COLORS: Record<SimpleField, string> = {
  pd: 'rgb(249,7,7)',
  ps: 'rgb(2,31,246)',
  crank: 'rgb(242,206,22)',
  td: 'rgb(243,42,206)',
  ts: 'rgb(55,244,240)',
  surface: 'rgb(240,149,43)',
  rpm: 'rgb(0,0,0)',
};

export const COMP_RELIABILITY_VAR_COLORS: Record<string, string> = {
  '토출 압력': 'rgb(237,12,16)',
  '흡입 압력': 'rgb(12,31,237)',
  'Crank Case 압력': 'rgb(242,182,114)',
  '토출 온도': 'rgb(235,77,77)',
  '흡입 온도': 'rgb(12,217,240)',
  '표면 온도-1': 'rgb(232,94,26)',
  'Comp.Speed': 'rgb(0,0,0)',
  '냉매 유량': 'rgb(146,30,230)',
  'ECV 전류': 'rgb(22,219,52)',
  'COMP 토크': 'rgb(190,184,194)',
  '클러치 전압': 'rgb(181,107,62)',
};

export const COMP_RELIABILITY_ELEC_COLORS: Record<string, string> = {
  '토출 압력': 'rgb(255,0,0)',
  '흡입 압력': 'rgb(0,0,255)',
  '챔버 온도': 'rgb(113,242,39)',
  '토출 온도': 'rgb(255,0,128)',
  '흡입 온도': 'rgb(0,191,255)',
  '표면 온도-1': 'rgb(232,94,26)',
  REV: 'rgb(112,48,160)',
  'Comp.Speed': 'rgb(112,48,160)',
  '냉매 유량': 'rgb(146,30,230)',
  'COMP 토크': 'rgb(190,184,194)',
};

export const COMP_RELIABILITY_FALLBACK_COLORS = [
  '#e74c3c',
  '#2980b9',
  '#27ae60',
  '#f39c12',
  '#8e44ad',
  '#1abc9c',
  '#d35400',
  '#2c3e50',
] as const;

export const COMPRESSOR_PERF_CHART_PALETTE = [
  '#7AB8E8',
  '#F08C8C',
  '#80D080',
  '#FFB870',
  '#B59FE0',
  '#FFD56B',
  '#7DD1C1',
  '#F5A5C7',
] as const;

export const COMPRESSOR_PERF_TABLE_CLASSES = {
  groupAltBg: 'bg-[rgb(232,231,231)]',
  groupEndBorder: 'border-b-2 border-b-[rgb(209,209,209)]',
} as const;

export const CORE_MEASUREMENT_COLORS = {
  inSpec: '#2980b9',
  outOfSpec: '#e74c3c',
  measuredLine: '#cfd8dc',
  nominal: '#90a4ae',
} as const;

export const SYSPERF_DIAGRAM_COLORS = {
  saturation: '#000',
  markerOutline: '#fff',
  isoquality: '#b8c2cf',
  isotherm: '#2E7D32',
  isentrope: '#C62828',
  isochor: '#6d4c41',
  isobar: '#7fa9c4',
  isenthalp: '#a06a3c',
  cycle: ['#1e40af', '#b91c1c', '#065f46', '#c2410c', '#6b21a8'],
} as const;

export const SYSPERF_DIAGRAM_TABLE_COLORS = {
  headerBg: '#5B9BD5',
  headerBorder: '1px solid #2E5C85',
  cellBorder: '1px solid #aab7c8',
  pressure: '#1e40af',
  temperature: '#b91c1c',
  enthalpy: '#065f46',
  superheat: '#c2410c',
  noteBg: '#fff8e1',
  noteText: '#8a4b08',
  white: '#fff',
} as const;
