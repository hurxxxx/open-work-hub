import { describe, expect, it } from 'vitest';

import type { SysPerfSheetData } from '../api/dataviz-api';
import type { UsableSysPerfUploadedFile } from './sysperf-files';
import type { MeasureItem } from './sysperf-items';
import {
  applyLoadedSysPerfMatchSheetDataProbesToState,
  applyLoadedSysPerfMatchSheetDataProbe,
  applyLoadedSysPerfMatchSheetDataProbes,
  applySysPerfItemKeywordOverrides,
  areSysPerfFidMapsEqual,
  confirmSysPerfMatchRequests,
  loadSysPerfItemKeywordOverrides,
  loadSysPerfMatchSheetDataProbePayload,
  parseSysPerfItemKeywordOverrides,
  type SysPerfMatchLoaderDeps,
} from './sysperf-match-loader';

const items: MeasureItem[] = [
  { n: 10, nm: 'Pressure', u: '', kw: ['P'] },
  { n: 20, nm: 'Temperature', u: '', kw: ['T'] },
];

function file(id: number, sheetName: string): UsableSysPerfUploadedFile {
  return {
    filename: `file-${id}.xlsx`,
    file_id: id,
    sheets: [{ sheet_name: sheetName, headers: [], header_numeric_counts: {} }],
  } as UsableSysPerfUploadedFile;
}

function sheetData(patch: Partial<SysPerfSheetData>): SysPerfSheetData {
  return {
    status: 'ok',
    columns: [],
    data: {},
    total_rows: 0,
    ...patch,
  };
}

function deps(patch: Partial<SysPerfMatchLoaderDeps>): SysPerfMatchLoaderDeps {
  return {
    getSheetData: async () => sheetData({}),
    getItemKeywords: async () => ({ data: [] }),
    confirmMatch: async () => ({ status: 'ok' }),
    ...patch,
  };
}

