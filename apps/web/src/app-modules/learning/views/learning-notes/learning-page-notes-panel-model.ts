import type { BlockContent } from '@open-alm/ui';

import { formatRelativeTime } from '@/src/platform/time/time-utils';
import { LearningNotesApiError } from '../../api/learning-notes-api';
import type {
  LearningPageNoteDetail,
  LearningPageNoteUpsertPayload,
  LearningPageNoteVisibility,
} from '../../api/types';

export type MyEditorMode = 'view' | 'edit';

export const EMPTY_NOTE_BLOCKS: BlockContent = [];
export const LEARNING_NOTE_SAVED_FLASH_MS = 1800;

export type NotesPanelState = {
  mode: MyEditorMode;
  draftBlocks: BlockContent;
  draftVisibility: LearningPageNoteVisibility;
  flash: 'saved' | null;
  actionError: string | null;
  expanded: boolean;
};

export type NotesPanelAction =
  | {
      type: 'enterEdit';
      content: BlockContent;
      visibility: LearningPageNoteVisibility;
    }
  | { type: 'cancelEdit' }
  | { type: 'draftChanged'; content: BlockContent }
  | { type: 'visibilityChanged'; visibility: LearningPageNoteVisibility }
  | { type: 'clearActionError' }
  | { type: 'saveSuccess' }
  | { type: 'clearFlash' }
  | { type: 'actionError'; message: string }
  | { type: 'toggleExpanded' };

export const NOTES_PANEL_INITIAL_STATE: NotesPanelState = {
  mode: 'view',
  draftBlocks: EMPTY_NOTE_BLOCKS,
  draftVisibility: 'private',
  flash: null,
  actionError: null,
  expanded: false,
};

export function notesPanelReducer(
  state: NotesPanelState,
  action: NotesPanelAction,
): NotesPanelState {
  switch (action.type) {
    case 'enterEdit':
      return {
        ...state,
        mode: 'edit',
        draftBlocks: action.content,
        draftVisibility: action.visibility,
        actionError: null,
      };
    case 'cancelEdit':
      return {
        ...state,
        mode: 'view',
        draftBlocks: EMPTY_NOTE_BLOCKS,
        actionError: null,
        expanded: false,
      };
    case 'draftChanged':
      return { ...state, draftBlocks: action.content };
    case 'visibilityChanged':
      return { ...state, draftVisibility: action.visibility };
    case 'clearActionError':
      return { ...state, actionError: null };
    case 'saveSuccess':
      return {
        ...state,
        mode: 'view',
        draftBlocks: EMPTY_NOTE_BLOCKS,
        flash: 'saved',
        actionError: null,
        expanded: false,
      };
    case 'clearFlash':
      return { ...state, flash: null };
    case 'actionError':
      return { ...state, actionError: action.message };
    case 'toggleExpanded':
      return { ...state, expanded: !state.expanded };
  }
}

export function savedNoteContent(
  note: LearningPageNoteDetail | null,
): BlockContent {
  return (note?.content_blocks ?? []) as BlockContent;
}

export function editDraftFromNote({
  note,
  savedContent,
  startingFromExisting,
}: {
  note: LearningPageNoteDetail | null;
  savedContent: BlockContent;
  startingFromExisting: boolean;
}): Pick<
  Extract<NotesPanelAction, { type: 'enterEdit' }>,
  'content' | 'visibility'
> {
  return {
    content: startingFromExisting ? savedContent : EMPTY_NOTE_BLOCKS,
    visibility: note?.visibility ?? 'private',
  };
}

export function canCancelLearningNoteEdit({
  confirmDiscard,
  isDirty,
}: {
  confirmDiscard: () => boolean;
  isDirty: boolean;
}): boolean {
  return !isDirty || confirmDiscard();
}

export function canArchiveLearningPageNote({
  confirmArchive,
  note,
}: {
  confirmArchive: () => boolean;
  note: LearningPageNoteDetail | null;
}): boolean {
  return Boolean(note) && confirmArchive();
}

export function createLearningPageNoteUpsertPayload({
  contentBlocks,
  courseSlug,
  lessonId,
  lessonTitle,
  visibility,
}: {
  contentBlocks: BlockContent;
  courseSlug: string;
  lessonId: string;
  lessonTitle: string;
  visibility: LearningPageNoteVisibility;
}): LearningPageNoteUpsertPayload {
  return {
    content_blocks: contentBlocks as unknown[],
    course_slug: courseSlug,
    lesson_id: lessonId,
    lesson_title: lessonTitle,
    visibility,
  };
}

export function getLearningPageNoteActionErrorMessage({
  caught,
  fallback,
}: {
  caught: unknown;
  fallback: string;
}): string {
  return caught instanceof LearningNotesApiError ? caught.message : fallback;
}

export function lockLearningPageNotesBodyScroll({
  bodyStyle,
}: {
  bodyStyle: Pick<CSSStyleDeclaration, 'overflow'>;
}): () => void {
  const previous = bodyStyle.overflow;
  bodyStyle.overflow = 'hidden';
  return () => {
    bodyStyle.overflow = previous;
  };
}

export function formatLearningNoteRelativeTime({
  iso,
  locale,
  timeZone,
}: {
  iso: string;
  locale: string;
  timeZone: string;
}): string {
  return formatRelativeTime(iso, { locale, timeZone });
}

export function authorInitials(name: string): string {
  const trimmed = (name || '').trim();
  if (!trimmed) return '·';
  const parts = trimmed.split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] ?? '') + (parts[1][0] ?? '');
  }
  return trimmed.slice(0, 2);
}
