import { describe, expect, it, vi } from 'vitest';

import {
  FILES_CHANGED_EVENT,
  FILES_UPLOAD_COMPLETED_EVENT,
  applyFileUploadProgress,
  buildFileUploadProgressSnapshot,
  canStartFileUpload,
  completeFileUploadRecord,
  createFileUploadId,
  createFileUploadRecord,
  dismissFileUploadRecord,
  failFileUploadRecord,
  getFileUploadSuccessEvents,
  runFileUploadBatch,
  type FileUploadFileAdapter,
} from './file-upload-session';

function file(name: string, size: number): File {
  return new File(['x'.repeat(size)], name);
}

describe('file upload session', () => {
  it('guards starts and creates the initial upload record', () => {
    const files = [file('one.pdf', 4), file('two.pdf', 6)];

    expect(canStartFileUpload({ files, hasActiveUpload: false })).toBe(true);
    expect(canStartFileUpload({ files, hasActiveUpload: true })).toBe(false);
    expect(canStartFileUpload({ files: [], hasActiveUpload: false })).toBe(
      false,
    );
    expect(createFileUploadId({ now: 1000, sequence: 3 })).toBe(
      'file-upload-1000-3',
    );
    expect(
      createFileUploadRecord({ files, id: 'upload-1', now: 1000 }),
    ).toEqual({
      id: 'upload-1',
      currentFileIndex: 1,
      currentFileName: 'one.pdf',
      loadedBytes: 0,
      percent: 0,
      status: 'uploading',
      totalBytes: 10,
      totalFiles: 2,
      updatedAt: 1000,
    });
  });

  it('updates, completes, fails, and dismisses records through pure transitions', () => {
    const record = createFileUploadRecord({
      files: [file('one.pdf', 10)],
      id: 'upload-1',
      now: 1000,
    });
    const progressed = applyFileUploadProgress({
      now: 1001,
      progress: {
        fileIndex: 1,
        fileName: 'one.pdf',
        loadedBytes: 5,
        percent: 50,
      },
      upload: record,
    });
    const failed = failFileUploadRecord({
      errorMessage: 'Upload failed',
      now: 1002,
      upload: progressed,
    });
    const completed = completeFileUploadRecord({
      now: 1003,
      upload: progressed,
    });

    expect(progressed).toMatchObject({ loadedBytes: 5, percent: 50 });
    expect(failed).toMatchObject({
      errorMessage: 'Upload failed',
      status: 'failed',
    });
    expect(completed).toMatchObject({
      loadedBytes: 10,
      percent: 100,
      status: 'succeeded',
    });
    expect(dismissFileUploadRecord([record, failed], 'upload-1')).toEqual([
      record,
    ]);
    expect(dismissFileUploadRecord([record], 'upload-1')).toEqual([record]);
  });

  it('computes batch progress across files', () => {
    expect(
      buildFileUploadProgressSnapshot({
        completedBytes: 10,
        file: file('two.pdf', 30),
        fileIndex: 2,
        progress: { loaded: 15, percent: 50, total: 30 },
        totalBytes: 40,
      }),
    ).toEqual({
      fileIndex: 2,
      fileName: 'two.pdf',
      loadedBytes: 25,
      percent: 63,
    });
  });

  it('runs upload batches sequentially and reports progress', async () => {
    const progress: unknown[] = [];
    const uploadFile = vi.fn<FileUploadFileAdapter>(
      async ({ file: currentFile, onProgress }) => {
        onProgress({
          loaded: currentFile.size / 2,
          percent: 50,
          total: currentFile.size,
        });
      },
    );

    await expect(
      runFileUploadBatch({
        fallbackErrorMessage: 'Fallback',
        files: [file('one.pdf', 10), file('two.pdf', 30)],
        folderId: 'folder-1',
        onProgress: (snapshot) => progress.push(snapshot),
        signal: new AbortController().signal,
        token: 'token',
        uploadFile,
        uploadVisibility: 'workspace',
        workspaceSlug: 'acme',
      }),
    ).resolves.toEqual({ ok: true });

    expect(uploadFile).toHaveBeenCalledTimes(2);
    expect(progress).toEqual([
      { fileIndex: 1, fileName: 'one.pdf', loadedBytes: 5, percent: 13 },
      { fileIndex: 1, fileName: 'one.pdf', loadedBytes: 10, percent: 25 },
      { fileIndex: 2, fileName: 'two.pdf', loadedBytes: 25, percent: 63 },
      { fileIndex: 2, fileName: 'two.pdf', loadedBytes: 40, percent: 100 },
    ]);
  });

  it('returns adapter errors and exposes success event descriptors', async () => {
    await expect(
      runFileUploadBatch({
        fallbackErrorMessage: 'Fallback',
        files: [file('one.pdf', 10)],
        folderId: null,
        onProgress: () => undefined,
        signal: new AbortController().signal,
        token: 'token',
        uploadFile: async () => {
          throw new Error('Network failed');
        },
        uploadVisibility: 'private',
        workspaceSlug: 'acme',
      }),
    ).resolves.toEqual({ errorMessage: 'Network failed', ok: false });

    expect(
      getFileUploadSuccessEvents({
        folderId: 'folder-1',
        workspaceSlug: 'acme',
      }),
    ).toEqual([
      {
        detail: { folderId: 'folder-1', workspaceSlug: 'acme' },
        name: FILES_UPLOAD_COMPLETED_EVENT,
      },
      {
        detail: { folderId: 'folder-1', workspaceSlug: 'acme' },
        name: FILES_CHANGED_EVENT,
      },
    ]);
  });
});
