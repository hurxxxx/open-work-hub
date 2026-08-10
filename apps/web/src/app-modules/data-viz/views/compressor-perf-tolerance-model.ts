import type {
  ProfileTolCell,
  TolSign,
  ToleranceAllResponse,
} from '../api/dataviz-api';

export type RefToleranceValues = Record<string, Record<string, number | null>>;
export type ProfileToleranceValues = Record<
  string,
  Record<string, ProfileTolCell>
>;
export type ProfileToleranceProfiles = Record<string, ProfileToleranceValues>;

export const DEFAULT_REF_GROUPS = [
  'ES 1',
  'ES 2',
  'ES 3',
  'ES 4',
  'ES 5',
  'ES 6',
] as const;

// Capacity-specific approved reference value columns.
export const REF_TOLERANCE_FIELDS = [
  'rpm',
  'pd',
  'ps',
  'cooling_cap_a',
  'power_kw',
  'torque',
  'vol_eff',
] as const;

export const REF_TOLERANCE_FIELD_LABELS: Record<string, string> = {
  rpm: 'RPM',
  pd: 'Pd',
  ps: 'Ps',
  cooling_cap_a: 'Cool.capa',
  power_kw: 'Power',
  torque: 'Torque',
  vol_eff: 'Vol.eff',
};

export const TEST_TOLERANCE_FIELDS = [
  'rpm',
  'pd',
  'ps',
  'superheat',
  'subcool',
] as const;

export const TEST_TOLERANCE_FIELD_KEYS = [
  'rpm',
  'pd',
  'ps',
  'superheat',
  'subcool',
] as const;

export const TOLERANCE_SIGN_OPTIONS: TolSign[] = ['±', '+', '-', '편측'];

export function numberOrNull(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function trailingNum(value: string): number {
  return parseInt(value.match(/(\d+)\s*$/)?.[1] ?? '0', 10);
}

function groupPrefix(value: string): string {
  return value.replace(/(\d+)\s*$/, '');
}

export function profileToleranceGroups(
  category: string,
  values: ProfileToleranceValues,
  rowCount: number,
): string[] {
  const prefix = category.trim() || 'ES';
  const generated = Array.from(
    { length: rowCount },
    (_, index) => `${prefix}${index + 1}`,
  );
  const all = Array.from(new Set([...generated, ...Object.keys(values)]));
  return all.sort((a, b) => {
    const prefixCompare = groupPrefix(a).localeCompare(groupPrefix(b));
    if (prefixCompare !== 0) return prefixCompare;
    return trailingNum(a) - trailingNum(b);
  });
}

export function profileToleranceRowCount(
  values: ProfileToleranceValues,
): number {
  return Math.max(3, Object.keys(values).length);
}

export function nonEmptyProfileToleranceGroups(
  values: ProfileToleranceValues,
): string[] {
  return Object.keys(values)
    .filter((group) =>
      Object.values(values[group] ?? {}).some(
        (cell) =>
          cell && (cell.ref != null || cell.tol != null || cell.lower != null),
      ),
    )
    .sort((a, b) => trailingNum(a) - trailingNum(b));
}

export function formatProfileToleranceCell(
  cell: ProfileTolCell | undefined,
): string {
  if (!cell || (cell.ref == null && cell.tol == null && cell.lower == null)) {
    return '-';
  }
  const ref = cell.ref != null ? String(cell.ref) : '';
  let tolerance = '';
  if (cell.sign === '편측') {
    const upper = cell.tol != null ? `+${cell.tol}` : '';
    const lower = cell.lower != null ? `-${cell.lower}` : '';
    const pair = [upper, lower].filter(Boolean).join('/');
    tolerance = pair ? ` ${pair}` : '';
  } else if (cell.tol != null) {
    tolerance = ` ${cell.sign || '±'} ${cell.tol}`;
  }
  return `${ref}${tolerance}`.trim();
}

export function sortToleranceCapModelKeys(
  data: ToleranceAllResponse,
): string[] {
  return Object.keys(data.cap_models).sort((a, b) => {
    const left = data.cap_models[a];
    const right = data.cap_models[b];
    const leftCapacity =
      parseInt(String(left.capacity).replace(/[^0-9]/g, ''), 10) || 0;
    const rightCapacity =
      parseInt(String(right.capacity).replace(/[^0-9]/g, ''), 10) || 0;
    if (leftCapacity !== rightCapacity) return leftCapacity - rightCapacity;
    return String(left.model).localeCompare(String(right.model));
  });
}

export function toleranceEsOrder(value: string): number {
  const match = value.match(/(\d+)/);
  return match ? parseInt(match[1], 10) : 9999;
}
