import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BlockContent } from '@open-work-hub/ui';

import type { LearningPageNoteDetail } from '../../api/types';
import { useLearningPageNotesController } from './useLearningPageNotesController';

const mocks = vi.hoisted(() => ({
  archive: vi.fn(),
  listRefresh: vi.fn(),
  upsert: vi.fn(),
  useList: vi.fn(),
  useMine: vi.fn(),
}));

vi.mock('../../api/learning-notes-hooks', () => ({
  useLearningPageNotesList: mocks.useList,
  useMyLearningPageNote: mocks.useMine,
}));

function note(contentBlocks: BlockContent = []): LearningPageNoteDetail {
  return {
    doc_id: 'note-1',
    content_blocks: contentBlocks as unknown[],
    visibility: 'public',
  } as LearningPageNoteDetail;
}

function renderController() {
  return renderHook(() =>
    useLearningPageNotesController({
      token: 'token',
      courseSlug: 'course-1',
      lessonId: 'lesson-1',
      lessonTitle: 'Lesson 1',
      timeZone: 'Asia/Seoul',
    }),
  );
}

describe('useLearningPageNotesController', () => {
  beforeEach(() => {
    mocks.archive.mockReset();
    mocks.listRefresh.mockReset();
    mocks.upsert.mockReset();
    mocks.useList.mockReset();
    mocks.useMine.mockReset();
    mocks.useList.mockReturnValue({
      status: 'ready',
      items: [],
      myNote: null,
      othersNotes: [],
      error: null,
      refresh: mocks.listRefresh,
    });
    mocks.useMine.mockReturnValue({
      status: 'ready',
      note: null,
      error: null,
      saving: false,
      refresh: vi.fn(),
      upsert: mocks.upsert,
      archive: mocks.archive,
      restore: vi.fn(),
    });
  });

  it('enters edit mode, saves a draft, clears dirty state, and refreshes the list', async () => {
    const saved = note();
    mocks.upsert.mockResolvedValue(saved);
    const { result } = renderController();
    const draft = [{ type: 'paragraph', content: [] }] as BlockContent;

    act(() => {
      result.current.actions.enterEditMode(false);
      result.current.actions.onDraftChange(draft);
      result.current.actions.onVisibilityChange('public');
    });
    await act(async () => {
      await result.current.actions.saveDraft();
    });

    expect(mocks.upsert).toHaveBeenCalledWith({
      content_blocks: draft,
      course_slug: 'course-1',
      lesson_id: 'lesson-1',
      lesson_title: 'Lesson 1',
      visibility: 'public',
    });
    expect(mocks.listRefresh).toHaveBeenCalledTimes(1);
    expect(result.current.panelState.mode).toBe('view');
    expect(result.current.panelState.flash).toBe('saved');
  });

  it('asks before cancelling dirty edits and keeps editing when discard is rejected', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { result } = renderController();

    act(() => {
      result.current.actions.enterEditMode(false);
      result.current.actions.onDraftChange([{ type: 'paragraph', content: [] }] as BlockContent);
      result.current.actions.cancelEdit();
    });

    expect(confirm).toHaveBeenCalled();
    expect(result.current.panelState.mode).toBe('edit');
    confirm.mockRestore();
  });

  it('archives the current note after confirmation and refreshes the list', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    mocks.archive.mockResolvedValue(note());
    mocks.useMine.mockReturnValue({
      status: 'ready',
      note: note(),
      error: null,
      saving: false,
      refresh: vi.fn(),
      upsert: mocks.upsert,
      archive: mocks.archive,
      restore: vi.fn(),
    });
    const { result } = renderController();

    await act(async () => {
      await result.current.actions.archiveMine();
    });

    expect(mocks.archive).toHaveBeenCalledWith('note-1');
    expect(mocks.listRefresh).toHaveBeenCalledTimes(1);
    confirm.mockRestore();
  });
});