describe('sysperf match loader', () => {
  it('parses and applies item keyword overrides without mutating other items', () => {
    const overrides = parseSysPerfItemKeywordOverrides([
      { item_n: 10, keywords: ' PS, Pressure , ' },
      { item_n: 20, keywords: '' },
    ]);

    expect(overrides).toEqual({ 10: ['PS', 'Pressure'], 20: [] });
    expect(applySysPerfItemKeywordOverrides(items, overrides)).toEqual([
      { n: 10, nm: 'Pressure', u: '', kw: ['PS', 'Pressure'] },
      { n: 20, nm: 'Temperature', u: '', kw: [] },
    ]);
    expect(items[0].kw).toEqual(['P']);
  });

  it('loads item keyword overrides and treats fetch failures as no overrides', async () => {
    await expect(
      loadSysPerfItemKeywordOverrides({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: deps({
          getItemKeywords: async () => ({
            data: [{ item_n: 10, keywords: 'A,B' }],
          }),
        }),
      }),
    ).resolves.toEqual({ 10: ['A', 'B'] });

    await expect(
      loadSysPerfItemKeywordOverrides({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: deps({
          getItemKeywords: async () => {
            throw new Error('network');
          },
        }),
      }),
    ).resolves.toEqual({});
  });

  it('loads sheet-data probe payloads and applies them to the latest value state', async () => {
    const calls: Parameters<SysPerfMatchLoaderDeps['getSheetData']>[] = [];
    const payload = await loadSysPerfMatchSheetDataProbePayload({
      token: 'token',
      workspaceSlug: 'workspace',
      file: file(1, 'Sheet A'),
      deps: deps({
        getSheetData: async (...args) => {
          calls.push(args);
          return sheetData({
            data: {
              Pressure: [null, 1],
              Temperature: [null, Number.NaN],
            },
          });
        },
      }),
    });

    expect(calls[0]).toEqual(['token', 'workspace', 1, 'Sheet A', 30]);
    expect(payload).toEqual({
      fileId: 1,
      data: {
        Pressure: [null, 1],
        Temperature: [null, Number.NaN],
      },
      status: 'ok',
    });
    expect(
      applyLoadedSysPerfMatchSheetDataProbe({
        items,
        match: { 1: { 10: 'Pressure', 20: 'Temperature' } },
        valueState: { 1: { 10: 'loading', 20: 'loading' } },
        payload,
      }),
    ).toEqual({
      valueState: { 1: { 10: 'ok', 20: 'nodata' } },
      uncheckedItemNumbers: [20],
    });
  });

  it('applies cached sheet-data probe payloads to the latest match state', () => {
    expect(
      applyLoadedSysPerfMatchSheetDataProbes({
        items,
        match: {
          1: { 10: 'Pressure', 20: '' },
          2: { 10: 'Pressure', 20: 'Temperature' },
        },
        valueState: {
          1: { 10: 'loading', 20: 'loading' },
          2: { 10: 'loading', 20: 'loading' },
        },
        payloads: [
          {
            fileId: 1,
            status: 'ok',
            data: {
              Pressure: [1],
              Temperature: [2],
            },
          },
          {
            fileId: 2,
            status: 'ok',
            data: {
              Pressure: [1],
              Temperature: [Number.NaN],
            },
          },
        ],
      }),
    ).toEqual({
      valueState: {
        1: { 10: 'ok', 20: '' },
        2: { 10: 'ok', 20: 'nodata' },
      },
      uncheckedByFileId: {
        2: [20],
      },
    });
  });

  it('compares fid maps by semantic file/item values', () => {
    expect(
      areSysPerfFidMapsEqual(
        { 1: { 10: 'ok', 20: 'nodata' }, 2: { 10: '' } },
        { 2: { 10: '' }, 1: { 20: 'nodata', 10: 'ok' } },
      ),
    ).toBe(true);
    expect(
      areSysPerfFidMapsEqual(
        { 1: { 10: true, 20: false } },
        { 1: { 10: true, 20: true } },
      ),
    ).toBe(false);
    expect(
      areSysPerfFidMapsEqual({ 1: { 10: true } }, { 1: { 10: true }, 2: {} }),
    ).toBe(false);
  });

  it('applies cached sheet-data probes to value state and checked state together', () => {
    expect(
      applyLoadedSysPerfMatchSheetDataProbesToState({
        items,
        match: {
          1: { 10: 'Pressure', 20: 'Temperature' },
        },
        valueState: {
          1: { 10: 'loading', 20: 'loading' },
        },
        checked: {
          1: { 10: true, 20: true },
        },
        payloads: [
          {
            fileId: 1,
            status: 'ok',
            data: {
              Pressure: [1],
              Temperature: [Number.NaN],
            },
          },
        ],
      }),
    ).toEqual({
      valueState: {
        1: { 10: 'ok', 20: 'nodata' },
      },
      checked: {
        1: { 10: true, 20: false },
      },
      uncheckedByFileId: {
        1: [20],
      },
    });
  });

  it('falls back to a blank sheet name for malformed uploaded file metadata', async () => {
    const calls: Parameters<SysPerfMatchLoaderDeps['getSheetData']>[] = [];

    await loadSysPerfMatchSheetDataProbePayload({
      token: 'token',
      workspaceSlug: 'workspace',
      file: {
        filename: 'file-1.xlsx',
        file_id: 1,
        sheets: [{}],
      } as unknown as UsableSysPerfUploadedFile,
      deps: deps({
        getSheetData: async (...args) => {
          calls.push(args);
          return sheetData({});
        },
      }),
    });

    expect(calls[0]).toEqual(['token', 'workspace', 1, '', 30]);
  });

  it('turns missing and rejected sheet-data probes into model statuses', async () => {
    await expect(
      loadSysPerfMatchSheetDataProbePayload({
        token: 'token',
        workspaceSlug: 'workspace',
        file: file(1, 'Sheet A'),
        deps: deps({
          getSheetData: async () =>
            sheetData({ data: {}, error: 'missing mapping' }),
        }),
      }),
    ).resolves.toEqual({ fileId: 1, data: {}, status: 'missing' });

    await expect(
      loadSysPerfMatchSheetDataProbePayload({
        token: 'token',
        workspaceSlug: 'workspace',
        file: file(1, 'Sheet A'),
        deps: deps({
          getSheetData: async () => {
            throw new Error('network');
          },
        }),
      }),
    ).resolves.toEqual({ fileId: 1, status: 'error' });
  });

  it('confirms match requests sequentially and reports committed mapping counts', async () => {
    const calls: Parameters<SysPerfMatchLoaderDeps['confirmMatch']>[] = [];
    const results = await confirmSysPerfMatchRequests({
      token: 'token',
      workspaceSlug: 'workspace',
      requests: [
        {
          fileId: 1,
          sheetName: 'A',
          fileIndex: 0,
          mappings: [
            { col_index: 0, original_name: 'P', standard_name: '10_Pressure' },
          ],
        },
        {
          fileId: 2,
          sheetName: 'B',
          fileIndex: 1,
          mappings: [
            {
              col_index: 1,
              original_name: 'T',
              standard_name: '20_Temperature',
            },
            {
              col_index: 2,
              original_name: 'T2',
              standard_name: '21_Temperature',
            },
          ],
        },
      ],
      deps: deps({
        confirmMatch: async (...args) => {
          calls.push(args);
          return { status: 'ok' };
        },
      }),
    });

    expect(calls.map((call) => call.slice(0, 4))).toEqual([
      ['token', 'workspace', 1, 'A'],
      ['token', 'workspace', 2, 'B'],
    ]);
    expect(results).toEqual([
      { fileIndex: 0, count: 1 },
      { fileIndex: 1, count: 2 },
    ]);
  });
});
