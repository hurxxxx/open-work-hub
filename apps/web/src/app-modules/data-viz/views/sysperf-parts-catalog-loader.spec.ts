import { describe, expect, it } from 'vitest';

import type {
  SysPerfPartsCatalogItem,
  SysPerfPartsCatalogSavePayload,
} from '../api/dataviz-api';
import {
  buildSysPerfPartsCatalogSavePayload,
  deleteSysPerfPartsCatalogItem,
  isSysPerfPartsCatalogNameSubmittable,
  loadSysPerfPartsCatalogRows,
  saveSysPerfPartsCatalogItem,
  type SysPerfPartsCatalogLoaderDeps,
} from './sysperf-parts-catalog-loader';

function item(
  patch: Partial<SysPerfPartsCatalogItem>,
): SysPerfPartsCatalogItem {
  return {
    id: 1,
    category: 'txv',
    drive_type: '',
    sub_type: '',
    name: 'TXV',
    sort_order: 0,
    note: '',
    ...patch,
  };
}

function deps(
  patch: Partial<SysPerfPartsCatalogLoaderDeps>,
): SysPerfPartsCatalogLoaderDeps {
  return {
    getPartsCatalog: async () => ({ data: [] }),
    savePartsCatalog: async () => ({ status: 'ok', id: 1 }),
    deletePartsCatalog: async () => ({ status: 'ok' }),
    ...patch,
  };
}

describe('sysperf parts catalog loader', () => {
  it('loads catalog rows and forwards workspace context', async () => {
    const calls: Parameters<
      SysPerfPartsCatalogLoaderDeps['getPartsCatalog']
    >[] = [];

    await expect(
      loadSysPerfPartsCatalogRows({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: deps({
          getPartsCatalog: async (...args) => {
            calls.push(args);
            return {
              data: [item({ id: 7, category: 'comp', name: 'Belt Comp' })],
            };
          },
        }),
      }),
    ).resolves.toEqual([item({ id: 7, category: 'comp', name: 'Belt Comp' })]);
    expect(calls[0]).toEqual(['token', 'workspace']);
  });

  it('propagates load failures', async () => {
    await expect(
      loadSysPerfPartsCatalogRows({
        token: 'token',
        workspaceSlug: 'workspace',
        deps: deps({
          getPartsCatalog: async () => {
            throw new Error('network');
          },
        }),
      }),
    ).rejects.toThrow('network');
  });

  it('builds exact comp and non-comp save payloads', () => {
    expect(
      buildSysPerfPartsCatalogSavePayload({
        category: 'comp',
        drive_type: 'belt',
        sub_type: '내부가변',
        name: '  Belt Comp  ',
      }),
    ).toEqual({
      category: 'comp',
      drive_type: 'belt',
      sub_type: '내부가변',
      name: 'Belt Comp',
    });

    expect(
      buildSysPerfPartsCatalogSavePayload({
        category: 'txv',
        drive_type: '',
        sub_type: '',
        name: '  TXV  ',
      }),
    ).toEqual({
      category: 'txv',
      drive_type: '',
      sub_type: '',
      name: 'TXV',
    });
  });

  it('identifies blank names as not submittable', () => {
    expect(isSysPerfPartsCatalogNameSubmittable('   ')).toBe(false);
    expect(isSysPerfPartsCatalogNameSubmittable('  TXV  ')).toBe(true);
  });

  it('saves through the API adapter and returns non-ok statuses unchanged', async () => {
    const calls: [string, string, SysPerfPartsCatalogSavePayload][] = [];

    await expect(
      saveSysPerfPartsCatalogItem({
        token: 'token',
        workspaceSlug: 'workspace',
        draft: {
          category: 'txv',
          drive_type: '',
          sub_type: '',
          name: '  TXV  ',
        },
        deps: deps({
          savePartsCatalog: async (...args) => {
            calls.push(args);
            return { status: 'duplicate', id: 0 };
          },
        }),
      }),
    ).resolves.toEqual({ status: 'duplicate', id: 0 });

    expect(calls[0]).toEqual([
      'token',
      'workspace',
      {
        category: 'txv',
        drive_type: '',
        sub_type: '',
        name: 'TXV',
      },
    ]);
  });

  it('propagates save and delete failures', async () => {
    await expect(
      saveSysPerfPartsCatalogItem({
        token: 'token',
        workspaceSlug: 'workspace',
        draft: {
          category: 'txv',
          drive_type: '',
          sub_type: '',
          name: 'TXV',
        },
        deps: deps({
          savePartsCatalog: async () => {
            throw new Error('save failed');
          },
        }),
      }),
    ).rejects.toThrow('save failed');

    await expect(
      deleteSysPerfPartsCatalogItem({
        token: 'token',
        workspaceSlug: 'workspace',
        id: 7,
        deps: deps({
          deletePartsCatalog: async () => {
            throw new Error('delete failed');
          },
        }),
      }),
    ).rejects.toThrow('delete failed');
  });

  it('deletes through the API adapter with the selected catalog id', async () => {
    const calls: Parameters<
      SysPerfPartsCatalogLoaderDeps['deletePartsCatalog']
    >[] = [];

    await deleteSysPerfPartsCatalogItem({
      token: 'token',
      workspaceSlug: 'workspace',
      id: 7,
      deps: deps({
        deletePartsCatalog: async (...args) => {
          calls.push(args);
          return { status: 'ok' };
        },
      }),
    });

    expect(calls[0]).toEqual(['token', 'workspace', 7]);
  });
});
