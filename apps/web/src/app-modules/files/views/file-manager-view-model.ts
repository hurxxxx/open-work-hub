import { formatByteSize } from '@/src/platform/format/byte-size';
import { formatDateTime } from '@/src/platform/time/time-utils';

import type { FileItem, FileRagStatus } from '../api/files-api';

export const IMAGE_PREVIEW_ZOOM_MIN = 0.5;
export const IMAGE_PREVIEW_ZOOM_MAX = 4;
export const IMAGE_PREVIEW_ZOOM_STEP = 0.25;
export const FILE_RAG_POLL_INITIAL_DELAY_MS = 3000;
export const FILE_RAG_POLL_MAX_DELAY_MS = 30000;

export const FILE_RAG_STATUS_PRESENTATION: Record<
  FileRagStatus,
  { className: string; labelKey: string; processing: boolean }
> = {
  disabled: {
    className: 'border-app-border bg-app-surface-hover text-app-ink/55',
    labelKey: 'files.ragStatus.disabled',
    processing: false,
  },
  pending: {
    className:
      'border-app-warning-border bg-app-warning-bg text-app-warning-text',
    labelKey: 'files.ragStatus.pending',
    processing: true,
  },
  processing: {
    className:
      'border-app-warning-border bg-app-warning-bg text-app-warning-text',
    labelKey: 'files.ragStatus.processing',
    processing: true,
  },
  ready: {
    className:
      'border-app-success-border bg-app-success-bg text-app-success-text',
    labelKey: 'files.ragStatus.ready',
    processing: false,
  },
  unsupported: {
    className: 'border-app-border bg-app-surface-hover text-app-ink/55',
    labelKey: 'files.ragStatus.unsupported',
    processing: false,
  },
  failed: {
    className: 'border-app-danger-border bg-app-danger-bg text-app-danger-text',
    labelKey: 'files.ragStatus.failed',
    processing: false,
  },
};

export function shouldPollFileRagStatuses(files: FileItem[]): boolean {
  return files.some(
    (file) => file.rag_status === 'pending' || file.rag_status === 'processing',
  );
}

export function shouldDisplayFileRagStatus(status: FileRagStatus): boolean {
  return status !== 'disabled';
}

export function fileRagPollingSignature(files: FileItem[]): string {
  return files
    .filter(
      (file) =>
        file.rag_status === 'pending' || file.rag_status === 'processing',
    )
    .map(
      (file) =>
        `${file.id}:${file.rag_status}:${file.rag_updated_at ?? 'unknown'}`,
    )
    .join('|');
}

export function nextFileRagPollingDelay(
  currentDelayMs: number,
  succeeded: boolean,
): number {
  const multiplier = succeeded ? 1.5 : 2;
  return Math.min(
    Math.round(currentDelayMs * multiplier),
    FILE_RAG_POLL_MAX_DELAY_MS,
  );
}

export function isPreviewableImageFile(file: FileItem): boolean {
  return file.content_type
    .split(';', 1)[0]
    .trim()
    .toLowerCase()
    .startsWith('image/');
}

export function clampImagePreviewZoom(value: number): number {
  return Math.min(
    IMAGE_PREVIEW_ZOOM_MAX,
    Math.max(IMAGE_PREVIEW_ZOOM_MIN, value),
  );
}

export function formatFileSize(bytes: number): string {
  return formatByteSize(bytes, {
    fractionDigits: 'compact',
    units: ['KB', 'MB', 'GB', 'TB'],
  });
}

export function formatFileUpdatedAt(
  value: string,
  locale: string,
  timeZone: string,
): string {
  return formatDateTime(value, {
    dateStyle: 'medium',
    fallback: value,
    locale,
    timeStyle: 'short',
    timeZone,
  });
}
