import { describe, expect, it } from 'vitest';

import type {
  SysPerfDbSavePayload,
  SysPerfSheetData,
} from '../api/dataviz-api';
import { emptyPartsState, type PartsState } from './sysperf-parts-state';
import {
  loadSysPerfSheetPreview,
  saveSysPerfTableDb,
  type SysPerfTableLoaderDeps,
} from './sysperf-table-loader';
import type { CommonInfo, FileInfo } from './sysperf-testinfo';

function sheetData(patch: Partial<SysPerfSheetData>): SysPerfSheetData {
  return {
    status: 'ok',
    columns: [],
    data: {},
    total_rows: 0,
    ...patch,
  };
}

function deps(patch: Partial<SysPerfTableLoaderDeps>): SysPerfTableLoaderDeps {
  return {
    getSheetData: async () => sheetData({}),
    saveDb: async () => ({
      status: 'ok',
      test_id: 1,
      csv: 'file.csv',
      row_count: 2,
      col_count: 3,
    }),
    ...patch,
  };
}

describe('sysperf table loader', () => {
  it('loads sheet preview data with the preview row limit', async () => {
    const calls: Parameters<SysPerfTableLoaderDeps['getSheetData']>[] = [];

    await expect(
      loadSysPerfSheetPreview({
        token: 'token',
        workspaceSlug: 'workspace',
        fileId: 7,
        sheet: 'Sheet A',
        fallbackError: 'load failed',
        deps: deps({
          getSheetData: async (...args) => {
            calls.push(args);
            return sheetData({
              columns: ['A'],
              data: { A: [1] },
              total_rows: 5,
            });
          },
        }),
      }),
    ).resolves.toEqual({
      preview: { columns: ['A'], data: { A: [1] }, total_rows: 5 },
      error: null,
    });
    expect(calls[0]).toEqual(['token', 'workspace', 7, 'Sheet A', 500]);
  });

  it('returns API and fallback errors without throwing', async () => {
    await expect(
      loadSysPerfSheetPreview({
        token: 'token',
        workspaceSlug: 'workspace',
        fileId: 7,
        sheet: 'Sheet A',
        fallbackError: 'load failed',
        deps: deps({
          getSheetData: async () => sheetData({ error: 'missing mapping' }),
        }),
      }),
    ).resolves.toEqual({ preview: null, error: 'missing mapping' });

    await expect(
      loadSysPerfSheetPreview({
        token: 'token',
        workspaceSlug: 'workspace',
        fileId: 7,
        sheet: 'Sheet A',
        fallbackError: 'load failed',
        deps: deps({
          getSheetData: async () => {
            return Promise.reject('bad');
          },
        }),
      }),
    ).resolves.toEqual({ preview: null, error: 'load failed' });
  });

  it('builds and saves the DB payload through the API adapter', async () => {
    const calls: [string, string, SysPerfDbSavePayload][] = [];
    const common: CommonInfo = {
      car_code: 'CN7',
      car_type: 'EV',
      engine: 'PE',
      stage: 'P1',
      car_number: '42',
    };
    const perFile: Record<number, FileInfo> = {
      7: {
        test_item: 'Cooling',
        test_date: '20260101',
        refrigerant_charge: '500g',
        lot_no: '',
      },
    };
    const parts: Record<number, PartsState> = { 7: emptyPartsState() };
    parts[7].comp.direct = 'Direct Comp';

    await expect(
      saveSysPerfTableDb({
        token: 'token',
        workspaceSlug: 'workspace',
        fileId: 7,
        sheet: 'Sheet A',
        common,
        perFile,
        parts,
        deps: deps({
          saveDb: async (...args) => {
            calls.push(args);
            return {
              status: 'ok',
              test_id: 99,
              csv: 'sys_perf_99.csv',
              row_count: 10,
              col_count: 20,
            };
          },
        }),
      }),
    ).resolves.toEqual({
      status: 'ok',
      test_id: 99,
      csv: 'sys_perf_99.csv',
      row_count: 10,
      col_count: 20,
    });
    expect(calls[0][0]).toBe('token');
    expect(calls[0][1]).toBe('workspace');
    expect(calls[0][2]).toEqual(
      expect.objectContaining({
        file_id: 7,
        sheet_name: 'Sheet A',
        car_code: 'CN7',
        test_item: 'Cooling',
        comp: 'Direct Comp',
      }),
    );
  });
});
