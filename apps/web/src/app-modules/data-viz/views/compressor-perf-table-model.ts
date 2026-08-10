import type { PerfAverage, PerfRow } from '../api/dataviz-api';

export interface GroupedPerfRow<T> {
  row: T;
  groupIndex: number;
  isGroupEnd: boolean;
}

export function testGroupFamily(value: unknown): string {
  return String(value ?? '')
    .replace(/\d+/g, '')
    .trim();
}

export function testGroupOrder(value: unknown): number {
  const match = String(value ?? '').match(/(\d+)/);
  return match ? parseInt(match[1], 10) : 9999;
}

export function testDateValue(value: unknown): number {
  const str = String(value ?? '').trim();
  if (!str) return 0;
  const time = new Date(str).getTime();
  return Number.isFinite(time) ? time : 0;
}

export function compareTestGroup(a: unknown, b: unknown): number {
  const familyCmp = testGroupFamily(a).localeCompare(testGroupFamily(b));
  if (familyCmp !== 0) return familyCmp;
  return testGroupOrder(a) - testGroupOrder(b);
}

export function groupPerfRowsBySerial(
  rows: PerfRow[],
): GroupedPerfRow<PerfRow>[] {
  const groups = new Map<string, PerfRow[]>();
  rows.forEach((row) => {
    const key = String(row.serial_no ?? '');
    const list = groups.get(key);
    if (list) list.push(row);
    else groups.set(key, [row]);
  });

  for (const list of groups.values()) {
    list.sort((a, b) => compareTestGroup(a.test_group, b.test_group));
  }

  const entries = Array.from(groups.entries());
  entries.sort(([, a], [, b]) => {
    const ad = Math.max(...a.map((row) => testDateValue(row.test_date)));
    const bd = Math.max(...b.map((row) => testDateValue(row.test_date)));
    return bd - ad;
  });

  return entries.flatMap(([, list], groupIndex) =>
    list.map((row, index) => ({
      row,
      groupIndex,
      isGroupEnd: index === list.length - 1,
    })),
  );
}

export function groupPerfAverages(
  rows: PerfAverage[],
  options: { showComponent?: boolean; showSerial?: boolean } = {},
): GroupedPerfRow<PerfAverage>[] {
  const groupKey = (row: PerfAverage): string => {
    if (options.showSerial) return String(row.serial_no ?? '');
    if (options.showComponent) return String(row.comp_type ?? '');
    return '__all__';
  };
  const groups = new Map<string, PerfAverage[]>();
  rows.forEach((row) => {
    const key = groupKey(row);
    const list = groups.get(key);
    if (list) list.push(row);
    else groups.set(key, [row]);
  });

  for (const list of groups.values()) {
    list.sort((a, b) => compareTestGroup(a.test_group, b.test_group));
  }

  const entries = Array.from(groups.entries());
  return entries.flatMap(([, list], groupIndex) =>
    list.map((row, index) => ({
      row,
      groupIndex,
      isGroupEnd: index === list.length - 1,
    })),
  );
}

const DECIMAL_PLACES: Record<string, number> = {
  rpm: 0,
  pd: 0,
  td: 1,
  ps: 1,
  ts: 1,
  pc: 1,
  mass_flow: 2,
  vol_eff: 2,
  ocr: 2,
  cooling_cap_a: 2,
  cooling_cap_f: 2,
  power_kw: 2,
  cop_sc: 2,
  torque: 2,
  heat_balance: 2,
};

export function formatPerfValue(value: unknown): string {
  if (value == null || value === '') return '-';
  if (typeof value === 'number')
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

export function formatPerfNumber(value: unknown, key?: string): string {
  if (value == null || value === '') return '-';
  if (typeof value !== 'number') return String(value);
  const decimals = key != null ? DECIMAL_PLACES[key] : undefined;
  if (decimals !== undefined) return value.toFixed(decimals);
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}
