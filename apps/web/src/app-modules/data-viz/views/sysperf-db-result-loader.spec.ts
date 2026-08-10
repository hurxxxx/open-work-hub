import { describe, expect, it } from 'vitest';

import type { SysPerfDbTest } from '../api/dataviz-api';
import {
  buildSysPerfDbCsvFilename,
  deleteSysPerfDbResult,
  downloadSysPerfDbCsv,
  listSysPerfDbResults,
  prepareSysPerfDbCsvDownload,
  type SysPerfDbResultLoaderDeps,
} from './sysperf-db-result-loader';

function dbRow(patch: Partial<SysPerfDbTest>): SysPerfDbTest {
  return {
    id: 1,
    file_id: 1,
    filename: 'file.xlsx',
    sheet_name: 'Sheet1',
    saved_at: '2026-01-01T00:00:00Z',
    csv_path: 'sys_perf.csv',
    row_count: 10,
    col_count: 20,
    car_code: '',
    car_type: '',
    engine: '',
    stage: '',
    car_number: '',
    test_item: '',
    test_date: '',
    refrigerant_charge: '',
    comp: '',
    indoor_condenser: '',
    condenser: '',
    cooling_fan: '',
    radiator: '',
    ihx: '',
    txv: '',
    battery_chiller: '',
    eva: '',
    hvac: '',
    heater_core: '',
    ptc: '',
    ...patch,
  };
}

function deps(
  patch: Partial<SysPerfDbResultLoaderDeps>,
): SysPerfDbResultLoaderDeps {
  return {
    list: async () => ({ data: [] }),
    csv: async () => new Blob(['csv']),
    delete: async () => ({ status: 'ok' }),
    ...patch,
  };
}

describe('sysperf DB result loader', () => {
  it('builds DB CSV filenames with the test fallback', () => {
    expect(buildSysPerfDbCsvFilename('car.xlsx')).toBe('car.xlsx.csv');
    expect(buildSysPerfDbCsvFilename('  ')).toBe('test.csv');
    expect(buildSysPerfDbCsvFilename(null)).toBe('test.csv');
  });

  it('loads DB result rows through the API adapter', async () => {
    const calls: Parameters<SysPerfDbResultLoaderDeps['list']>[] = [];

    await expect(
      listSysPerfDbResults({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: deps({
          list: async (...args) => {
            calls.push(args);
            return { data: [dbRow({ id: 7 })] };
          },
        }),
      }),
    ).resolves.toEqual({ data: [expect.objectContaining({ id: 7 })] });
    expect(calls[0]).toEqual(['token', 'workspace']);
  });

  it('prepares DB CSV downloads with blob and filename together', async () => {
    const csv = new Blob(['csv']);
    const csvCalls: Parameters<SysPerfDbResultLoaderDeps['csv']>[] = [];

    await expect(
      prepareSysPerfDbCsvDownload({
        token: 'token',
        workspaceSlug: 'workspace',
        testId: 9,
        name: '',
        deps: deps({
          csv: async (...args) => {
            csvCalls.push(args);
            return csv;
          },
        }),
      }),
    ).resolves.toEqual({
      blob: csv,
      filename: 'test.csv',
    });
    expect(csvCalls[0]).toEqual(['token', 'workspace', 9]);
  });

  it('downloads CSV blobs and deletes result rows by test id', async () => {
    const csvCalls: Parameters<SysPerfDbResultLoaderDeps['csv']>[] = [];
    const deleteCalls: Parameters<SysPerfDbResultLoaderDeps['delete']>[] = [];
    const adapter = deps({
      csv: async (...args) => {
        csvCalls.push(args);
        return new Blob(['a,b']);
      },
      delete: async (...args) => {
        deleteCalls.push(args);
        return { status: 'ok' };
      },
    });

    await expect(
      downloadSysPerfDbCsv({
        token: 'token',
        workspaceSlug: 'workspace',
        testId: 9,
        deps: adapter,
      }),
    ).resolves.toBeInstanceOf(Blob);
    await expect(
      deleteSysPerfDbResult({
        token: 'token',
        workspaceSlug: 'workspace',
        testId: 9,
        deps: adapter,
      }),
    ).resolves.toEqual({ status: 'ok' });

    expect(csvCalls[0]).toEqual(['token', 'workspace', 9]);
    expect(deleteCalls[0]).toEqual(['token', 'workspace', 9]);
  });
});
