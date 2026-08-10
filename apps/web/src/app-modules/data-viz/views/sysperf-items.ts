// i18n-exempt-file: SysPerf standard_name and Excel header contract constants; rendering modules localize display copy separately.
// 시스템 성능 매칭 테이블의 뼈대 — 원본 sys_perf.js L591~661 의 _MI[] / _CAT_COLORS 를
// 그대로 이식. 임의 변경 금지. 필드 의미는 원본 주석 그대로:
//   n        : No (표준항목 고유번호, standard_name "n_nm" 의 n)
//   c        : 카테고리(구분) — 첫 항목에만 표기, 이후 행은 같은 카테고리 (rowspan)
//   nm       : 항목명
//   u        : 단위
//   cs       : 카테고리 rowspan 수 (구분 셀 세로 병합 개수)
//   kw       : 자동찾기 키워드 배열
//   cat_type : 'P'(압력) / 'T'(온도) / 'TIME' — 사이클·시간축 식별
//   avg      : true = 평균 항목 (하위 sub들의 평균, "적정값" 버튼 대상)
//   grp      : 평균 그룹 키 (이 항목이 묶는 하위 그룹명)
//   sub      : 하위 항목이 속한 그룹 키 (들여쓰기·공유매칭 허용)
//   calc     : true = 계산 항목 (S.C / S.H — 매칭 아닌 CoolProp 계산값)
//
// ⚠️ standard_name = `${n}_${nm}` (예: '4_COMP IN', '92_Time (min)'). confirm-match 전송 시
//    반드시 이 포맷이어야 백엔드 CYCLE_MAP 과 맞는다. __none__ 은 전송에서 제외.
import { SYSPERF_CATEGORY_COLORS } from './data-viz-colors';

export interface MeasureItem {
  n: number;
  c?: string;
  nm: string;
  u: string;
  cs?: number;
  kw: string[];
  cat_type?: 'P' | 'T' | 'TIME';
  avg?: boolean;
  grp?: string;
  sub?: string;
  calc?: boolean;
}

