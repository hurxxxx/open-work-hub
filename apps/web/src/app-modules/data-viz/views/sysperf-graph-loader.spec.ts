import { describe, expect, it } from 'vitest';

import type { SysPerfGraphData } from '../api/dataviz-api';
import type { UsableSysPerfUploadedFile } from './sysperf-files';
import {
  loadSysPerfGraphFile,
  loadMissingSysPerfGraphFiles,
  mergeSysPerfGraphLoadResults,
  selectMissingSysPerfGraphFiles,
  type SysPerfGraphLoaderDeps,
} from './sysperf-graph-loader';

function file(id: number, sheetName: string): UsableSysPerfUploadedFile {
  return {
    filename: `file-${id}.xlsx`,
    file_id: id,
    sheets: [{ sheet_name: sheetName, headers: [], header_numeric_counts: {} }],
  } as UsableSysPerfUploadedFile;
}

function graphData(data: SysPerfGraphData['data']): SysPerfGraphData {
  return {
    status: 'ok',
    data,
    units: {},
    total_rows: 1,
  };
}

describe('sysperf graph loader', () => {
  it('selects only missing files and honors checked state', () => {
    expect(
      selectMissingSysPerfGraphFiles({
        files: [file(1, 'A'), file(2, 'B'), file(3, 'C')],
        cache: { 2: { data: {}, units: {} } },
        checked: { 1: true, 2: true, 3: false },
      }).map((candidate) => candidate.file_id),
    ).toEqual([1]);
  });

  it('can treat cached error entries as missing for retry paths', () => {
    const files = [file(1, 'A'), file(2, 'B')];
    const cache = {
      1: { data: {}, units: {}, error: 'network down' },
      2: { data: { Time: [0] }, units: {} },
    };

    expect(
      selectMissingSysPerfGraphFiles({
        files,
        cache,
      }).map((candidate) => candidate.file_id),
    ).toEqual([]);

    expect(
      selectMissingSysPerfGraphFiles({
        files,
        cache,
        retryErrors: true,
      }).map((candidate) => candidate.file_id),
    ).toEqual([1]);
  });

  it('loads missing graph files into cache entries', async () => {
    const calls: Parameters<SysPerfGraphLoaderDeps['getGraphData']>[] = [];
    const deps: SysPerfGraphLoaderDeps = {
      getGraphData: async (...args) => {
        calls.push(args);
        return graphData({ Time: [0], Value: [1] });
      },
    };

    const results = await loadMissingSysPerfGraphFiles({
      token: 'token',
      workspaceSlug: 'workspace',
      files: [file(1, 'Sheet A')],
      cache: {},
      fallbackError: 'load failed',
      deps,
    });

    expect(calls[0]).toEqual(['token', 'workspace', 1, 'Sheet A', 3000]);
    expect(results).toEqual([
      {
        fileId: 1,
        cache: { data: { Time: [0], Value: [1] }, units: {} },
      },
    ]);
  });

  it('loads one graph file with the requested max point limit', async () => {
    const calls: Parameters<SysPerfGraphLoaderDeps['getGraphData']>[] = [];
    const deps: SysPerfGraphLoaderDeps = {
      getGraphData: async (...args) => {
        calls.push(args);
        return graphData({ Time: [0, 1] });
      },
    };

    await expect(
      loadSysPerfGraphFile({
        token: 'token',
        workspaceSlug: 'workspace',
        file: file(2, 'Data'),
        maxPoints: 120,
        fallbackError: 'load failed',
        deps,
      }),
    ).resolves.toEqual({
      fileId: 2,
      cache: { data: { Time: [0, 1] }, units: {} },
    });
    expect(calls[0]).toEqual(['token', 'workspace', 2, 'Data', 120]);
  });

  it('can either cache errors or skip failed compare loads', async () => {
    const deps: SysPerfGraphLoaderDeps = {
      getGraphData: async () => {
        throw new Error('network down');
      },
    };

    await expect(
      loadMissingSysPerfGraphFiles({
        token: 'token',
        workspaceSlug: 'workspace',
        files: [file(1, 'Sheet A')],
        cache: {},
        fallbackError: 'load failed',
        deps,
      }),
    ).resolves.toEqual([
      {
        fileId: 1,
        cache: { data: {}, units: {}, error: 'network down' },
      },
    ]);

    await expect(
      loadMissingSysPerfGraphFiles({
        token: 'token',
        workspaceSlug: 'workspace',
        files: [file(1, 'Sheet A')],
        cache: {},
        fallbackError: 'load failed',
        cacheErrors: false,
        deps,
      }),
    ).resolves.toEqual([]);
  });

  it('retries cached error entries when failed loads should not be cached', async () => {
    const calls: Parameters<SysPerfGraphLoaderDeps['getGraphData']>[] = [];
    const deps: SysPerfGraphLoaderDeps = {
      getGraphData: async (...args) => {
        calls.push(args);
        return graphData({ Time: [0], Value: [1] });
      },
    };

    await expect(
      loadMissingSysPerfGraphFiles({
        token: 'token',
        workspaceSlug: 'workspace',
        files: [file(1, 'Sheet A')],
        cache: {
          1: { data: {}, units: {}, error: 'previous failure' },
        },
        fallbackError: 'load failed',
        cacheErrors: false,
        deps,
      }),
    ).resolves.toEqual([
      {
        fileId: 1,
        cache: { data: { Time: [0], Value: [1] }, units: {} },
      },
    ]);
    expect(calls[0]).toEqual(['token', 'workspace', 1, 'Sheet A', 3000]);
  });

  it('merges graph load results without mutating existing cache entries', () => {
    const previous = { 1: { data: { Time: [0] }, units: {} } };
    const merged = mergeSysPerfGraphLoadResults(previous, [
      { fileId: 2, cache: { data: { Time: [1] }, units: {} } },
    ]);

    expect(merged).toEqual({
      1: { data: { Time: [0] }, units: {} },
      2: { data: { Time: [1] }, units: {} },
    });
    expect(merged).not.toBe(previous);
  });
});
