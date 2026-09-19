import { Button } from '@open-work-hub/ui';
import { Download, File, Trash2, Upload, X } from 'lucide-react';
import { useRef } from 'react';
import {
  attachmentDownload,
  locked,
  type Attachment,
  type Detail,
} from './api';
import type { Translate } from './i18n';

export const fileSize = (bytes: number) =>
  bytes < 1024
    ? `${bytes} B`
    : bytes < 1024 * 1024
      ? `${(bytes / 1024).toFixed(1)} KiB`
      : `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;

export function AttachmentBadges({
  files,
  taskId,
  t,
  onRemove,
  disabled = false,
}: {
  files: Attachment[];
  taskId: string;
  t: Translate;
  onRemove?: (id: string) => void;
  disabled?: boolean;
}) {
  return (
    <div
      className="attachment-badges"
      role="group"
      aria-label={t(onRemove ? 'Files for this message' : 'Attached files')}
    >
      {files.map((file) => (
        <span className="attachment-badge" key={file.id}>
          <File size={13} aria-hidden />
          {onRemove || file.deleted ? (
            <span title={file.name}>{file.name}</span>
          ) : (
            <a
              href={attachmentDownload(taskId, file.id)}
              download
              title={file.name}
            >
              {file.name}
            </a>
          )}
          {file.deleted && <small>{t('Deleted')}</small>}
          {onRemove && (
            <button
              type="button"
              disabled={disabled}
              aria-label={`${t('Remove from message')}: ${file.name}`}
              onClick={() => onRemove(file.id)}
            >
              <X size={13} />
            </button>
          )}
        </span>
      ))}
    </div>
  );
}

export function FileLibrary({
  task,
  selectedIds,
  t,
  busy,
  selectUploads = false,
  onToggle,
  onUpload,
  onDelete,
}: {
  task: Detail;
  selectedIds: string[];
  t: Translate;
  busy: boolean;
  selectUploads?: boolean;
  onToggle: (id: string) => void;
  onUpload: (files: File[], select: boolean) => void;
  onDelete: (id: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const used = task.attachments.reduce((total, file) => total + file.size, 0);
  return (
    <section
      className="attachment-library"
      onDragOver={(event) => {
        event.preventDefault();
      }}
      onDrop={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!busy)
          onUpload(Array.from(event.dataTransfer.files), selectUploads);
      }}
    >
      <div className="attachment-library-heading">
        <h3>{t('Task files')}</h3>
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          <Upload size={15} />
          {t('Upload files')}
        </Button>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          aria-label={t('Upload files')}
          onChange={(event) => {
            onUpload(
              Array.from(event.currentTarget.files ?? []),
              selectUploads,
            );
            event.currentTarget.value = '';
          }}
        />
      </div>
      <p className="muted">
        {t(
          'Select files to include in your next message. Uploading alone does not send them to Codex.',
        )}
      </p>
      <p className="muted">
        {t('All file types')} · {t('Per file')}:{' '}
        {fileSize(task.attachment_limits.file_bytes)} · {t('Storage')}:{' '}
        {fileSize(used)} / {fileSize(task.attachment_limits.task_bytes)}
      </p>
      {!task.attachments.length && (
        <div className="attachment-empty">
          <Upload size={24} />
          <p>{t('Drop files here or use Upload files.')}</p>
        </div>
      )}
      <div className="attachment-rows">
        {task.attachments.map((file) => (
          <div className="attachment-row" key={file.id}>
            <label>
              <input
                type="checkbox"
                checked={selectedIds.includes(file.id)}
                disabled={busy || task.status === 'uncertain'}
                onChange={() => onToggle(file.id)}
              />
              <span>
                <strong>{file.name}</strong>
                <small>{fileSize(file.size)}</small>
              </span>
            </label>
            <a
              className="attachment-action"
              href={attachmentDownload(task.id, file.id)}
              download
              aria-label={`${t('Download')}: ${file.name}`}
            >
              <Download size={15} />
            </a>
            <Button
              variant="ghost"
              size="icon"
              disabled={busy || locked(task)}
              aria-label={`${t('Delete file')}: ${file.name}`}
              onClick={() => onDelete(file.id)}
            >
              <Trash2 size={15} />
            </Button>
          </div>
        ))}
      </div>
      <p className="muted">
        {t(
          'Deselecting a file stops attaching it to new messages. Content already read may remain in the conversation.',
        )}
      </p>
    </section>
  );
}
