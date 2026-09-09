import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  authenticatedContentObjectUrl,
  downloadAuthenticatedContent,
  downloadBlobAsFile,
} from '@/src/platform/browser/browser-download';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  browseFiles,
  bulkDeleteFileItems,
  createFileFolder,
  deleteDriveFile,
  deleteFileFolder,
  downloadFileArchive,
  getFileDownloadUrl,
  getFilePreviewUrl,
  updateFileFolder,
  type FileBrowseResponse,
  type FileFolderItem,
  type FileItem,
  type FileVisibility,
} from '../api/files-api';
import { useFileUploadManager } from '../file-upload-provider';
import {
  FILES_CHANGED_EVENT,
  FILES_UPLOAD_COMPLETED_EVENT,
} from '../file-upload-session';
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
import {
  FILE_RAG_POLL_INITIAL_DELAY_MS,
  fileRagPollingSignature,
  nextFileRagPollingDelay,
  shouldPollFileRagStatuses,
} from './file-manager-view-model';

export type LoadState = 'idle' | 'loading' | 'ready' | 'error';
export type BulkAction = 'delete' | 'download' | null;
export type FolderDialogState =
  | { mode: 'create'; folder: null }
  | { mode: 'edit'; folder: FileFolderItem };
export type ImagePreviewState = {
  file: FileItem;
  url: string;
};

function isFileDrag(event: DragEvent<HTMLElement>) {
  return Array.from(event.dataTransfer.types).includes('Files');
}

