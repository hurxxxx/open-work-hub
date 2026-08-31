import { useCallback, useState, type SetStateAction } from 'react';
import type { TFunction } from 'i18next';

import {
  createChecklistItem,
  deleteChecklistItem,
  updateChecklistItem,
  type PmsChecklistItem,
} from '../api/pms-api';
import {
  getTaskDetailMutationErrorMessage,
  notifyTaskDetailUpdated,
} from './task-detail-mutation';

type CreateChecklistItemPayload = Parameters<typeof createChecklistItem>[2];

export function buildTaskDetailChecklistItemPayload({
  sortOrder,
  text,
}: {
  sortOrder: number;
  text: string;
}): CreateChecklistItemPayload {
  return {
    sort_order: sortOrder,
    text: text.trim(),
  };
}

export function getTaskDetailChecklistProgress(
  checklistItems: Pick<PmsChecklistItem, 'completed'>[],
): { done: number; total: number } {
  return {
    done: checklistItems.filter((item) => item.completed).length,
    total: checklistItems.length,
  };
}

export function useTaskDetailChecklist({
  canEdit,
  checklistItems,
  onUpdate,
  setChecklistItems,
  setSaveError,
  taskId,
  token,
  t,
  workspaceSlug,
}: {
  canEdit: boolean;
  checklistItems: PmsChecklistItem[];
  onUpdate?: () => void | Promise<void>;
  setChecklistItems: (value: SetStateAction<PmsChecklistItem[]>) => void;
  setSaveError: (message: string | null) => void;
  taskId: string;
  token: string | null;
  t: TFunction;
  workspaceSlug: string;
}) {
  const [newChecklistText, setNewChecklistText] = useState('');
  const [addingChecklist, setAddingChecklist] = useState(false);
  const [editingChecklistId, setEditingChecklistId] = useState<string | null>(
    null,
  );
  const [editingChecklistText, setEditingChecklistText] = useState('');
  const checklistProgress = getTaskDetailChecklistProgress(checklistItems);

  const handleAddChecklistItem = useCallback(async () => {
    if (!token || !canEdit || !workspaceSlug || !newChecklistText.trim())
      return;
    setAddingChecklist(true);
    setSaveError(null);
    try {
      const item = await createChecklistItem(
        token,
        taskId,
        buildTaskDetailChecklistItemPayload({
          sortOrder: checklistItems.length,
          text: newChecklistText,
        }),
        workspaceSlug,
      );
      setChecklistItems((prev) => [...prev, item]);
      setNewChecklistText('');
      await notifyTaskDetailUpdated(onUpdate);
    } catch (error) {
      setSaveError(
        getTaskDetailMutationErrorMessage(
          error,
          t('pms.taskDetail.errors.addChecklistFailed'),
        ),
      );
    } finally {
      setAddingChecklist(false);
    }
  }, [
    canEdit,
    checklistItems.length,
    newChecklistText,
    onUpdate,
    setChecklistItems,
    setSaveError,
    t,
    taskId,
    token,
    workspaceSlug,
  ]);

  const handleToggleChecklistItem = useCallback(
    async (item: PmsChecklistItem) => {
      if (!token || !canEdit || !workspaceSlug) return;
      const newCompleted = !item.completed;
      setChecklistItems((prev) =>
        prev.map((checklistItem) =>
          checklistItem.id === item.id
            ? { ...checklistItem, completed: newCompleted }
            : checklistItem,
        ),
      );
      try {
        await updateChecklistItem(
          token,
          item.id,
          { completed: newCompleted },
          workspaceSlug,
        );
        await notifyTaskDetailUpdated(onUpdate);
      } catch (error) {
        setChecklistItems((prev) =>
          prev.map((checklistItem) =>
            checklistItem.id === item.id
              ? { ...checklistItem, completed: !newCompleted }
              : checklistItem,
          ),
        );
        setSaveError(
          getTaskDetailMutationErrorMessage(
            error,
            t('pms.taskDetail.errors.updateChecklistFailed'),
          ),
        );
      }
    },
    [
      canEdit,
      onUpdate,
      setChecklistItems,
      setSaveError,
      t,
      token,
      workspaceSlug,
    ],
  );

  const handleSaveChecklistEdit = useCallback(
    async (itemId: string) => {
      if (!token || !canEdit || !workspaceSlug || !editingChecklistText.trim())
        return;
      try {
        await updateChecklistItem(
          token,
          itemId,
          {
            text: editingChecklistText.trim(),
          },
          workspaceSlug,
        );
        setChecklistItems((prev) =>
          prev.map((checklistItem) =>
            checklistItem.id === itemId
              ? { ...checklistItem, text: editingChecklistText.trim() }
              : checklistItem,
          ),
        );
        setEditingChecklistId(null);
      } catch (error) {
        setSaveError(
          getTaskDetailMutationErrorMessage(
            error,
            t('pms.taskDetail.errors.editChecklistFailed'),
          ),
        );
      }
    },
    [
      canEdit,
      editingChecklistText,
      setChecklistItems,
      setSaveError,
      t,
      token,
      workspaceSlug,
    ],
  );

  const handleDeleteChecklistItem = useCallback(
    async (itemId: string) => {
      if (!token || !canEdit || !workspaceSlug) return;
      try {
        await deleteChecklistItem(token, itemId, workspaceSlug);
        setChecklistItems((prev) =>
          prev.filter((checklistItem) => checklistItem.id !== itemId),
        );
        await notifyTaskDetailUpdated(onUpdate);
      } catch (error) {
        setSaveError(
          getTaskDetailMutationErrorMessage(
            error,
            t('pms.taskDetail.errors.deleteChecklistFailed'),
          ),
        );
      }
    },
    [
      canEdit,
      onUpdate,
      setChecklistItems,
      setSaveError,
      t,
      token,
      workspaceSlug,
    ],
  );

  return {
    addingChecklist,
    checklistDone: checklistProgress.done,
    checklistTotal: checklistProgress.total,
    editingChecklistId,
    editingChecklistText,
    handleAddChecklistItem,
    handleDeleteChecklistItem,
    handleSaveChecklistEdit,
    handleToggleChecklistItem,
    newChecklistText,
    setEditingChecklistId,
    setEditingChecklistText,
    setNewChecklistText,
  };
}
