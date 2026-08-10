import type {
  SysPerfCarModel,
  SysPerfCarModelSavePayload,
} from '../api/dataviz-api';

export const SYS_PERF_BASE_CARS_ALL_FILTER_VALUE = '__all__';

export const SYS_PERF_BASE_CAR_BRANDS = {
  hyundai: '현대', // i18n-exempt-line: stored BASE brand value
  kia: '기아', // i18n-exempt-line: stored BASE brand value
  genesis: '제네시스', // i18n-exempt-line: stored BASE brand value
} as const;

export const SYS_PERF_BASE_CAR_BRAND_OPTIONS = [
  { value: SYS_PERF_BASE_CAR_BRANDS.hyundai, labelKey: 'hyundai' },
  { value: SYS_PERF_BASE_CAR_BRANDS.kia, labelKey: 'kia' },
  { value: SYS_PERF_BASE_CAR_BRANDS.genesis, labelKey: 'genesis' },
] as const;

export const SYS_PERF_BASE_CAR_ERA_OPTIONS = [
  { value: '1', labelKey: 'first' },
  { value: '2', labelKey: 'second' },
] as const;

export const SYS_PERF_BASE_CAR_TABLE_HEADER_KEYS = [
  'era',
  'brand',
  'year',
  'carName',
  'modelCode',
  'segmentCode',
  'segmentName',
  'actions',
] as const;

export interface SysPerfBaseCarDraft {
  brand: string;
  era: string;
  year: string;
  car_name: string;
  model_code: string;
  segment_code: string;
  segment_name: string;
}

export interface SysPerfBaseCarFilter {
  query: string;
  brand: string;
  era: string;
  segment: string;
}

export function createEmptySysPerfBaseCarDraft(): SysPerfBaseCarDraft {
  return {
    brand: SYS_PERF_BASE_CAR_BRANDS.hyundai,
    era: '2',
    year: '',
    car_name: '',
    model_code: '',
    segment_code: '',
    segment_name: '',
  };
}

export function updateSysPerfBaseCarDraft(
  draft: SysPerfBaseCarDraft,
  field: keyof SysPerfBaseCarDraft,
  value: string,
): SysPerfBaseCarDraft {
  return { ...draft, [field]: value };
}

export function sysPerfBaseCarBrandLabelKey(brand: string): string | null {
  const option = SYS_PERF_BASE_CAR_BRAND_OPTIONS.find(
    (item) => item.value === brand,
  );
  return option?.labelKey ?? null;
}

export function buildSysPerfBaseCarSegments(rows: SysPerfCarModel[]): string[] {
  return Array.from(
    new Set(rows.map((row) => row.segment_name).filter(Boolean)),
  ).sort();
}

export function filterSysPerfBaseCars({
  rows,
  filter,
}: {
  rows: SysPerfCarModel[];
  filter: SysPerfBaseCarFilter;
}): SysPerfCarModel[] {
  const query = filter.query.trim().toLowerCase();
  return rows.filter((row) => {
    if (
      query &&
      !row.car_name.toLowerCase().includes(query) &&
      !row.model_code.toLowerCase().includes(query)
    ) {
      return false;
    }
    if (
      filter.brand !== SYS_PERF_BASE_CARS_ALL_FILTER_VALUE &&
      row.brand !== filter.brand
    ) {
      return false;
    }
    if (
      filter.era !== SYS_PERF_BASE_CARS_ALL_FILTER_VALUE &&
      row.era !== filter.era
    ) {
      return false;
    }
    if (
      filter.segment !== SYS_PERF_BASE_CARS_ALL_FILTER_VALUE &&
      row.segment_name !== filter.segment
    ) {
      return false;
    }
    return true;
  });
}

export function buildSysPerfBaseCarSavePayload(
  draft: SysPerfBaseCarDraft,
): SysPerfCarModelSavePayload | null {
  const carName = draft.car_name.trim();
  if (!carName) return null;
  return {
    brand: draft.brand.trim(),
    era: draft.era.trim(),
    year: draft.year.trim(),
    car_name: carName,
    model_code: draft.model_code.trim(),
    segment_code: draft.segment_code.trim(),
    segment_name: draft.segment_name.trim(),
    refrigerant: '',
    note: '',
  };
}
