import { describe, expect, it } from 'vitest';

import type {
  SysPerfCarModel,
  SysPerfCarModelSavePayload,
} from '../api/dataviz-api';
import { SYS_PERF_BASE_CAR_BRANDS } from './sysperf-base-cars';
import {
  deleteSysPerfBaseCarModel,
  isSysPerfBaseCarDraftSubmittable,
  loadSysPerfBaseCarModels,
  saveSysPerfBaseCarModel,
  type SysPerfBaseCarsLoaderDeps,
} from './sysperf-base-cars-loader';

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

function deps(
  patch: Partial<SysPerfBaseCarsLoaderDeps>,
): SysPerfBaseCarsLoaderDeps {
  return {
    getCarModels: async () => ({ data: [] }),
    saveCarModel: async () => ({ status: 'ok' }),
    deleteCarModel: async () => ({ status: 'ok' }),
    ...patch,
  };
}

describe('sysperf base cars loader', () => {
  it('loads car models with the default empty API filters', async () => {
    const calls: Parameters<SysPerfBaseCarsLoaderDeps['getCarModels']>[] = [];

    await expect(
      loadSysPerfBaseCarModels({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: deps({
          getCarModels: async (...args) => {
            calls.push(args);
            return { data: [car({ id: 7, car_name: 'Tucson' })] };
          },
        }),
      }),
    ).resolves.toEqual([car({ id: 7, car_name: 'Tucson' })]);
    expect(calls[0]).toEqual(['token', 'workspace', {}]);
  });

  it('propagates load failures', async () => {
    await expect(
      loadSysPerfBaseCarModels({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: deps({
          getCarModels: async () => {
            throw new Error('network');
          },
        }),
      }),
    ).rejects.toThrow('network');
  });

  it('identifies blank car names as not submittable', () => {
    expect(
      isSysPerfBaseCarDraftSubmittable({
        brand: SYS_PERF_BASE_CAR_BRANDS.hyundai,
        era: '2',
        year: '',
        car_name: '   ',
        model_code: 'NE',
        segment_code: 'C',
        segment_name: 'EV',
      }),
    ).toBe(false);
    expect(
      isSysPerfBaseCarDraftSubmittable({
        brand: SYS_PERF_BASE_CAR_BRANDS.hyundai,
        era: '2',
        year: '',
        car_name: 'Tucson',
        model_code: '',
        segment_code: '',
        segment_name: '',
      }),
    ).toBe(true);
  });

  it('returns null and skips the API adapter for blank car names', async () => {
    const calls: Parameters<SysPerfBaseCarsLoaderDeps['saveCarModel']>[] = [];

    await expect(
      saveSysPerfBaseCarModel({
        token: 'token',
        workspaceSlug: 'workspace',
        draft: {
          brand: SYS_PERF_BASE_CAR_BRANDS.hyundai,
          era: '2',
          year: '',
          car_name: '   ',
          model_code: '',
          segment_code: '',
          segment_name: '',
        },
        deps: deps({
          saveCarModel: async (...args) => {
            calls.push(args);
            return { status: 'ok' };
          },
        }),
      }),
    ).resolves.toBeNull();
    expect(calls).toEqual([]);
  });

  it('saves through the API adapter with the normalized payload', async () => {
    const calls: [string, string, SysPerfCarModelSavePayload][] = [];

    await saveSysPerfBaseCarModel({
      token: 'token',
      workspaceSlug: 'workspace',
      draft: {
        brand: ` ${SYS_PERF_BASE_CAR_BRANDS.hyundai} `,
        era: ' 2 ',
        year: ' 2026 ',
        car_name: '  Tucson  ',
        model_code: ' NX4 ',
        segment_code: ' C ',
        segment_name: ' SUV ',
      },
      deps: deps({
        saveCarModel: async (...args) => {
          calls.push(args);
          return { status: 'ok' };
        },
      }),
    });

    expect(calls[0]).toEqual([
      'token',
      'workspace',
      {
        brand: SYS_PERF_BASE_CAR_BRANDS.hyundai,
        era: '2',
        year: '2026',
        car_name: 'Tucson',
        model_code: 'NX4',
        segment_code: 'C',
        segment_name: 'SUV',
        refrigerant: '',
        note: '',
      },
    ]);
  });

  it('propagates save and delete failures', async () => {
    await expect(
      saveSysPerfBaseCarModel({
        token: 'token',
        workspaceSlug: 'workspace',
        draft: {
          brand: SYS_PERF_BASE_CAR_BRANDS.hyundai,
          era: '2',
          year: '',
          car_name: 'Tucson',
          model_code: '',
          segment_code: '',
          segment_name: '',
        },
        deps: deps({
          saveCarModel: async () => {
            throw new Error('save failed');
          },
        }),
      }),
    ).rejects.toThrow('save failed');

    await expect(
      deleteSysPerfBaseCarModel({
        token: 'token',
        workspaceSlug: 'workspace',
        modelId: 7,
        deps: deps({
          deleteCarModel: async () => {
            throw new Error('delete failed');
          },
        }),
      }),
    ).rejects.toThrow('delete failed');
  });

  it('deletes through the API adapter with the selected model id', async () => {
    const calls: Parameters<SysPerfBaseCarsLoaderDeps['deleteCarModel']>[] = [];

    await deleteSysPerfBaseCarModel({
      token: 'token',
      workspaceSlug: 'workspace',
      modelId: 7,
      deps: deps({
        deleteCarModel: async (...args) => {
          calls.push(args);
          return { status: 'ok' };
        },
      }),
    });

    expect(calls[0]).toEqual(['token', 'workspace', 7]);
  });
});
