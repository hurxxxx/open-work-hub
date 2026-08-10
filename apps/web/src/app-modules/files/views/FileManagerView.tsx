import { useTranslation } from 'react-i18next';
import {
  CircleAlert,
  CircleSlash2,
  Clock3,
  CheckCircle2,
  Download,
  Eye,
  File,
  FileUp,
  Folder,
  FolderPlus,
  Home,
  Loader2,
  Lock,
  Pencil,
  RefreshCw,
  Share2,
  Trash2,
  X,
} from 'lucide-react';
import { InlineNotice } from '@open-work-hub/ui';

import { cn } from '@/src/lib/utils';
import {
  type FileFolderItem,
  type FileItem,
  type FileVisibility,
} from '../api/files-api';
import { FileImagePreviewDialog } from './FileImagePreviewDialog';
import {
  FILE_RAG_STATUS_PRESENTATION,
  formatFileSize,
  formatFileUpdatedAt,
  isPreviewableImageFile,
  shouldDisplayFileRagStatus,
} from './file-manager-view-model';
import {
  useFileManagerController,
  type BulkAction,
} from './useFileManagerController';

export function FileManagerView() {
  const controller = useFileManagerController();
  return <FileManagerViewContent controller={controller} />;
}

function FileManagerViewContent({
  controller,
}: {
  controller: ReturnType<typeof useFileManagerController>;
}) {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const {
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
    setImagePreview,
    setUploadVisibility,
    timeZone,
    uploadVisibility,
    workspaceName,
  } = controller;
  const visibleTitle = currentFolder?.name ?? t('files.title');

  return (
    <div
      className="flex h-full min-h-0 flex-col bg-app-bg"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <header className="border-b border-app-border bg-app-bg px-5 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-app-ink/60">
              <FolderOpenIcon />
              <span className="app-text-overline">{workspaceName}</span>
            </div>
            <h1 className="app-text-title mt-1 truncate text-app-ink">
              {visibleTitle}
            </h1>
            <Breadcrumbs
              breadcrumbs={browse?.breadcrumbs ?? []}
              onSelect={navigateToFolder}
              rootLabel={t('files.sidebar.root')}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {currentFolder ? (
              <VisibilityReadOnlyControl
                label={t('files.fields.inheritedVisibility')}
                value={effectiveUploadVisibility}
              />
            ) : (
              <VisibilityControl
                label={t('files.fields.uploadVisibility')}
                onChange={setUploadVisibility}
                value={uploadVisibility}
              />
            )}
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-app-border px-3 app-text-control text-app-ink transition-colors hover:bg-app-surface-hover"
            >
              <RefreshCw size={16} />
              {t('files.actions.refresh')}
            </button>
            <button
              type="button"
              onClick={openCreateFolder}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-app-border px-3 app-text-control text-app-ink transition-colors hover:bg-app-surface-hover"
            >
              <FolderPlus size={16} />
              {t('files.actions.newFolder')}
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={hasActiveUploads}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-app-accent px-3 app-text-control text-app-accent-fg transition-opacity disabled:opacity-60"
            >
              {hasActiveUploads ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <FileUp size={16} />
              )}
              {t('files.actions.upload')}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => void handleFileChange(event)}
              aria-label={t('files.actions.upload')}
            />
          </div>
        </div>

        {currentFolder?.can_manage ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => openEditFolder(currentFolder)}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-app-border px-2.5 app-text-control-sm text-app-ink transition-colors hover:bg-app-surface-hover"
            >
              <Pencil size={14} />
              {t('files.actions.editFolder')}
            </button>
            <button
              type="button"
              onClick={() => void handleDeleteFolder(currentFolder)}
              disabled={busyId === currentFolder.id}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-app-danger/30 px-2.5 app-text-control-sm text-app-danger transition-colors hover:bg-app-danger/10 disabled:opacity-60"
            >
              <Trash2 size={14} />
              {t('files.actions.deleteFolder')}
            </button>
          </div>
        ) : null}
      </header>

      {error ? (
        <InlineNotice
          className="mx-5 mt-4 app-text-body-sm"
          role="alert"
          tone="danger"
        >
          {error}
        </InlineNotice>
      ) : null}

      <main
        className="relative min-h-0 flex-1 overflow-y-auto p-5"
        aria-label={t('files.dropUpload.ariaLabel')}
        aria-busy={hasActiveUploads}
      >
        {draggingFiles ? (
          <div className="pointer-events-none absolute inset-5 z-20 flex items-center justify-center rounded-md border-2 border-dashed border-app-accent bg-app-bg/85 text-app-ink shadow-sm backdrop-blur-sm">
            <div className="flex flex-col items-center gap-2 text-center">
              <span className="flex size-12 items-center justify-center rounded-md bg-app-accent text-app-accent-fg">
                <FileUp size={24} />
              </span>
              <span className="app-text-body font-semibold">
                {t('files.dropUpload.title')}
              </span>
              <span className="app-text-body-sm text-app-ink/60">
                {t('files.dropUpload.description', {
                  visibility: t(
                    `files.visibility.${effectiveUploadVisibility}`,
                  ),
                })}
              </span>
            </div>
          </div>
        ) : null}

        {selectedCount > 0 ? (
          <BulkActionBar
            allVisibleSelected={allVisibleSelected}
            busyAction={bulkAction}
            onDelete={() => void handleBulkDelete()}
            onDownload={() => void handleBulkDownload()}
            onSelectAll={setAllVisibleSelected}
            selectedCount={selectedCount}
            selectedSize={selectedVisibleSize}
          />
        ) : null}

        {loadState === 'loading' && !browse ? (
          <div className="flex h-64 items-center justify-center text-app-ink/55">
            <Loader2 size={24} className="animate-spin" />
          </div>
        ) : null}

        {isEmpty ? (
          <div className="flex h-64 items-center justify-center rounded-md border border-dashed border-app-border">
            <span className="app-text-body text-app-ink/55">
              {t('files.empty')}
            </span>
          </div>
        ) : null}

        {!isEmpty ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
            {folders.map((folder) => (
              <FolderTile
                key={folder.id}
                busy={busyId === folder.id}
                folder={folder}
                onDelete={() => void handleDeleteFolder(folder)}
                onEdit={() => openEditFolder(folder)}
                onOpen={() => navigateToFolder(folder.id)}
                onSelectedChange={(checked) =>
                  setFolderSelected(folder.id, checked)
                }
                selected={filteredSelection.folderIds.has(folder.id)}
              />
            ))}
            {files.map((file) => (
              <FileTile
                key={file.id}
                busy={busyId === file.id}
                canPreview={isPreviewableImageFile(file)}
                file={file}
                formatDate={(value) =>
                  formatFileUpdatedAt(value, i18n.language, timeZone)
                }
                onDelete={() => void handleDeleteFile(file)}
                onDownload={() => void handleDownload(file)}
                onPreview={() => void handlePreview(file)}
                onSelectedChange={(checked) =>
                  setFileSelected(file.id, checked)
                }
                previewing={previewBusyId === file.id}
                selected={filteredSelection.fileIds.has(file.id)}
                t={t}
              />
            ))}
          </div>
        ) : null}
      </main>

      {folderDialog ? (
        <FolderDialog
          folderName={folderName}
          folderVisibility={folderVisibility}
          mode={folderDialog.mode}
          onClose={() => setFolderDialog(null)}
          onNameChange={setFolderName}
          onSubmit={() => void handleFolderSubmit()}
          onVisibilityChange={setFolderVisibility}
          saving={savingFolder}
          visibilityMode={
            folderDialog.mode === 'edit'
              ? 'locked'
              : currentFolder
                ? 'inherited'
                : 'editable'
          }
        />
      ) : null}
      {imagePreview ? (
        <FileImagePreviewDialog
          file={imagePreview.file}
          onClose={() => setImagePreview(null)}
          url={imagePreview.url}
        />
      ) : null}
    </div>
  );
}

