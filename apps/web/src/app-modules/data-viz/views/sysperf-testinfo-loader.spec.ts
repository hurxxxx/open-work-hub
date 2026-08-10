import { describe, expect, it } from 'vitest';

import type { SysPerfTestInfoItem } from '../api/dataviz-api';
import type { UsableSysPerfUploadedFile } from './sysperf-files';
import {
  loadSysPerfTestInfoPartsCatalog,
  saveSysPerfTestInfo,
  type SysPerfTestInfoLoaderDeps,
} from './sysperf-testinfo-loader';
import type { CommonInfo, FileInfo } from './sysperf-testinfo';

function sheet(sheetName: string) {
  return {
    sheet_name: sheetName,
    info_text: '',
    headers: [],
    header_count: 0,
    header_row: 0,
    info_row: 0,
    header_numeric_counts: {},
  };
}

function file(id: number): UsableSysPerfUploadedFile {
  return {
    filename: `file-${id}.xlsx`,
    file_id: id,
    sheets: [sheet('A'), sheet('B')],
  } as UsableSysPerfUploadedFile;
}

function deps(
  patch: Partial<SysPerfTestInfoLoaderDeps>,
): SysPerfTestInfoLoaderDeps {
  return {
    getPartsCatalog: async () => ({ data: [] }),
    saveTestInfo: async () => ({ status: 'ok' }),
    ...patch,
  };
}

describe('sysperf test info loader', () => {
  it('loads and rebuilds the parts catalog tree', async () => {
    const calls: Parameters<SysPerfTestInfoLoaderDeps['getPartsCatalog']>[] =
      [];
    const catalog = await loadSysPerfTestInfoPartsCatalog({
      token: 'token',
      workspaceSlug: 'workspace',
      deps: deps({
        getPartsCatalog: async (...args) => {
          calls.push(args);
          return {
            data: [
              {
                id: 1,
                category: 'comp',
                drive_type: 'belt',
                sub_type: '내부가변',
                name: 'Belt Comp',
                sort_order: 1,
                note: '',
              },
              {
                id: 2,
                category: 'txv',
                drive_type: '',
                sub_type: '',
                name: 'TXV',
                sort_order: 1,
                note: '',
              },
            ],
          };
        },
      }),
    });

    expect(calls[0]).toEqual(['token', 'workspace']);
    expect(catalog.comp.belt['내부가변']).toEqual([
      { id: 1, name: 'Belt Comp' },
    ]);
    expect(catalog.txv).toEqual([{ id: 2, name: 'TXV' }]);
  });

  it('falls back to an empty parts catalog when loading fails', async () => {
    const catalog = await loadSysPerfTestInfoPartsCatalog({
      token: 'token',
      workspaceSlug: 'workspace',
      deps: deps({
        getPartsCatalog: async () => {
          throw new Error('network');
        },
      }),
    });

    expect(catalog.comp.belt['내부가변']).toEqual([]);
    expect(catalog.txv).toEqual([]);
  });

  it('builds and saves the exact test-info payload for every uploaded sheet', async () => {
    const calls: [string, string, SysPerfTestInfoItem[]][] = [];
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
        lot_no: 'LOT42',
      },
    };

    await saveSysPerfTestInfo({
      token: 'token',
      workspaceSlug: 'workspace',
      files: [file(7)],
      common,
      perFile,
      deps: deps({
        saveTestInfo: async (...args) => {
          calls.push(args);
          return { status: 'ok' };
        },
      }),
    });

    expect(calls[0][0]).toBe('token');
    expect(calls[0][1]).toBe('workspace');
    expect(calls[0][2]).toEqual([
      {
        file_id: 7,
        sheet_name: 'A',
        car_model: 'CN7',
        spec: '',
        test_item: 'Cooling',
        test_date: '20260101',
        lot_no: 'LOT42',
        refrigerant: '500g',
        note: '',
      },
      {
        file_id: 7,
        sheet_name: 'B',
        car_model: 'CN7',
        spec: '',
        test_item: 'Cooling',
        test_date: '20260101',
        lot_no: 'LOT42',
        refrigerant: '500g',
        note: '',
      },
    ]);
  });

  it('propagates save failures and keeps empty file-info fallback payload fields', async () => {
    const calls: [string, string, SysPerfTestInfoItem[]][] = [];
    const common: CommonInfo = {
      car_code: 'CN7',
      car_type: '',
      engine: '',
      stage: '',
      car_number: '',
    };
    const failingDeps = deps({
      saveTestInfo: async (...args) => {
        calls.push(args);
        throw new Error('save failed');
      },
    });

    await expect(
      saveSysPerfTestInfo({
        token: 'token',
        workspaceSlug: 'workspace',
        files: [file(8)],
        common,
        perFile: {},
        deps: failingDeps,
      }),
    ).rejects.toThrow('save failed');

    expect(calls[0][2][0]).toEqual({
      file_id: 8,
      sheet_name: 'A',
      car_model: 'CN7',
      spec: '',
      test_item: '',
      test_date: '',
      lot_no: '',
      refrigerant: '',
      note: '',
    });
  });
});