export function useFileManagerController() {
  const { t, i18n } = useTranslation(['apps', 'common']);

  const [searchParams, setSearchParams] = useSearchParams();
  const { token, user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const { hasActiveUploads, startUpload } = useFileUploadManager();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dragDepthRef = useRef(0);
  const loadAbortRef = useRef<AbortController | null>(null);
  const foregroundLoadAbortRef = useRef<AbortController | null>(null);
  const loadRequestSeqRef = useRef(0);
  const previewRequestSeqRef = useRef(0);
  const previewObjectUrlRef = useRef<string | null>(null);
  const folderId = searchParams.get('folder');
  const [browse, setBrowse] = useState<FileBrowseResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [uploadVisibility, setUploadVisibility] =
    useState<FileVisibility>('private');
  const [draggingFiles, setDraggingFiles] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [previewBusyId, setPreviewBusyId] = useState<string | null>(null);
  const [bulkAction, setBulkAction] = useState<BulkAction>(null);
  const [selection, setSelection] = useState(createEmptyFileManagerSelection);
  const [imagePreview, setImagePreview] = useState<ImagePreviewState | null>(
    null,
  );
  const [folderDialog, setFolderDialog] = useState<FolderDialogState | null>(
    null,
  );
  const [folderName, setFolderName] = useState('');
  const [folderVisibility, setFolderVisibility] =
    useState<FileVisibility>('private');
  const [savingFolder, setSavingFolder] = useState(false);

  const closeImagePreview = useCallback(() => {
    previewRequestSeqRef.current += 1;
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
    setImagePreview(null);
  }, []);

  useEffect(
    () => () => {
      previewRequestSeqRef.current += 1;
      if (previewObjectUrlRef.current) {
        URL.revokeObjectURL(previewObjectUrlRef.current);
        previewObjectUrlRef.current = null;
      }
    },
    [],
  );

  useEffect(() => {
    closeImagePreview();
  }, [closeImagePreview, token]);

  const companyName = t('common:labels.company');
  const currentFolder = browse?.current_folder ?? null;
  const effectiveUploadVisibility =
    currentFolder?.visibility ?? uploadVisibility;

  const load = useCallback(
    async (options: { silent?: boolean } = {}) => {
      if (!token) {
        return false;
      }
      if (options.silent && foregroundLoadAbortRef.current !== null) {
        return false;
      }
      const sequence = loadRequestSeqRef.current + 1;
      loadRequestSeqRef.current = sequence;
      loadAbortRef.current?.abort();
      const controller = new AbortController();
      loadAbortRef.current = controller;
      if (!options.silent) {
        foregroundLoadAbortRef.current = controller;
        setLoadState('loading');
        setError(null);
      }
      try {
        const response = await browseFiles(token, folderId, {
          signal: controller.signal,
        });
        if (
          !controller.signal.aborted &&
          loadRequestSeqRef.current === sequence
        ) {
          setBrowse(response);
          if (!options.silent) {
            setLoadState('ready');
          }
          return true;
        }
        return false;
      } catch (caughtError) {
        if (
          !options.silent &&
          !controller.signal.aborted &&
          loadRequestSeqRef.current === sequence
        ) {
          setLoadState('error');
          setError(
            caughtError instanceof Error
              ? caughtError.message
              : t('files.errors.loadFailed'),
          );
        }
        return false;
      } finally {
        if (loadAbortRef.current === controller) {
          loadAbortRef.current = null;
        }
        if (foregroundLoadAbortRef.current === controller) {
          foregroundLoadAbortRef.current = null;
        }
      }
    },
    [folderId, t, token],
  );

  useEffect(() => {
    void load();
    return () => {
      loadAbortRef.current?.abort();
    };
  }, [load]);

  const openCreateFolder = useCallback(() => {
    setFolderDialog({ mode: 'create', folder: null });
    setFolderName('');
    setFolderVisibility(effectiveUploadVisibility);
  }, [effectiveUploadVisibility]);

  useEffect(() => {
    const uploadHandler = () => fileInputRef.current?.click();
    const createFolderHandler = () => openCreateFolder();
    window.addEventListener('files:upload', uploadHandler);
    window.addEventListener('files:create-folder', createFolderHandler);
    return () => {
      window.removeEventListener('files:upload', uploadHandler);
      window.removeEventListener('files:create-folder', createFolderHandler);
    };
  }, [openCreateFolder]);

  useEffect(() => {
    const uploadCompletedHandler = (event: Event) => {
      const detail = (
        event as CustomEvent<{
          folderId?: string | null;
        }>
      ).detail;
      if ((detail.folderId ?? null) !== (folderId ?? null)) {
        return;
      }
      void load();
    };
    window.addEventListener(
      FILES_UPLOAD_COMPLETED_EVENT,
      uploadCompletedHandler,
    );
    return () => {
      window.removeEventListener(
        FILES_UPLOAD_COMPLETED_EVENT,
        uploadCompletedHandler,
      );
    };
  }, [folderId, load]);

  const folders = useMemo(() => browse?.folders ?? [], [browse?.folders]);
  const files = useMemo(() => browse?.files ?? [], [browse?.files]);
  const shouldPollRagStatuses = useMemo(
    () => shouldPollFileRagStatuses(files),
    [files],
  );
  const ragPollingSignature = useMemo(
    () => fileRagPollingSignature(files),
    [files],
  );

  useEffect(() => {
    if (!shouldPollRagStatuses) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;
    let nextDelayMs = FILE_RAG_POLL_INITIAL_DELAY_MS;
    const schedule = () => {
      timer = window.setTimeout(run, nextDelayMs);
    };
    const run = async () => {
      timer = undefined;
      if (document.visibilityState === 'hidden') {
        return;
      }
      const succeeded = await load({ silent: true });
      nextDelayMs = nextFileRagPollingDelay(nextDelayMs, succeeded);
      if (!cancelled) {
        schedule();
      }
    };
    const handleVisibilityChange = () => {
      if (
        document.visibilityState === 'visible' &&
        timer === undefined &&
        !cancelled
      ) {
        schedule();
      }
    };

    schedule();
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [load, ragPollingSignature, shouldPollRagStatuses]);

  const isEmpty =
    loadState === 'ready' && folders.length === 0 && files.length === 0;
  const filteredSelection = useMemo(
    () =>
      filterSelectionToVisibleItems(selection, {
        files,
        folders,
      }),
    [files, folders, selection],
  );
  const { allVisibleSelected, selectedCount, selectedVisibleSize } = useMemo(
    () =>
      summarizeFileManagerSelection(filteredSelection, {
        files,
        folders,
      }),
    [files, filteredSelection, folders],
  );

  const clearSelection = useCallback(() => {
    setSelection(createEmptyFileManagerSelection());
  }, []);

  function navigateToFolder(nextFolderId: string | null) {
    const next = new URLSearchParams(searchParams);
    if (nextFolderId) {
      next.set('folder', nextFolderId);
    } else {
      next.delete('folder');
    }
    setSearchParams(next);
  }

  function openEditFolder(folder: FileFolderItem) {
    setFolderDialog({ mode: 'edit', folder });
    setFolderName(folder.name);
    setFolderVisibility(folder.visibility);
  }

  function setAllVisibleSelected(checked: boolean) {
    setSelection(
      selectAllVisibleFileManagerItems(
        {
          files,
          folders,
        },
        checked,
      ),
    );
  }

  function setFileSelected(fileId: string, checked: boolean) {
    setSelection((current) => toggleFileSelection(current, fileId, checked));
  }

  function setFolderSelected(folderIdValue: string, checked: boolean) {
    setSelection((current) =>
      toggleFolderSelection(current, folderIdValue, checked),
    );
  }

  async function handleFolderSubmit() {
    if (!token || !folderDialog) {
      return;
    }
    setSavingFolder(true);
    setError(null);
    try {
      if (folderDialog.mode === 'create') {
        const plan = planCreateFolderCommand({
          name: folderName,
          currentFolderId: folderId,
          currentFolderVisibility: currentFolder?.visibility,
          selectedVisibility: folderVisibility,
        });
        if (
          plan.payload.visibility === 'company' &&
          !window.confirm(t('shell:contentPublication.confirm'))
        )
          return;
        await createFileFolder(token, {
          company_admin_read_acknowledged:
            plan.payload.visibility === 'company',
          name: plan.payload.name,
          parent_id: plan.payload.parent_id,
          visibility: plan.payload.visibility,
        });
      } else {
        await updateFileFolder(token, folderDialog.folder.id, {
          name: folderName,
        });
      }
      setFolderDialog(null);
      window.dispatchEvent(new CustomEvent(FILES_CHANGED_EVENT));
      await load();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('files.errors.saveFolderFailed'),
      );
    } finally {
      setSavingFolder(false);
    }
  }

  const uploadFiles = useCallback(
    (selectedFilesValue: File[]) => {
      if (!token || selectedFilesValue.length === 0) {
        return;
      }
      setError(null);
      if (
        effectiveUploadVisibility === 'company' &&
        !window.confirm(t('shell:contentPublication.confirm'))
      )
        return;
      const accepted = startUpload({
        companyAdminReadAcknowledged: effectiveUploadVisibility === 'company',
        files: selectedFilesValue,
        folderId,
        token,
        uploadVisibility: effectiveUploadVisibility,
      });
      if (!accepted) {
        setError(t('files.errors.uploadAlreadyRunning'));
      }
    },
    [effectiveUploadVisibility, folderId, startUpload, t, token],
  );

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selectedFilesValue = Array.from(event.target.files ?? []);
    event.target.value = '';
    uploadFiles(selectedFilesValue);
  }

  function handleDragEnter(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event)) {
      return;
    }
    event.preventDefault();
    if (hasActiveUploads) {
      event.dataTransfer.dropEffect = 'none';
      setDraggingFiles(false);
      return;
    }
    dragDepthRef.current += 1;
    setDraggingFiles(true);
  }

  function handleDragOver(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event)) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = hasActiveUploads ? 'none' : 'copy';
    if (!hasActiveUploads) {
      setDraggingFiles(true);
    }
  }

  function handleDragLeave(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event)) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setDraggingFiles(false);
    }
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event)) {
      return;
    }
    event.preventDefault();
    dragDepthRef.current = 0;
    setDraggingFiles(false);
    if (hasActiveUploads) {
      setError(t('files.errors.uploadAlreadyRunning'));
      return;
    }
    uploadFiles(Array.from(event.dataTransfer.files));
  }

  async function handleDownload(file: FileItem) {
    if (!token) {
      return;
    }
    setBusyId(file.id);
    setError(null);
    try {
      const response = await getFileDownloadUrl(token, file.id);
      await downloadAuthenticatedContent(token, response.url, file.filename);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('files.errors.downloadFailed'),
      );
    } finally {
      setBusyId(null);
    }
  }

  async function handlePreview(file: FileItem) {
    if (!token) {
      return;
    }
    setPreviewBusyId(file.id);
    setError(null);
    const sequence = previewRequestSeqRef.current + 1;
    previewRequestSeqRef.current = sequence;
    try {
      const response = await getFilePreviewUrl(token, file.id);
      const objectUrl = await authenticatedContentObjectUrl(
        token,
        response.url,
      );
      if (previewRequestSeqRef.current !== sequence) {
        URL.revokeObjectURL(objectUrl);
        return;
      }
      if (previewObjectUrlRef.current) {
        URL.revokeObjectURL(previewObjectUrlRef.current);
      }
      previewObjectUrlRef.current = objectUrl;
      setImagePreview({ file, url: objectUrl });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('files.errors.previewFailed'),
      );
    } finally {
      setPreviewBusyId(null);
    }
  }

  async function handleDeleteFile(file: FileItem) {
    if (!token) {
      return;
    }
    if (
      !window.confirm(t('files.confirm.deleteFile', { name: file.filename }))
    ) {
      return;
    }
    setBusyId(file.id);
    setError(null);
    try {
      await deleteDriveFile(token, file.id);
      window.dispatchEvent(new CustomEvent(FILES_CHANGED_EVENT));
      await load();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('files.errors.deleteFailed'),
      );
    } finally {
      setBusyId(null);
    }
  }

  async function handleDeleteFolder(folder: FileFolderItem) {
    if (!token) {
      return;
    }
    if (
      !window.confirm(t('files.confirm.deleteFolder', { name: folder.name }))
    ) {
      return;
    }
    const plan = planDeleteFolderCommand({
      folderId: folder.id,
      currentFolderId: folderId,
    });
    setBusyId(plan.busyId);
    setError(null);
    try {
      await deleteFileFolder(token, plan.folderId);
      if (plan.afterSuccess.kind === 'navigate-root-and-clear-browse') {
        navigateToFolder(plan.afterSuccess.targetFolderId);
        setBrowse(null);
      } else {
        await load();
      }
      window.dispatchEvent(new CustomEvent(FILES_CHANGED_EVENT));
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('files.errors.deleteFailed'),
      );
    } finally {
      setBusyId(null);
    }
  }

  async function handleBulkDelete() {
    if (!token || selectedCount === 0) {
      return;
    }
    if (
      !window.confirm(
        t('files.confirm.deleteSelected', { count: selectedCount }),
      )
    ) {
      return;
    }
    const plan = planBulkDeleteCommand(filteredSelection);
    if (plan.kind === 'none') {
      return;
    }
    setBulkAction('delete');
    setError(null);
    try {
      await bulkDeleteFileItems(token, plan.payload);
      clearSelection();
      window.dispatchEvent(new CustomEvent(FILES_CHANGED_EVENT));
      await load();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('files.errors.deleteFailed'),
      );
    } finally {
      setBulkAction(null);
    }
  }

  async function handleBulkDownload() {
    if (!token || selectedCount === 0) {
      return;
    }
    const plan = planFileManagerBulkDownload(filteredSelection, files);
    if (plan.kind === 'none') {
      return;
    }
    if (plan.kind === 'single-file') {
      await handleDownload(plan.file);
      return;
    }

    setBulkAction('download');
    setError(null);
    try {
      const archive = await downloadFileArchive(token, {
        fileIds: plan.payload.fileIds,
        folderIds: plan.payload.folderIds,
      });
      downloadBlobAsFile(archive.blob, archive.filename);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('files.errors.downloadFailed'),
      );
    } finally {
      setBulkAction(null);
    }
  }

  return {
    allVisibleSelected,
    browse,
    bulkAction,
    busyId,
    currentFolder,
    draggingFiles,
    effectiveUploadVisibility,
    error,
    fileInputRef,
    files,
    filteredSelection,
    folderDialog,
    folderName,
    folders,
    folderVisibility,
    handleBulkDelete,
    handleBulkDownload,
    handleDeleteFile,
    handleDeleteFolder,
    handleDownload,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    handleFileChange,
    handleFolderSubmit,
    handlePreview,
    hasActiveUploads,
    imagePreview,
    closeImagePreview,
    i18nLanguage: i18n.language,
    isEmpty,
    load,
    loadState,
    navigateToFolder,
    openCreateFolder,
    openEditFolder,
    previewBusyId,
    savingFolder,
    selectedCount,
    selectedVisibleSize,
    setAllVisibleSelected,
    setFileSelected,
    setFolderDialog,
    setFolderName,
    setFolderSelected,
    setFolderVisibility,
    setUploadVisibility,
    timeZone,
    uploadVisibility,
    companyName,
  };
}
