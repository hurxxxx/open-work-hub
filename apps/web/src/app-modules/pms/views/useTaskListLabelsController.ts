import { useCallback, useState } from 'react';

import {
  createTaskListLabel,
  deleteLabel,
  updateLabel,
  type PmsLabel,
} from '../api/pms-api';
import { LABEL_PRESET_COLORS } from './pms-color-palettes';

export { LABEL_PRESET_COLORS } from './pms-color-palettes';

type LabelErrorMessages = {
  createFailed: string;
  deleteFailed: string;
  updateFailed: string;
};

type UseTaskListLabelsControllerParams = {
  errorMessages: LabelErrorMessages;
  onError: (message: string | null) => void;
  onLabelsChanged?: (labels: PmsLabel[]) => void;
  taskListId: string;
  token: string | null | undefined;
};

export function useTaskListLabelsController({
  errorMessages,
  onError,
  onLabelsChanged,
  taskListId,
  token,
}: UseTaskListLabelsControllerParams) {
  const [labels, setLabels] = useState<PmsLabel[]>([]);
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState(LABEL_PRESET_COLORS[0]);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editColor, setEditColor] = useState('');

  const replaceLabels = useCallback(
    (updated: PmsLabel[]) => {
      setLabels(updated);
      onLabelsChanged?.(updated);
    },
    [onLabelsChanged],
  );

  const handleCreate = useCallback(async () => {
    if (!token || !newName.trim()) return;
    setCreating(true);
    onError(null);
    try {
      const label = await createTaskListLabel(token, taskListId, {
        name: newName.trim(),
        color: newColor,
      });
      replaceLabels([...labels, label]);
      setNewName('');
      setNewColor(LABEL_PRESET_COLORS[0]);
    } catch (caughtError) {
      onError(
        caughtError instanceof Error
          ? caughtError.message
          : errorMessages.createFailed,
      );
    } finally {
      setCreating(false);
    }
  }, [
    errorMessages.createFailed,
    labels,
    newColor,
    newName,
    onError,
    replaceLabels,
    taskListId,
    token,
  ]);

  const startEdit = useCallback((label: PmsLabel) => {
    setEditingId(label.id);
    setEditName(label.name);
    setEditColor(label.color);
  }, []);

  const handleSaveEdit = useCallback(async () => {
    if (!token || !editingId || !editName.trim()) return;
    onError(null);
    try {
      const updatedLabel = await updateLabel(token, editingId, {
        name: editName.trim(),
        color: editColor,
      });
      replaceLabels(
        labels.map((label) => (label.id === editingId ? updatedLabel : label)),
      );
      setEditingId(null);
    } catch (caughtError) {
      onError(
        caughtError instanceof Error
          ? caughtError.message
          : errorMessages.updateFailed,
      );
    }
  }, [
    editColor,
    editName,
    editingId,
    errorMessages.updateFailed,
    labels,
    onError,
    replaceLabels,
    token,
  ]);

  const handleDelete = useCallback(
    async (labelId: string) => {
      if (!token) return;
      onError(null);
      try {
        await deleteLabel(token, labelId);
        replaceLabels(labels.filter((label) => label.id !== labelId));
      } catch (caughtError) {
        onError(
          caughtError instanceof Error
            ? caughtError.message
            : errorMessages.deleteFailed,
        );
      }
    },
    [errorMessages.deleteFailed, labels, onError, replaceLabels, token],
  );

  return {
    creating,
    editColor,
    editName,
    editingId,
    handleCreate,
    handleDelete,
    handleSaveEdit,
    labels,
    newColor,
    newName,
    replaceLabels,
    setEditColor,
    setEditName,
    setEditingId,
    setNewColor,
    setNewName,
    startEdit,
  };
}