function FolderOpenIcon() {
  return <Folder size={18} />;
}

function BulkActionBar({
  allVisibleSelected,
  busyAction,
  onDelete,
  onDownload,
  onSelectAll,
  selectedCount,
  selectedSize,
}: {
  allVisibleSelected: boolean;
  busyAction: BulkAction;
  onDelete: () => void;
  onDownload: () => void;
  onSelectAll: (checked: boolean) => void;
  selectedCount: number;
  selectedSize: number;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-app-border bg-app-surface px-3 py-2">
      <label className="inline-flex min-w-0 items-center gap-2 app-text-body-sm text-app-ink">
        <input
          type="checkbox"
          checked={allVisibleSelected}
          onChange={(event) => onSelectAll(event.currentTarget.checked)}
          className="size-4 rounded border-app-border accent-app-accent"
        />
        <span className="truncate">
          {t(
            selectedSize > 0
              ? 'files.selection.summaryWithSize'
              : 'files.selection.summary',
            {
              count: selectedCount,
              size: formatFileSize(selectedSize),
            },
          )}
        </span>
      </label>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={onDownload}
          disabled={busyAction !== null}
          className="inline-flex h-8 items-center gap-2 rounded-md border border-app-border px-2.5 app-text-control-sm text-app-ink transition-colors hover:bg-app-surface-hover disabled:opacity-60"
        >
          {busyAction === 'download' ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Download size={14} />
          )}
          {t('files.actions.download')}
        </button>
        <button
          type="button"
          onClick={onDelete}
          disabled={busyAction !== null}
          className="inline-flex h-8 items-center gap-2 rounded-md border border-app-danger/30 px-2.5 app-text-control-sm text-app-danger transition-colors hover:bg-app-danger/10 disabled:opacity-60"
        >
          {busyAction === 'delete' ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Trash2 size={14} />
          )}
          {t('files.actions.delete')}
        </button>
      </div>
    </div>
  );
}

