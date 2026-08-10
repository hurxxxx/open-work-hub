import { describe, expect, it } from 'vitest';

import type { FileItem } from '../api/files-api';
import {
  clampImagePreviewZoom,
  FILE_RAG_STATUS_PRESENTATION,
  fileRagPollingSignature,
  formatFileSize,
  isPreviewableImageFile,
  nextFileRagPollingDelay,
  shouldDisplayFileRagStatus,
  shouldPollFileRagStatuses,
} from './file-manager-view-model';

function file(contentType: string): FileItem {
  return {
    id: 'file-1',
    folder_id: null,
    filename: 'file',
    content_type: contentType,
    size_bytes: 1024,
    visibility: 'workspace',
    owner_id: 'owner',
    owner_name: 'Owner',
    can_delete: true,
    rag_status: 'ready',
    rag_updated_at: '2026-05-30T00:00:00Z',
    created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
  };
}

describe('file manager view model', () => {
  it('detects previewable image content types with parameters', () => {
    expect(isPreviewableImageFile(file('image/png; charset=binary'))).toBe(
      true,
    );
    expect(isPreviewableImageFile(file('IMAGE/JPEG'))).toBe(true);
    expect(isPreviewableImageFile(file('application/pdf'))).toBe(false);
  });

  it('clamps image preview zoom to the supported range', () => {
    expect(clampImagePreviewZoom(0.1)).toBe(0.5);
    expect(clampImagePreviewZoom(1.75)).toBe(1.75);
    expect(clampImagePreviewZoom(9)).toBe(4);
  });

  it('formats file sizes across byte units', () => {
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(1023)).toBe('1023 B');
    expect(formatFileSize(1024)).toBe('1.0 KB');
    expect(formatFileSize(1536)).toBe('1.5 KB');
    expect(formatFileSize(12 * 1024)).toBe('12 KB');
    expect(formatFileSize(1024 * 1024)).toBe('1.0 MB');
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MB');
    expect(formatFileSize(1024 ** 4)).toBe('1.0 TB');
  });

  it('maps every RAG status to a localized presentation', () => {
    expect(Object.keys(FILE_RAG_STATUS_PRESENTATION).sort()).toEqual([
      'disabled',
      'failed',
      'pending',
      'processing',
      'ready',
      'unsupported',
    ]);
    expect(FILE_RAG_STATUS_PRESENTATION.ready.labelKey).toBe(
      'files.ragStatus.ready',
    );
    expect(FILE_RAG_STATUS_PRESENTATION.failed.processing).toBe(false);
  });

  it('polls only while at least one RAG status is non-terminal', () => {
    const item = file('text/plain');
    expect(
      shouldPollFileRagStatuses([{ ...item, rag_status: 'pending' }]),
    ).toBe(true);
    expect(
      shouldPollFileRagStatuses([{ ...item, rag_status: 'processing' }]),
    ).toBe(true);
    expect(
      shouldPollFileRagStatuses([
        { ...item, rag_status: 'ready' },
        { ...item, id: 'file-2', rag_status: 'unsupported' },
        { ...item, id: 'file-3', rag_status: 'failed' },
      ]),
    ).toBe(false);
  });

  it('hides the RAG property when the server capability is disabled', () => {
    expect(shouldDisplayFileRagStatus('disabled')).toBe(false);
    expect(shouldDisplayFileRagStatus('ready')).toBe(true);
  });

  it('backs off unchanged polling and resets when the status signature changes', () => {
    const item = file('text/plain');
    const pending = { ...item, rag_status: 'pending' as const };
    const processing = {
      ...item,
      rag_status: 'processing' as const,
      rag_updated_at: '2026-05-30T00:01:00Z',
    };

    expect(fileRagPollingSignature([pending])).not.toBe(
      fileRagPollingSignature([processing]),
    );
    expect(nextFileRagPollingDelay(3000, true)).toBe(4500);
    expect(nextFileRagPollingDelay(4500, false)).toBe(9000);
    expect(nextFileRagPollingDelay(25000, false)).toBe(30000);
  });
});
