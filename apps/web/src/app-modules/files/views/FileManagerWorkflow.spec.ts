import { describe, expect, it } from 'vitest';

import {
  createEmptyFileManagerSelection,
  filterSelectionToVisibleItems,
  planBulkDeleteCommand,
  planCreateFolderCommand,
  planDeleteFolderCommand,
  planFileManagerBulkDownload,
  selectAllVisibleFileManagerItems,
  summarizeFileManagerSelection,
  toggleFileSelection,
  toggleFolderSelection,
} from './FileManagerWorkflow';

describe('FileManagerWorkflow', () => {
  it('toggles file and folder selections as immutable state transitions', () => {
    const initial = createEmptyFileManagerSelection();
    const withFile = toggleFileSelection(initial, 'file-1', true);
    const withFolder = toggleFolderSelection(withFile, 'folder-1', true);
    const withoutFile = toggleFileSelection(withFolder, 'file-1', false);

    expect(initial.fileIds.size).toBe(0);
    expect(withFile.fileIds.has('file-1')).toBe(true);
    expect(withFolder.folderIds.has('folder-1')).toBe(true);
    expect(withoutFile.fileIds.has('file-1')).toBe(false);
    expect(withoutFile.folderIds.has('folder-1')).toBe(true);
  });

  it('selects or clears all currently visible items', () => {
    const selected = selectAllVisibleFileManagerItems(
      {
        files: [
          { id: 'file-1' },
          { id: 'file-2' },
        ],
        folders: [{ id: 'folder-1' }],
      },
      true,
    );

    expect([...selected.fileIds]).toEqual(['file-1', 'file-2']);
    expect([...selected.folderIds]).toEqual(['folder-1']);

    expect(
      selectAllVisibleFileManagerItems(
        {
          files: [{ id: 'file-1' }],
          folders: [{ id: 'folder-1' }],
        },
        false,
      ),
    ).toEqual(createEmptyFileManagerSelection());
  });

  it('filters stale selections while preserving object identity when unchanged', () => {
    const selection = {
      fileIds: new Set(['file-1', 'file-gone']),
      folderIds: new Set(['folder-1']),
    };

    const filtered = filterSelectionToVisibleItems(selection, {
      files: [{ id: 'file-1' }],
      folders: [{ id: 'folder-1' }],
    });
    expect([...filtered.fileIds]).toEqual(['file-1']);
    expect([...filtered.folderIds]).toEqual(['folder-1']);
    expect(filtered).not.toBe(selection);

    const unchanged = filterSelectionToVisibleItems(filtered, {
      files: [{ id: 'file-1' }],
      folders: [{ id: 'folder-1' }],
    });
    expect(unchanged).toBe(filtered);
  });

  it('summarizes visible selection count, file size, and all-visible state', () => {
    const summary = summarizeFileManagerSelection(
      {
        fileIds: new Set(['file-1', 'file-hidden']),
        folderIds: new Set(['folder-1']),
      },
      {
        files: [
          { id: 'file-1', size_bytes: 512 },
          { id: 'file-2', size_bytes: 1024 },
        ],
        folders: [{ id: 'folder-1' }],
      },
    );

    expect(summary.selectedCount).toBe(3);
    expect(summary.selectedFiles.map((file) => file.id)).toEqual(['file-1']);
    expect(summary.selectedVisibleSize).toBe(512);
    expect(summary.allVisibleSelected).toBe(false);

    expect(
      summarizeFileManagerSelection(
        {
          fileIds: new Set(['file-1', 'file-2']),
          folderIds: new Set(['folder-1']),
        },
        {
          files: [
            { id: 'file-1', size_bytes: 512 },
            { id: 'file-2', size_bytes: 1024 },
          ],
          folders: [{ id: 'folder-1' }],
        },
      ).allVisibleSelected,
    ).toBe(true);
  });

  it('plans child folder creation with current folder visibility', () => {
    expect(
      planCreateFolderCommand({
        name: 'Specs',
        currentFolderId: 'parent-folder',
        currentFolderVisibility: 'workspace',
        selectedVisibility: 'private',
      }),
    ).toEqual({
      payload: {
        name: 'Specs',
        parent_id: 'parent-folder',
        visibility: 'workspace',
      },
      afterSuccess: {
        closeDialog: true,
        emitChangedEvent: true,
        reload: true,
      },
    });
  });

  it('plans current folder deletion with root navigation and browse clearing', () => {
    expect(
      planDeleteFolderCommand({
        folderId: 'folder-1',
        currentFolderId: 'folder-1',
      }),
    ).toEqual({
      busyId: 'folder-1',
      folderId: 'folder-1',
      afterSuccess: {
        kind: 'navigate-root-and-clear-browse',
        targetFolderId: null,
        emitChangedEvent: true,
      },
    });
  });

  it('plans non-current folder deletion with reload only', () => {
    expect(
      planDeleteFolderCommand({
        folderId: 'folder-1',
        currentFolderId: 'folder-2',
      }),
    ).toEqual({
      busyId: 'folder-1',
      folderId: 'folder-1',
      afterSuccess: {
        kind: 'reload',
        emitChangedEvent: true,
      },
    });
  });

  it('plans bulk delete with selected ids and selection clearing', () => {
    expect(
      planBulkDeleteCommand({
        fileIds: new Set(['file-1', 'file-2']),
        folderIds: new Set(['folder-1']),
      }),
    ).toEqual({
      kind: 'delete',
      payload: {
        fileIds: ['file-1', 'file-2'],
        folderIds: ['folder-1'],
      },
      afterSuccess: {
        clearSelection: true,
        emitChangedEvent: true,
        reload: true,
      },
    });
  });

  it('plans no bulk download for empty or stale single-file selections', () => {
    expect(
      planFileManagerBulkDownload(
        createEmptyFileManagerSelection(),
        [{ id: 'file-1' }],
      ),
    ).toEqual({ kind: 'none' });

    expect(
      planFileManagerBulkDownload(
        { fileIds: new Set(['file-gone']), folderIds: new Set() },
        [{ id: 'file-1' }],
      ),
    ).toEqual({ kind: 'none' });
  });

  it('plans single-file downloads without archive payloads', () => {
    const file = { id: 'file-1', filename: 'report.pdf' };

    expect(
      planFileManagerBulkDownload(
        { fileIds: new Set(['file-1']), folderIds: new Set() },
        [file],
      ),
    ).toEqual({ kind: 'single-file', file });
  });

  it('plans archive downloads for multi-file, folder, and mixed selections', () => {
    expect(
      planFileManagerBulkDownload(
        {
          fileIds: new Set(['file-1', 'file-2']),
          folderIds: new Set(),
        },
        [{ id: 'file-1' }, { id: 'file-2' }],
      ),
    ).toEqual({
      kind: 'archive',
      payload: { fileIds: ['file-1', 'file-2'], folderIds: [] },
    });

    expect(
      planFileManagerBulkDownload(
        {
          fileIds: new Set(),
          folderIds: new Set(['folder-1']),
        },
        [],
      ),
    ).toEqual({
      kind: 'archive',
      payload: { fileIds: [], folderIds: ['folder-1'] },
    });

    expect(
      planFileManagerBulkDownload(
        {
          fileIds: new Set(['file-1']),
          folderIds: new Set(['folder-1']),
        },
        [{ id: 'file-1' }],
      ),
    ).toEqual({
      kind: 'archive',
      payload: { fileIds: ['file-1'], folderIds: ['folder-1'] },
    });
  });
});