function Breadcrumbs({
  breadcrumbs,
  onSelect,
  rootLabel,
}: {
  breadcrumbs: FileFolderItem[];
  onSelect: (folderId: string | null) => void;
  rootLabel: string;
}) {
  return (
    <nav className="mt-2 flex min-w-0 flex-wrap items-center gap-1 app-text-caption text-app-ink/55">
      <button
        type="button"
        onClick={() => onSelect(null)}
        className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
      >
        <Home size={13} />
        <span>{rootLabel}</span>
      </button>
      {breadcrumbs.map((folder) => (
        <span
          key={folder.id}
          className="inline-flex min-w-0 items-center gap-1"
        >
          <span className="text-app-ink/30">/</span>
          <button
            type="button"
            onClick={() => onSelect(folder.id)}
            className="max-w-44 truncate rounded-md px-1.5 py-1 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
          >
            {folder.name}
          </button>
        </span>
      ))}
    </nav>
  );
}

function VisibilityControl({
  label,
  onChange,
  value,
}: {
  label: string;
  onChange: (value: FileVisibility) => void;
  value: FileVisibility;
}) {
  const { t } = useTranslation('apps');
  return (
    <fieldset
      aria-label={label}
      className="flex h-9 items-center gap-1 rounded-md border border-app-border bg-app-surface px-1"
    >
      {(['private', 'workspace'] as const).map((option) => {
        const Icon = option === 'private' ? Lock : Share2;
        return (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            aria-pressed={value === option}
            title={t(`files.visibility.${option}`)}
            className={cn(
              'inline-flex h-7 items-center gap-1.5 rounded px-2 app-text-control-sm transition-colors',
              value === option
                ? 'bg-app-accent text-app-accent-fg'
                : 'text-app-ink/65 hover:bg-app-surface-hover hover:text-app-ink',
            )}
          >
            <Icon size={14} />
            <span>{t(`files.visibility.${option}`)}</span>
          </button>
        );
      })}
    </fieldset>
  );
}

function VisibilityReadOnlyControl({
  label,
  value,
}: {
  label: string;
  value: FileVisibility;
}) {
  const { t } = useTranslation('apps');
  const Icon = value === 'private' ? Lock : Share2;
  return (
    <fieldset
      aria-label={label}
      className="flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 app-text-control-sm text-app-ink/70"
    >
      <Icon size={14} />
      <span>{label}</span>
      <span className="text-app-ink">{t(`files.visibility.${value}`)}</span>
    </fieldset>
  );
}

