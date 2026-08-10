import { describe, expect, it } from 'vitest';

import type { BlockContent } from '@ai-do/ui';
import type { LearningPageNoteDetail } from '../../api/types';
import {
  EMPTY_NOTE_BLOCKS,
  LEARNING_NOTE_SAVED_FLASH_MS,
  NOTES_PANEL_INITIAL_STATE,
  authorInitials,
  canArchiveLearningPageNote,
  canCancelLearningNoteEdit,
  createLearningPageNoteUpsertPayload,
  editDraftFromNote,
  getLearningPageNoteActionErrorMessage,
  lockLearningPageNotesBodyScroll,
  notesPanelReducer,
  savedNoteContent,
} from './learning-page-notes-panel-model';
import { LearningNotesApiError } from '../../api/learning-notes-api';

function note(
  contentBlocks: BlockContent,
  visibility: LearningPageNoteDetail['visibility'] = 'public',
): LearningPageNoteDetail {
  return {
    content_blocks: contentBlocks as unknown[],
    visibility,
  } as LearningPageNoteDetail;
}

describe('learning page notes panel model', () => {
  it('starts editing from existing content or from an empty private draft', () => {
    const savedContent = [{ type: 'paragraph', content: [] }] as BlockContent;

    expect(
      editDraftFromNote({
        note: note(savedContent, 'public'),
        savedContent,
        startingFromExisting: true,
      }),
    ).toEqual({ content: savedContent, visibility: 'public' });

    expect(
      editDraftFromNote({
        note: null,
        savedContent,
        startingFromExisting: false,
      }),
    ).toEqual({ content: EMPTY_NOTE_BLOCKS, visibility: 'private' });
  });

  it('keeps reducer state transitions local to editor workflow', () => {
    const content = [{ type: 'paragraph', content: [] }] as BlockContent;
    const editing = notesPanelReducer(NOTES_PANEL_INITIAL_STATE, {
      type: 'enterEdit',
      content,
      visibility: 'public',
    });

    expect(editing).toMatchObject({
      mode: 'edit',
      draftBlocks: content,
      draftVisibility: 'public',
      actionError: null,
    });

    const expanded = notesPanelReducer(editing, { type: 'toggleExpanded' });
    expect(expanded.expanded).toBe(true);

    const saved = notesPanelReducer(expanded, { type: 'saveSuccess' });
    expect(saved).toMatchObject({
      mode: 'view',
      draftBlocks: EMPTY_NOTE_BLOCKS,
      flash: 'saved',
      actionError: null,
      expanded: false,
    });

    expect(notesPanelReducer(saved, { type: 'clearFlash' }).flash).toBeNull();
  });

  it('clears drafts and fullscreen state when editing is cancelled', () => {
    const dirtyExpanded = {
      ...NOTES_PANEL_INITIAL_STATE,
      mode: 'edit' as const,
      draftBlocks: [{ type: 'paragraph', content: [] }] as BlockContent,
      actionError: 'Save failed',
      expanded: true,
    };

    expect(notesPanelReducer(dirtyExpanded, { type: 'cancelEdit' })).toEqual({
      ...dirtyExpanded,
      mode: 'view',
      draftBlocks: EMPTY_NOTE_BLOCKS,
      actionError: null,
      expanded: false,
    });
  });

  it('derives saved content and author initials for compact rendering', () => {
    const saved = [{ type: 'paragraph', content: [] }] as BlockContent;

    expect(savedNoteContent(note(saved))).toBe(saved);
    expect(savedNoteContent(null)).toEqual([]);
    expect(authorInitials('')).toBe('·');
    expect(authorInitials('Ada Lovelace')).toBe('AL');
    expect(authorInitials('홍길동')).toBe('홍길');
  });

  it('keeps dirty cancel and archive confirmation policy in the model', () => {
    expect(
      canCancelLearningNoteEdit({
        confirmDiscard: () => {
          throw new Error('should not ask');
        },
        isDirty: false,
      }),
    ).toBe(true);
    expect(
      canCancelLearningNoteEdit({
        confirmDiscard: () => false,
        isDirty: true,
      }),
    ).toBe(false);

    expect(
      canArchiveLearningPageNote({
        confirmArchive: () => true,
        note: note([]),
      }),
    ).toBe(true);
    expect(
      canArchiveLearningPageNote({
        confirmArchive: () => true,
        note: null,
      }),
    ).toBe(false);
  });

  it('builds save payloads and maps action errors', () => {
    const contentBlocks = [{ type: 'paragraph', content: [] }] as BlockContent;

    expect(
      createLearningPageNoteUpsertPayload({
        contentBlocks,
        courseSlug: 'course-1',
        lessonId: 'lesson-1',
        lessonTitle: 'Intro',
        visibility: 'public',
      }),
    ).toEqual({
      content_blocks: contentBlocks,
      course_slug: 'course-1',
      lesson_id: 'lesson-1',
      lesson_title: 'Intro',
      visibility: 'public',
    });
    expect(
      getLearningPageNoteActionErrorMessage({
        caught: new LearningNotesApiError(500, 'Backend failed'),
        fallback: 'Fallback',
      }),
    ).toBe('Backend failed');
    expect(
      getLearningPageNoteActionErrorMessage({
        caught: new Error('Other'),
        fallback: 'Fallback',
      }),
    ).toBe('Fallback');
    expect(LEARNING_NOTE_SAVED_FLASH_MS).toBe(1800);
  });

  it('restores body scroll after fullscreen edit closes', () => {
    const bodyStyle = { overflow: 'auto' };
    const unlock = lockLearningPageNotesBodyScroll({ bodyStyle });

    expect(bodyStyle.overflow).toBe('hidden');
    unlock();
    expect(bodyStyle.overflow).toBe('auto');
  });
});
