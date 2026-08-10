import { describe, expect, it } from 'vitest';

import type { SysPerfStandardColumn } from '../api/dataviz-api';
import {
  buildSysPerfBaseColumnSavePayload,
  deleteSysPerfBaseColumn,
  isSysPerfBaseColumnDraftSubmittable,
  loadSysPerfBaseColumns,
  saveSysPerfBaseColumn,
  type SysPerfBaseColumnsLoaderDeps,
} from './sysperf-base-columns-loader';

function column(patch: Partial<SysPerfStandardColumn>): SysPerfStandardColumn {
  return {
    id: 1,
    standard_name: 'Item',
    keywords: '',
    unit: '',
    category: 'general',
    display_order: 0,
    ...patch,
  };
}

function deps(
  patch: Partial<SysPerfBaseColumnsLoaderDeps>,
): SysPerfBaseColumnsLoaderDeps {
  return {
    getColumns: async () => ({ data: [] }),
    saveColumn: async () => ({ status: 'ok' }),
    deleteColumn: async () => ({ status: 'ok' }),
    ...patch,
  };
}

describe('sysperf base columns loader', () => {
  it('loads base columns and forwards workspace context', async () => {
    const calls: Parameters<SysPerfBaseColumnsLoaderDeps['getColumns']>[] = [];

    await expect(
      loadSysPerfBaseColumns({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: deps({
          getColumns: async (...args) => {
            calls.push(args);
            return { data: [column({ id: 7, standard_name: 'RPM' })] };
          },
        }),
      }),
    ).resolves.toEqual([column({ id: 7, standard_name: 'RPM' })]);
    expect(calls[0]).toEqual(['token', 'workspace']);
  });

  it('propagates load failures', async () => {
    await expect(
      loadSysPerfBaseColumns({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: deps({
          getColumns: async () => {
            throw new Error('network');
          },
        }),
      }),
    ).rejects.toThrow('network');
  });

  it('builds the exact save payload and trims only the standard name', () => {
    expect(
      buildSysPerfBaseColumnSavePayload({
        standard_name: '  RPM  ',
        keywords: '  speed, rpm  ',
        unit: '  r/min  ',
        category: '  general  ',
      }),
    ).toEqual({
      standard_name: 'RPM',
      keywords: '  speed, rpm  ',
      unit: '  r/min  ',
      category: '  general  ',
    });
  });

  it('identifies blank standard names as not submittable', () => {
    expect(
      isSysPerfBaseColumnDraftSubmittable({
        standard_name: '   ',
        keywords: 'rpm',
        unit: 'rpm',
        category: 'general',
      }),
    ).toBe(false);
    expect(
      isSysPerfBaseColumnDraftSubmittable({
        standard_name: 'RPM',
        keywords: '',
        unit: '',
        category: 'general',
      }),
    ).toBe(true);
  });

  it('saves through the API adapter with the exact four-field payload', async () => {
    const calls: Parameters<SysPerfBaseColumnsLoaderDeps['saveColumn']>[] = [];

    await saveSysPerfBaseColumn({
      token: 'token',
      workspaceSlug: 'workspace',
      draft: {
        standard_name: '  RPM  ',
        keywords: 'speed',
        unit: 'rpm',
        category: 'general',
      },
      deps: deps({
        saveColumn: async (...args) => {
          calls.push(args);
          return { status: 'ok' };
        },
      }),
    });

    expect(calls[0]).toEqual([
      'token',
      'workspace',
      {
        standard_name: 'RPM',
        keywords: 'speed',
        unit: 'rpm',
        category: 'general',
      },
    ]);
  });

  it('propagates save and delete failures', async () => {
    await expect(
      saveSysPerfBaseColumn({
        token: 'token',
        workspaceSlug: 'workspace',
        draft: {
          standard_name: 'RPM',
          keywords: '',
          unit: '',
          category: 'general',
        },
        deps: deps({
          saveColumn: async () => {
            throw new Error('save failed');
          },
        }),
      }),
    ).rejects.toThrow('save failed');

    await expect(
      deleteSysPerfBaseColumn({
        token: 'token',
        workspaceSlug: 'workspace',
        columnId: 7,
        deps: deps({
          deleteColumn: async () => {
            throw new Error('delete failed');
          },
        }),
      }),
    ).rejects.toThrow('delete failed');
  });

  it('deletes through the API adapter with the selected column id', async () => {
    const calls: Parameters<SysPerfBaseColumnsLoaderDeps['deleteColumn']>[] =
      [];

    await deleteSysPerfBaseColumn({
      token: 'token',
      workspaceSlug: 'workspace',
      columnId: 7,
      deps: deps({
        deleteColumn: async (...args) => {
          calls.push(args);
          return { status: 'ok' };
        },
      }),
    });

    expect(calls[0]).toEqual(['token', 'workspace', 7]);
  });
});
