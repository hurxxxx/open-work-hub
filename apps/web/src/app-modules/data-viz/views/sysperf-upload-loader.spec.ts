import { describe, expect, it } from 'vitest';

import type { SysPerfUploadedFile } from '../api/dataviz-api';
import {
  formatSysPerfUploadFailures,
  selectInitialSysPerfUploadSelection,
  splitSysPerfUploadResponseFiles,
  uploadSysPerfFiles,
  type SysPerfUploadLoaderDeps,
} from './sysperf-upload-loader';

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

describe('sysperf upload loader', () => {
  it('splits upload response files into usable files and failures', () => {
    const files: SysPerfUploadedFile[] = [
      { file_id: 1, filename: 'ok.xlsx', sheets: [sheet('A')] },
      { filename: 'bad.xlsx', error: 'invalid format' },
      { file_id: 2, filename: 'empty.xlsx', sheets: [] },
    ];

    const result = splitSysPerfUploadResponseFiles(files);

    expect(result.usableFiles.map((file) => file.filename)).toEqual([
      'ok.xlsx',
    ]);
    expect(result.failures).toEqual([
      { filename: 'bad.xlsx', error: 'invalid format' },
    ]);
  });

  it('formats upload failures with the existing file/error separator', () => {
    expect(
      formatSysPerfUploadFailures([
        { filename: 'a.xlsx', error: 'broken' },
        { filename: 'b.xlsx', error: 'missing sheet' },
      ]),
    ).toBe('a.xlsx: broken / b.xlsx: missing sheet');
  });

  it('selects the first uploaded file only when there is no current selection', () => {
    const { usableFiles } = splitSysPerfUploadResponseFiles([
      { file_id: 7, filename: 'ok.xlsx', sheets: [sheet('Sheet1')] },
    ]);

    expect(
      selectInitialSysPerfUploadSelection({
        usableFiles,
        currentFileId: null,
      }),
    ).toEqual({ fileId: 7, sheetName: 'Sheet1' });
    expect(
      selectInitialSysPerfUploadSelection({
        usableFiles,
        currentFileId: 3,
      }),
    ).toBeNull();
  });

  it('uploads files through the API adapter before splitting the response', async () => {
    const calls: Parameters<SysPerfUploadLoaderDeps['upload']>[] = [];
    const file = { name: 'local.xlsx' } as File;
    const deps: SysPerfUploadLoaderDeps = {
      upload: async (...args) => {
        calls.push(args);
        return {
          status: 'ok',
          files: [{ file_id: 1, filename: 'ok.xlsx', sheets: [sheet('A')] }],
        };
      },
    };

    await expect(
      uploadSysPerfFiles({
        token: 'token',
        workspaceSlug: 'workspace',
        files: [file],
        deps,
      }),
    ).resolves.toEqual({
      usableFiles: [
        expect.objectContaining({
          file_id: 1,
          filename: 'ok.xlsx',
        }),
      ],
      failures: [],
    });
    expect(calls[0]).toEqual(['token', 'workspace', [file]]);
  });
});
