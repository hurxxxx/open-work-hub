import { useCallback, useState, type SetStateAction } from 'react';
import type { TFunction } from 'i18next';

import { formatByteSize } from '@/src/platform/format/byte-size';

import {
  deleteAttachment,
  uploadAttachment,
  type PmsAttachment,
} from '../api/pms-api';
import {
  getTaskDetailMutationErrorMessage,
  notifyTaskDetailUpdated,
} from './task-detail-mutation';

export function formatTaskDetailAttachmentSize(sizeBytes: number): string {
  return formatByteSize(sizeBytes);
}

export function useTaskDetailAttachments({
  canEdit,
  onUpdate,
  setAttachments,
  setSaveError,
  taskId,
  token,
  t,
  workspaceSlug,
}: {
  canEdit: boolean;
  onUpdate?: () => void | Promise<void>;
  setAttachments: (value: SetStateAction<PmsAttachment[]>) => void;
  setSaveError: (message: string | null) => void;
  taskId: string;
  token: string | null;
  t: TFunction;
  workspaceSlug: string;
}) {
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleFileUpload = useCallback(
    async (files: FileList | File[]) => {
      if (!token || !canEdit || !workspaceSlug) return;
      setUploading(true);
      setSaveError(null);
      try {
        const uploadedAttachments = await Promise.all(
          Array.from(files).map((file) =>
            uploadAttachment(token, taskId, file, workspaceSlug),
          ),
        );
        setAttachments((prev) => [...prev, ...uploadedAttachments]);
        await notifyTaskDetailUpdated(onUpdate);
      } catch (error) {
        setSaveError(
          getTaskDetailMutationErrorMessage(
            error,
            t('pms.taskDetail.errors.uploadFileFailed'),
          ),
        );
      } finally {
        setUploading(false);
        setDragOver(false);
      }
    },
    [
      canEdit,
      onUpdate,
      setAttachments,
      setSaveError,
      t,
      taskId,
      token,
      workspaceSlug,
    ],
  );

  const handleDeleteAttachment = useCallback(
    async (attachmentId: string) => {
      if (!token || !canEdit || !workspaceSlug) return;
      setSaveError(null);
      try {
        await deleteAttachment(token, attachmentId, workspaceSlug);
        setAttachments((prev) =>
          prev.filter((attachment) => attachment.id !== attachmentId),
        );
        await notifyTaskDetailUpdated(onUpdate);
      } catch (error) {
        setSaveError(
          getTaskDetailMutationErrorMessage(
            error,
            t('pms.taskDetail.errors.deleteAttachmentFailed'),
          ),
        );
      }
    },
    [canEdit, onUpdate, setAttachments, setSaveError, t, token, workspaceSlug],
  );

  return {
    dragOver,
    formatAttachmentSize: formatTaskDetailAttachmentSize,
    handleDeleteAttachment,
    handleFileUpload,
    setDragOver,
    uploading,
  };
}
