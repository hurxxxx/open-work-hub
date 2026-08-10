import { describe, expect, it } from 'vitest';

import type { SysPerfCarModel } from '../api/dataviz-api';
import {
  SYS_PERF_BASE_CARS_ALL_FILTER_VALUE,
  SYS_PERF_BASE_CAR_BRANDS,
  buildSysPerfBaseCarSavePayload,
  buildSysPerfBaseCarSegments,
  createEmptySysPerfBaseCarDraft,
  filterSysPerfBaseCars,
  sysPerfBaseCarBrandLabelKey,
  updateSysPerfBaseCarDraft,
} from './sysperf-base-cars';

function car(patch: Partial<SysPerfCarModel>): SysPerfCarModel {
  return {
    id: 1,
    brand: SYS_PERF_BASE_CAR_BRANDS.hyundai,
    era: '2',
    year: '2025',
    car_name: 'IONIQ 5',
    model_code: 'NE',
    segment_code: 'C',
    segment_name: 'EV',
    refrigerant: '',
    note: '',
    ...patch,
  };
}

describe('sysperf base cars model', () => {
  it('creates and updates draft values with BASE defaults', () => {
    const draft = createEmptySysPerfBaseCarDraft();

    expect(draft).toEqual({
      brand: SYS_PERF_BASE_CAR_BRANDS.hyundai,
      era: '2',
      year: '',
      car_name: '',
      model_code: '',
      segment_code: '',
      segment_name: '',
    });
    expect(updateSysPerfBaseCarDraft(draft, 'car_name', 'Sonata')).toEqual({
      ...draft,
      car_name: 'Sonata',
    });
  });

  it('filters cars by query, brand, era, and segment', () => {
    const rows = [
      car({ id: 1, car_name: 'IONIQ 5', model_code: 'NE', segment_name: 'EV' }),
      car({
        id: 2,
        brand: SYS_PERF_BASE_CAR_BRANDS.kia,
        era: '1',
        car_name: 'Sorento',
        model_code: 'MQ4',
        segment_name: 'SUV',
      }),
    ];

    expect(
      filterSysPerfBaseCars({
        rows,
        filter: {
          query: 'mq',
          brand: SYS_PERF_BASE_CARS_ALL_FILTER_VALUE,
          era: SYS_PERF_BASE_CARS_ALL_FILTER_VALUE,
          segment: SYS_PERF_BASE_CARS_ALL_FILTER_VALUE,
        },
      }).map((row) => row.id),
    ).toEqual([2]);
    expect(
      filterSysPerfBaseCars({
        rows,
        filter: {
          query: '',
          brand: SYS_PERF_BASE_CAR_BRANDS.kia,
          era: '1',
          segment: 'SUV',
        },
      }).map((row) => row.id),
    ).toEqual([2]);
  });

  it('builds sorted unique segment options and brand label keys', () => {
    expect(
      buildSysPerfBaseCarSegments([
        car({ segment_name: 'SUV' }),
        car({ segment_name: '' }),
        car({ segment_name: 'EV' }),
        car({ segment_name: 'SUV' }),
      ]),
    ).toEqual(['EV', 'SUV']);

    expect(sysPerfBaseCarBrandLabelKey(SYS_PERF_BASE_CAR_BRANDS.genesis)).toBe(
      'genesis',
    );
    expect(sysPerfBaseCarBrandLabelKey('Custom')).toBeNull();
  });

  it('normalizes save payloads and rejects blank car names', () => {
    expect(
      buildSysPerfBaseCarSavePayload(createEmptySysPerfBaseCarDraft()),
    ).toBeNull();
    expect(
      buildSysPerfBaseCarSavePayload({
        ...createEmptySysPerfBaseCarDraft(),
        car_name: '  Tucson  ',
        model_code: '  NX4 ',
        segment_name: ' SUV ',
      }),
    ).toEqual({
      brand: SYS_PERF_BASE_CAR_BRANDS.hyundai,
      era: '2',
      year: '',
      car_name: 'Tucson',
      model_code: 'NX4',
      segment_code: '',
      segment_name: 'SUV',
      refrigerant: '',
      note: '',
    });
  });
});
