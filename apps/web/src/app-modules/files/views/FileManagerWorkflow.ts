export type FileManagerSelection = {
  fileIds: Set<string>;
  folderIds: Set<string>;
};

export type FileManagerFolderVisibility = 'private' | 'company';

type VisibleItemIds = {
  files: readonly { id: string }[];
  folders: readonly { id: string }[];
};

export function createEmptyFileManagerSelection(): FileManagerSelection {
  return {
    fileIds: new Set(),
    folderIds: new Set(),
  };
}

export function toggleFileSelection(
  selection: FileManagerSelection,
  fileId: string,
  checked: boolean,
): FileManagerSelection {
  return {
    ...selection,
    fileIds: toggleId(selection.fileIds, fileId, checked),
  };
}

export function toggleFolderSelection(
  selection: FileManagerSelection,
  folderId: string,
  checked: boolean,
): FileManagerSelection {
  return {
    ...selection,
    folderIds: toggleId(selection.folderIds, folderId, checked),
  };
}

export function selectAllVisibleFileManagerItems(
  visibleItems: VisibleItemIds,
  checked: boolean,
): FileManagerSelection {
  if (!checked) {
    return createEmptyFileManagerSelection();
  }
  return {
    fileIds: new Set(visibleItems.files.map((file) => file.id)),
    folderIds: new Set(visibleItems.folders.map((folder) => folder.id)),
  };
}

export function filterSelectionToVisibleItems(
  selection: FileManagerSelection,
  visibleItems: VisibleItemIds,
): FileManagerSelection {
  const fileIds = filterIds(
    selection.fileIds,
    new Set(visibleItems.files.map((file) => file.id)),
  );
  const folderIds = filterIds(
    selection.folderIds,
    new Set(visibleItems.folders.map((folder) => folder.id)),
  );
  if (fileIds === selection.fileIds && folderIds === selection.folderIds) {
    return selection;
  }
  return { fileIds, folderIds };
}

export function summarizeFileManagerSelection<
  TFile extends { id: string; size_bytes: number },
  TFolder extends { id: string },
>(
  selection: FileManagerSelection,
  visibleItems: {
    files: readonly TFile[];
    folders: readonly TFolder[];
  },
): {
  allVisibleSelected: boolean;
  selectedCount: number;
  selectedFiles: TFile[];
  selectedVisibleSize: number;
} {
  const selectedFiles = visibleItems.files.filter((file) =>
    selection.fileIds.has(file.id),
  );
  const visibleItemCount =
    visibleItems.folders.length + visibleItems.files.length;
  return {
    allVisibleSelected:
      visibleItemCount > 0 &&
      visibleItems.folders.every((folder) =>
        selection.folderIds.has(folder.id),
      ) &&
      visibleItems.files.every((file) => selection.fileIds.has(file.id)),
    selectedCount: selection.fileIds.size + selection.folderIds.size,
    selectedFiles,
    selectedVisibleSize: selectedFiles.reduce(
      (total, file) => total + file.size_bytes,
      0,
    ),
  };
}

export type FileManagerBulkDownloadPlan<TFile> =
  | { kind: 'none' }
  | { kind: 'single-file'; file: TFile }
  | { kind: 'archive'; payload: { fileIds: string[]; folderIds: string[] } };

export type FileManagerCreateFolderPlan = {
  payload: {
    name: string;
    parent_id: string | null;
    visibility: FileManagerFolderVisibility;
  };
  afterSuccess: {
    closeDialog: true;
    emitChangedEvent: true;
    reload: true;
  };
};

export function planCreateFolderCommand(input: {
  name: string;
  currentFolderId: string | null;
  currentFolderVisibility: FileManagerFolderVisibility | null | undefined;
  selectedVisibility: FileManagerFolderVisibility;
}): FileManagerCreateFolderPlan {
  return {
    payload: {
      name: input.name,
      parent_id: input.currentFolderId,
      visibility: input.currentFolderVisibility ?? input.selectedVisibility,
    },
    afterSuccess: {
      closeDialog: true,
      emitChangedEvent: true,
      reload: true,
    },
  };
}

export type FileManagerDeleteFolderPlan = {
  busyId: string;
  folderId: string;
  afterSuccess:
    | {
        kind: 'navigate-root-and-clear-browse';
        targetFolderId: null;
        emitChangedEvent: true;
      }
    | { kind: 'reload'; emitChangedEvent: true };
};

export function planDeleteFolderCommand(input: {
  folderId: string;
  currentFolderId: string | null;
}): FileManagerDeleteFolderPlan {
  return {
    busyId: input.folderId,
    folderId: input.folderId,
    afterSuccess:
      input.folderId === input.currentFolderId
        ? {
            kind: 'navigate-root-and-clear-browse',
            targetFolderId: null,
            emitChangedEvent: true,
          }
        : { kind: 'reload', emitChangedEvent: true },
  };
}

export type FileManagerBulkDeletePlan =
  | { kind: 'none' }
  | {
      kind: 'delete';
      payload: { fileIds: string[]; folderIds: string[] };
      afterSuccess: {
        clearSelection: true;
        emitChangedEvent: true;
        reload: true;
      };
    };

export function planBulkDeleteCommand(
  selection: FileManagerSelection,
): FileManagerBulkDeletePlan {
  if (selection.fileIds.size === 0 && selection.folderIds.size === 0) {
    return { kind: 'none' };
  }

  return {
    kind: 'delete',
    payload: {
      fileIds: Array.from(selection.fileIds),
      folderIds: Array.from(selection.folderIds),
    },
    afterSuccess: {
      clearSelection: true,
      emitChangedEvent: true,
      reload: true,
    },
  };
}

export function planFileManagerBulkDownload<TFile extends { id: string }>(
  selection: FileManagerSelection,
  visibleFiles: readonly TFile[],
): FileManagerBulkDownloadPlan<TFile> {
  if (selection.fileIds.size === 0 && selection.folderIds.size === 0) {
    return { kind: 'none' };
  }

  if (selection.fileIds.size === 1 && selection.folderIds.size === 0) {
    const selectedFileId = Array.from(selection.fileIds)[0];
    const selectedFile = visibleFiles.find(
      (file) => file.id === selectedFileId,
    );
    return selectedFile
      ? { kind: 'single-file', file: selectedFile }
      : { kind: 'none' };
  }

  return {
    kind: 'archive',
    payload: {
      fileIds: Array.from(selection.fileIds),
      folderIds: Array.from(selection.folderIds),
    },
  };
}

function toggleId(ids: Set<string>, id: string, checked: boolean): Set<string> {
  const next = new Set(ids);
  if (checked) {
    next.add(id);
  } else {
    next.delete(id);
  }
  return next;
}

function filterIds(ids: Set<string>, validIds: Set<string>): Set<string> {
  let changed = false;
  const next = new Set<string>();
  for (const id of ids) {
    if (validIds.has(id)) {
      next.add(id);
    } else {
      changed = true;
    }
  }
  return changed ? next : ids;
}
