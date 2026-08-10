import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import type { BlockContent } from '@open-alm/ui';
import { useTranslation } from 'react-i18next';

import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  useLearningPageNotesList,
  useMyLearningPageNote,
} from '../../api/learning-notes-hooks';
import type { LearningPageNoteVisibility } from '../../api/types';
import {
  NOTES_PANEL_INITIAL_STATE,
  LEARNING_NOTE_SAVED_FLASH_MS,
  canArchiveLearningPageNote,
  canCancelLearningNoteEdit,
  createLearningPageNoteUpsertPayload,
  editDraftFromNote,
  getLearningPageNoteActionErrorMessage,
  lockLearningPageNotesBodyScroll,
  notesPanelReducer,
  savedNoteContent,
} from './learning-page-notes-panel-model';

export interface UseLearningPageNotesControllerOptions {
  token: string | null;
  courseSlug: string;
  lessonId: string;
  lessonTitle: string;
  timeZone?: string | null;
}

export function useLearningPageNotesController({
  token,
  courseSlug,
  lessonId,
  lessonTitle,
  timeZone,
}: UseLearningPageNotesControllerOptions) {
  const { t } = useTranslation('apps');
  const resolvedTimeZone = normalizeTimeZone(timeZone);
  const list = useLearningPageNotesList(token, courseSlug, lessonId);
  const mine = useMyLearningPageNote(token, courseSlug, lessonId);
  const [panelState, dispatchPanel] = useReducer(
    notesPanelReducer,
    NOTES_PANEL_INITIAL_STATE,
  );
  const draftDirtyRef = useRef(false);
  const flashTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!panelState.expanded || typeof document === 'undefined') return;
    return lockLearningPageNotesBodyScroll({
      bodyStyle: document.body.style,
    });
  }, [panelState.expanded]);

  useEffect(
    () => () => {
      if (flashTimerRef.current !== null) {
        window.clearTimeout(flashTimerRef.current);
      }
    },
    [],
  );

  const savedContent = useMemo<BlockContent>(
    () => savedNoteContent(mine.note),
    [mine.note],
  );

  const enterEditMode = useCallback(
    (startingFromExisting: boolean) => {
      draftDirtyRef.current = false;
      dispatchPanel({
        type: 'enterEdit',
        ...editDraftFromNote({
          note: mine.note,
          savedContent,
          startingFromExisting,
        }),
      });
    },
    [mine.note, savedContent],
  );

  const cancelEdit = useCallback(() => {
    if (
      !canCancelLearningNoteEdit({
        confirmDiscard: () =>
          typeof window !== 'undefined'
            ? window.confirm(t('learning.notesPanel.cancelDirtyConfirm'))
            : true,
        isDirty: draftDirtyRef.current,
      })
    ) {
      return;
    }
    draftDirtyRef.current = false;
    dispatchPanel({ type: 'cancelEdit' });
  }, [t]);

  const saveDraft = useCallback(async () => {
    dispatchPanel({ type: 'clearActionError' });
    try {
      await mine.upsert(
        createLearningPageNoteUpsertPayload({
          contentBlocks: panelState.draftBlocks,
          courseSlug,
          lessonId,
          lessonTitle,
          visibility: panelState.draftVisibility,
        }),
      );
      draftDirtyRef.current = false;
      dispatchPanel({ type: 'saveSuccess' });
      if (flashTimerRef.current !== null) {
        window.clearTimeout(flashTimerRef.current);
      }
      flashTimerRef.current = window.setTimeout(
        () => dispatchPanel({ type: 'clearFlash' }),
        LEARNING_NOTE_SAVED_FLASH_MS,
      );
      list.refresh();
    } catch (caught) {
      dispatchPanel({
        type: 'actionError',
        message: getLearningPageNoteActionErrorMessage({
          caught,
          fallback: t('learning.notesPanel.saveFailed'),
        }),
      });
    }
  }, [
    courseSlug,
    lessonId,
    lessonTitle,
    list,
    mine,
    panelState.draftBlocks,
    panelState.draftVisibility,
    t,
  ]);

  const archiveMine = useCallback(async () => {
    const note = mine.note;
    if (
      !note ||
      !canArchiveLearningPageNote({
        confirmArchive: () =>
          typeof window !== 'undefined'
            ? window.confirm(t('learning.notesPanel.archiveConfirm'))
            : true,
        note,
      })
    ) {
      return;
    }
    try {
      await mine.archive(note.doc_id);
      list.refresh();
    } catch (caught) {
      dispatchPanel({
        type: 'actionError',
        message: getLearningPageNoteActionErrorMessage({
          caught,
          fallback: t('learning.notesPanel.archiveFailed'),
        }),
      });
    }
  }, [list, mine, t]);

  const onDraftChange = useCallback((content: BlockContent) => {
    dispatchPanel({ type: 'draftChanged', content });
    draftDirtyRef.current = true;
  }, []);

  const onVisibilityChange = useCallback(
    (visibility: LearningPageNoteVisibility) => {
      dispatchPanel({ type: 'visibilityChanged', visibility });
      draftDirtyRef.current = true;
    },
    [],
  );

  return {
    panelState,
    savedContent,
    resolvedTimeZone,
    list,
    mine,
    busy: list.status === 'loading' || mine.status === 'loading',
    actions: {
      archiveMine,
      cancelEdit,
      enterEditMode,
      onDraftChange,
      onVisibilityChange,
      saveDraft,
      toggleExpanded: () => dispatchPanel({ type: 'toggleExpanded' }),
    },
  };
}