export const MEASURE_ITEMS: MeasureItem[] = [
  { n: 1, c: '목표', nm: '개발목표온도', u: '℃', cs: 3, kw: [] },
  { n: 2, nm: '실내평균온도', u: '', kw: ['ROOMAVG', '실내평균', 'ROOM AVG'] },
  { n: 3, nm: 'FBL', u: '', kw: ['FBL'] },
  // 시간 — 목표와 냉매측 사이. x축 기준 (분 단위 권장)
  {
    n: 92,
    c: '시간',
    nm: 'Time (min)',
    u: 'min',
    cs: 1,
    kw: ['TIME(min)', 'Time(min)', 'TIME (min)', 'Time', 'TIME', '시간'],
    cat_type: 'TIME',
  },
  {
    n: 4,
    c: '냉매측\n압력',
    nm: 'COMP IN',
    u: 'kgf/cm2',
    cs: 9,
    kw: ['PS', 'Ps'],
    cat_type: 'P',
  },
  { n: 5, nm: 'COMP OUT', u: '', kw: ['PCO', 'Pd'], cat_type: 'P' },
  { n: 6, nm: 'CRANK', u: '', kw: ['PC', 'CRANK', '크랭크'], cat_type: 'P' },
  { n: 7, nm: 'COND IN', u: '', kw: ['PCI'], cat_type: 'P' },
  { n: 8, nm: 'COND OUT', u: '', kw: ['PCond'], cat_type: 'P' },
  { n: 9, nm: 'TXV IN, ENG.TEI', u: '', kw: ['PEI', 'PTXV IN'], cat_type: 'P' },
  {
    n: 10,
    nm: 'TXV OUT, ENG TEO',
    u: '',
    kw: ['PEO', 'PTXV OUT'],
    cat_type: 'P',
  },
  {
    n: 11,
    nm: 'EVA IN',
    u: '',
    kw: ['EVA IN PRESS', 'EVA IN P'],
    cat_type: 'P',
  },
  { n: 12, nm: 'EVA OUT', u: '', kw: ['EVA OUT P'], cat_type: 'P' },
  {
    n: 13,
    c: '냉매측\n온도',
    nm: 'COMP IN',
    u: '℃',
    cs: 28,
    kw: ['TS', 'Ts'],
    cat_type: 'T',
  },
  { n: 14, nm: 'COMP OUT', u: '', kw: ['TD', 'Td'], cat_type: 'T' },
  {
    n: 15,
    nm: 'COND IN AVG',
    u: '',
    kw: ['TCI', 'TCIN'],
    cat_type: 'T',
    avg: true,
    grp: 'ci',
  },
  { n: 16, nm: 'COND IN 1', u: '', kw: ['COND IN 1'], sub: 'ci' },
  { n: 17, nm: 'COND IN 2', u: '', kw: ['COND IN 2'], sub: 'ci' },
  { n: 18, nm: 'COND IN 3', u: '', kw: ['COND IN 3'], sub: 'ci' },
  { n: 19, nm: 'COND IN 4', u: '', kw: ['COND IN 4'], sub: 'ci' },
  { n: 20, nm: 'COND IN 5', u: '', kw: ['COND IN 5'], sub: 'ci' },
  { n: 21, nm: 'COND IN 6', u: '', kw: ['COND IN 6'], sub: 'ci' },
  { n: 22, nm: 'COND IN 7', u: '', kw: ['COND IN 7'], sub: 'ci' },
  { n: 23, nm: 'COND IN 8', u: '', kw: ['COND IN 8'], sub: 'ci' },
  { n: 24, nm: 'COND IN 9', u: '', kw: ['COND IN 9'], sub: 'ci' },
  {
    n: 25,
    nm: 'COND 전면 AVG',
    u: '',
    kw: ['COND 전면'],
    avg: true,
    grp: 'cf',
  },
  { n: 26, nm: 'COND 전면 주변 1', u: '', kw: ['COND 전면 1'], sub: 'cf' },
  { n: 27, nm: 'COND 전면 주변 2', u: '', kw: ['COND 전면 2'], sub: 'cf' },
  { n: 28, nm: 'COND 전면 주변 3', u: '', kw: ['COND 전면 3'], sub: 'cf' },
  { n: 29, nm: 'COND 전면 주변 4', u: '', kw: ['COND 전면 4'], sub: 'cf' },
  { n: 30, nm: 'COND 전면 주변 5', u: '', kw: ['COND 전면 5'], sub: 'cf' },
  { n: 31, nm: 'COND 전면 주변 6', u: '', kw: ['COND 전면 6'], sub: 'cf' },
  {
    n: 32,
    nm: 'COND OUT',
    u: '',
    kw: ['TCO', 'TCOUT', 'COND OUT', 'CONDOUT'],
    cat_type: 'T',
  },
  {
    n: 33,
    nm: 'TXV IN',
    u: '',
    kw: ['E/TEI', 'TEI', 'TTXV IN', 'TXV IN', 'TXVIN'],
    cat_type: 'T',
  },
  {
    n: 34,
    nm: 'TXV OUT',
    u: '',
    kw: ['E/TEO', 'TEO', 'TTXV OUT', 'TXV OUT', 'TXVOUT'],
    cat_type: 'T',
  },
  { n: 35, nm: 'EVA IN', u: '', kw: ['TEVA IN'], cat_type: 'T' },
  { n: 36, nm: 'EVA OUT', u: '', kw: ['TEVA OUT'], cat_type: 'T' },
  { n: 37, nm: 'S.C (COND OUT)', u: '', kw: [], calc: true },
  { n: 38, nm: 'S.C (TXV IN)', u: '', kw: [], calc: true },
  { n: 39, nm: 'S.H (EVA OUT)', u: '', kw: [], calc: true },
  { n: 40, nm: 'S.H (COMP IN)', u: '', kw: [], calc: true },
  {
    n: 41,
    c: '공기측',
    nm: 'AMBIENT',
    u: '℃',
    cs: 44,
    kw: ['AMB', 'AMBIENT', '외기온'],
  },
  { n: 42, nm: 'HUMIDITY', u: '%', kw: ['HUMIDITY', '습도'] },
  {
    n: 43,
    nm: 'EVA OUT AVG',
    u: '℃',
    kw: ['EVAOUTAVG', 'EVA OUT AVG'],
    avg: true,
    grp: 'eo',
  },
  { n: 44, nm: 'F/EVAOUT 1', u: '℃', kw: ['F/EVAOUT 1', 'EVAOUT1'], sub: 'eo' },
  { n: 45, nm: 'F/EVAOUT 2', u: '℃', kw: ['F/EVAOUT 2'], sub: 'eo' },
  { n: 46, nm: 'F/EVAOUT 3', u: '℃', kw: ['F/EVAOUT 3'], sub: 'eo' },
  { n: 47, nm: 'F/EVAOUT 4', u: '℃', kw: ['F/EVAOUT 4'], sub: 'eo' },
  { n: 48, nm: 'F/EVAOUT 5', u: '℃', kw: ['F/EVAOUT 5'], sub: 'eo' },
  { n: 49, nm: 'F/EVAOUT 6', u: '℃', kw: ['F/EVAOUT 6'], sub: 'eo' },
  { n: 50, nm: 'F/EVAOUT 7', u: '℃', kw: ['F/EVAOUT 7'], sub: 'eo' },
  { n: 51, nm: 'F/EVAOUT 8', u: '℃', kw: ['F/EVAOUT 8'], sub: 'eo' },
  { n: 52, nm: 'F/EVAOUT 9', u: '℃', kw: ['F/EVAOUT 9'], sub: 'eo' },
  { n: 53, nm: 'F/EVAOUT 10', u: '℃', kw: ['F/EVAOUT 10'], sub: 'eo' },
  { n: 54, nm: 'F/EVAOUT 11', u: '℃', kw: ['F/EVAOUT 11'], sub: 'eo' },
  { n: 55, nm: 'F/EVAOUT 12', u: '℃', kw: ['F/EVAOUT 12'], sub: 'eo' },
  {
    n: 56,
    nm: 'Fr VENT AVG',
    u: '℃',
    kw: ['Fr VENTAVG', 'Fr VENT AVG'],
    avg: true,
    grp: 'fv',
  },
  { n: 57, nm: 'Ft VENT DR', u: '℃', kw: ['Ft VENT DR'], sub: 'fv' },
  { n: 58, nm: 'Ft VENT CTDR', u: '℃', kw: ['Ft VENT CTDR'], sub: 'fv' },
  { n: 59, nm: 'Ft VENT CTAS', u: '℃', kw: ['Ft VENT CTAS'], sub: 'fv' },
  { n: 60, nm: 'Ft VENT AS', u: '℃', kw: ['Ft VENT AS'], sub: 'fv' },
  {
    n: 61,
    nm: 'Rr VENT AVG',
    u: '℃',
    kw: ['Rr VENTAVG', 'Rr VENT AVG'],
    avg: true,
    grp: 'rv',
  },
  { n: 62, nm: 'Rr VENT DR', u: '℃', kw: ['Rr VENT DR'], sub: 'rv' },
  { n: 63, nm: 'Rr VENT AS', u: '℃', kw: ['Rr VENT AS'], sub: 'rv' },
  {
    n: 64,
    nm: 'ROOM AVG (A+B OR C+D)',
    u: '℃',
    kw: ['ROOMAVG', 'ROOM AVG'],
    avg: true,
    grp: 'rm',
  },
  {
    n: 65,
    nm: 'BREA AVG (A)',
    u: '℃',
    kw: ['BREAAVG', 'BREA AVG'],
    avg: true,
    grp: 'ba',
    sub: 'rm',
  },
  { n: 66, nm: 'Ft BREA DR', u: '℃', kw: ['Ft BREA DR'], sub: 'ba' },
  { n: 67, nm: 'Ft BREA AS', u: '℃', kw: ['Ft BREA AS'], sub: 'ba' },
  { n: 68, nm: 'R2 BREA DR', u: '℃', kw: ['R2 BREA DR'], sub: 'ba' },
  { n: 69, nm: 'R2 BREA AS', u: '℃', kw: ['R2 BREA AS'], sub: 'ba' },
  {
    n: 70,
    nm: 'FOOT AVG (B)',
    u: '℃',
    kw: ['FOOTAVG', 'FOOT AVG'],
    avg: true,
    grp: 'fa',
    sub: 'rm',
  },
  { n: 71, nm: 'Ft FOOT DR', u: '℃', kw: ['Ft FOOT DR'], sub: 'fa' },
  { n: 72, nm: 'Ft FOOT AS', u: '℃', kw: ['Ft FOOT AS'], sub: 'fa' },
  { n: 73, nm: 'R2 FOOT DR', u: '℃', kw: ['R2 FOOT DR'], sub: 'fa' },
  { n: 74, nm: 'R2 FOOT AS', u: '℃', kw: ['R2 FOOT AS'], sub: 'fa' },
  {
    n: 75,
    nm: 'Ft ROOMAVG (C)',
    u: '℃',
    kw: ['Ft ROOMAVG'],
    avg: true,
    grp: 'fc',
    sub: 'rm',
  },
  { n: 76, nm: 'Ft BREA DR', u: '℃', kw: [], sub: 'fc' },
  { n: 77, nm: 'Ft BREA AS', u: '℃', kw: [], sub: 'fc' },
  { n: 78, nm: 'R2 FOOT DR', u: '℃', kw: [], sub: 'fc' },
  { n: 79, nm: 'R2 FOOT AS', u: '℃', kw: [], sub: 'fc' },
  {
    n: 80,
    nm: 'R2 ROOMAVG (D)',
    u: '℃',
    kw: ['R2 ROOMAVG'],
    avg: true,
    grp: 'rd',
    sub: 'rm',
  },
  { n: 81, nm: 'R2 BREA DR', u: '℃', kw: ['R2 BREA DR'], sub: 'rd' },
  { n: 82, nm: 'R2 BREA AS', u: '℃', kw: ['R2 BREA AS'], sub: 'rd' },
  { n: 83, nm: 'R2 FOOT DR', u: '℃', kw: ['R2 FOOT DR'], sub: 'rd' },
  { n: 84, nm: 'R2 FOOT AS', u: '℃', kw: ['R2 FOOT AS'], sub: 'rd' },
  {
    n: 85,
    c: '기타',
    nm: 'CAR SPEED',
    u: 'KMH',
    cs: 7,
    kw: ['CARSPEED', 'CAR SPEED', '차속'],
  },
  { n: 86, nm: 'ENGINE RPM', u: 'RPM', kw: ['ENG RPM', 'RPM', '엔진회전수'] },
  { n: 87, nm: 'RAD UP', u: '℃', kw: ['RAD UP'] },
  { n: 88, nm: 'RAD LOW', u: '℃', kw: ['RAD LOW'] },
  { n: 89, nm: 'BLWR VOLTS', u: 'V', kw: ['BLWR VOLTS', '블로워전압'] },
  { n: 90, nm: 'C/F VOLTS (H)', u: 'V', kw: ['C/F VOLTS (H)', 'CF VOLTS H'] },
  { n: 91, nm: 'C/F VOLTS (L)', u: 'V', kw: ['C/F VOLTS (L)', 'CF VOLTS L'] },
];

export const CAT_COLORS = SYSPERF_CATEGORY_COLORS;

// standard_name 포맷 헬퍼 — 백엔드 CYCLE_MAP / column_mapping 과 일치하는 `${n}_${nm}`.
export function stdName(it: MeasureItem): string {
  return `${it.n}_${it.nm}`;
}