function FolderTile({
  busy,
  folder,
  onDelete,
  onEdit,
  onOpen,
  onSelectedChange,
  selected,
}: {
  busy: boolean;
  folder: FileFolderItem;
  onDelete: () => void;
  onEdit: () => void;
  onOpen: () => void;
  onSelectedChange: (checked: boolean) => void;
  selected: boolean;
}) {
  const { t } = useTranslation('apps');
  const VisibilityIcon = folder.visibility === 'private' ? Lock : Share2;
  return (
    <article
      className={cn(
        'group rounded-md border bg-app-surface p-3 transition-colors hover:border-app-accent/40',
        selected
          ? 'border-app-accent ring-1 ring-app-accent/40'
          : 'border-app-border',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={onOpen}
          className="flex min-w-0 flex-1 flex-col items-start gap-3 text-left"
        >
          <span className="flex size-11 items-center justify-center rounded-md bg-app-accent/12 text-app-accent">
            <Folder size={23} />
          </span>
          <span className="app-text-body-sm line-clamp-2 min-h-10 w-full break-words font-semibold text-app-ink">
            {folder.name}
          </span>
        </button>
        <input
          type="checkbox"
          checked={selected}
          onChange={(event) => onSelectedChange(event.currentTarget.checked)}
          aria-label={t('files.selection.selectFolder', { name: folder.name })}
          className="size-4 shrink-0 rounded border-app-border accent-app-accent"
        />
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="inline-flex min-w-0 items-center gap-1 app-text-caption text-app-ink/55">
          <VisibilityIcon size={12} />
          <span className="truncate">
            {t(`files.visibility.${folder.visibility}`)}
          </span>
        </span>
        {folder.can_manage ? (
          <span className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={onEdit}
              title={t('files.actions.editFolder')}
              aria-label={t('files.actions.editFolder')}
              className="flex size-7 items-center justify-center rounded-md text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
            >
              <Pencil size={14} />
            </button>
            <button
              type="button"
              onClick={onDelete}
              disabled={busy}
              title={t('files.actions.deleteFolder')}
              aria-label={t('files.actions.deleteFolder')}
              className="flex size-7 items-center justify-center rounded-md text-app-ink/55 transition-colors hover:bg-app-danger/10 hover:text-app-danger disabled:opacity-60"
            >
              {busy ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Trash2 size={14} />
              )}
            </button>
          </span>
        ) : null}
      </div>
    </article>
  );
}

function FileTile({
  busy,
  canPreview,
  file,
  formatDate,
  onDelete,
  onDownload,
  onPreview,
  onSelectedChange,
  previewing,
  selected,
  t,
}: {
  busy: boolean;
  canPreview: boolean;
  file: FileItem;
  formatDate: (value: string) => string;
  onDelete: () => void;
  onDownload: () => void;
  onPreview: () => void;
  onSelectedChange: (checked: boolean) => void;
  previewing: boolean;
  selected: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  const VisibilityIcon = file.visibility === 'private' ? Lock : Share2;
  const ragStatus = FILE_RAG_STATUS_PRESENTATION[file.rag_status];
  const RagStatusIcon =
    file.rag_status === 'ready'
      ? CheckCircle2
      : file.rag_status === 'failed'
        ? CircleAlert
        : file.rag_status === 'unsupported' || file.rag_status === 'disabled'
          ? CircleSlash2
          : file.rag_status === 'pending'
            ? Clock3
            : Loader2;
  const ragStatusLabel = t(ragStatus.labelKey);
  return (
    <article
      className={cn(
        'rounded-md border bg-app-surface p-3 transition-colors hover:border-app-accent/40',
        selected
          ? 'border-app-accent ring-1 ring-app-accent/40'
          : 'border-app-border',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-col items-start gap-3">
          <span className="flex size-11 items-center justify-center rounded-md bg-app-surface-hover text-app-ink/65">
            <File size={22} />
          </span>
          <span className="app-text-body-sm line-clamp-2 min-h-10 w-full break-words font-semibold text-app-ink">
            {file.filename}
          </span>
        </div>
        <input
          type="checkbox"
          checked={selected}
          onChange={(event) => onSelectedChange(event.currentTarget.checked)}
          aria-label={t('files.selection.selectFile', { name: file.filename })}
          className="size-4 shrink-0 rounded border-app-border accent-app-accent"
        />
      </div>
      <div className="mt-2 space-y-1 app-text-caption text-app-ink/55">
        <div>{formatFileSize(file.size_bytes)}</div>
        <div>{formatDate(file.updated_at)}</div>
        <div className="flex items-center gap-1">
          <VisibilityIcon size={12} />
          <span>{t(`files.visibility.${file.visibility}`)}</span>
        </div>
        {shouldDisplayFileRagStatus(file.rag_status) ? (
          <div className="flex items-center gap-1.5">
            <span>{t('files.ragStatus.label')}</span>
            <span
              role="status"
              aria-live="polite"
              aria-label={t('files.ragStatus.ariaLabel', {
                name: file.filename,
                status: ragStatusLabel,
              })}
              className={cn(
                'inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 font-medium',
                ragStatus.className,
              )}
            >
              <RagStatusIcon
                size={11}
                className={
                  file.rag_status === 'processing' ? 'animate-spin' : undefined
                }
              />
              <span>{ragStatusLabel}</span>
            </span>
          </div>
        ) : null}
      </div>
      <div className="mt-3 flex items-center justify-end gap-1">
        {canPreview ? (
          <button
            type="button"
            onClick={onPreview}
            disabled={busy || previewing}
            title={t('files.actions.preview')}
            aria-label={t('files.actions.preview')}
            className="flex size-8 items-center justify-center rounded-md text-app-ink/60 transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:opacity-60"
          >
            {previewing ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Eye size={15} />
            )}
          </button>
        ) : null}
        <button
          type="button"
          onClick={onDownload}
          disabled={busy}
          title={t('files.actions.download')}
          aria-label={t('files.actions.download')}
          className="flex size-8 items-center justify-center rounded-md text-app-ink/60 transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:opacity-60"
        >
          {busy ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Download size={15} />
          )}
        </button>
        {file.can_delete ? (
          <button
            type="button"
            onClick={onDelete}
            disabled={busy}
            title={t('files.actions.delete')}
            aria-label={t('files.actions.delete')}
            className="flex size-8 items-center justify-center rounded-md text-app-ink/60 transition-colors hover:bg-app-danger/10 hover:text-app-danger disabled:opacity-60"
          >
            <Trash2 size={15} />
          </button>
        ) : null}
      </div>
    </article>
  );
}

function FolderDialog({
  folderName,
  folderVisibility,
  mode,
  onClose,
  onNameChange,
  onSubmit,
  onVisibilityChange,
  saving,
  visibilityMode,
}: {
  folderName: string;
  folderVisibility: FileVisibility;
  mode: 'create' | 'edit';
  onClose: () => void;
  onNameChange: (value: string) => void;
  onSubmit: () => void;
  onVisibilityChange: (value: FileVisibility) => void;
  saving: boolean;
  visibilityMode: 'editable' | 'inherited' | 'locked';
}) {
  const { t } = useTranslation(['apps', 'common']);
  const readOnlyVisibilityLabel =
    visibilityMode === 'inherited'
      ? t('files.fields.inheritedVisibility')
      : t('files.fields.visibilityLocked');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4">
      <dialog
        open
        className="w-full max-w-md rounded-md border border-app-border bg-app-surface p-4 shadow-2xl"
        aria-labelledby="file-folder-dialog-title"
      >
        <div className="flex items-center justify-between gap-3">
          <h2
            id="file-folder-dialog-title"
            className="app-text-title text-app-ink"
          >
            {mode === 'create'
              ? t('files.dialog.createTitle')
              : t('files.dialog.editTitle')}
          </h2>
          <button
            type="button"
            onClick={onClose}
            title={t('common:actions.close')}
            aria-label={t('common:actions.close')}
            className="flex size-8 items-center justify-center rounded-md text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
          >
            <X size={16} />
          </button>
        </div>

        <label className="app-text-control-sm mt-4 block text-app-ink">
          <span>{t('files.fields.folderName')}</span>
          <input
            value={folderName}
            onChange={(event) => onNameChange(event.currentTarget.value)}
            className="app-text-body-sm mt-1 w-full rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink outline-none transition-colors focus:border-app-accent"
            placeholder={t('files.fields.folderNamePlaceholder')}
          />
        </label>

        <div className="mt-4">
          {visibilityMode === 'editable' ? (
            <VisibilityControl
              label={t('files.fields.visibility')}
              onChange={onVisibilityChange}
              value={folderVisibility}
            />
          ) : (
            <VisibilityReadOnlyControl
              label={readOnlyVisibilityLabel}
              value={folderVisibility}
            />
          )}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 items-center rounded-md border border-app-border px-3 app-text-control text-app-ink transition-colors hover:bg-app-surface-hover"
          >
            {t('common:actions.cancel')}
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={saving || !folderName.trim()}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-app-accent px-3 app-text-control text-app-accent-fg transition-opacity disabled:opacity-60"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : null}
            {mode === 'create'
              ? t('common:actions.create')
              : t('common:actions.save')}
          </button>
        </div>
      </dialog>
    </div>
  );
}
