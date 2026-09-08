import { describe, expect, it } from 'vitest';

import type {
  DocsHubItem,
  DocsPageItem,
} from '@/src/app-modules/docs/public-api';

import type { MeetingDetail } from '../../api/meeting-api';
import {
  MEETING_DETAIL_INITIAL_STATE,
  formatMeetingDetailRange,
  meetingDetailReducer,
  type MeetingDetailState,
} from './meeting-detail-layout-model';

function meeting(overrides: Partial<MeetingDetail> = {}): MeetingDetail {
  return {
    id: 'meeting-1',
    title: 'Planning',
    agenda: 'Roadmap',
    start_at: '2026-05-30T01:00:00',
    end_at: '2026-05-30T02:00:00',
    organizer_id: 'organizer',
    organizer_name: 'Organizer',
    notes_doc_id: 'doc-1',
    notes_page_id: 'page-1',
    attendees: [],
    task_links: [],
    doc_links: [],
    file_attachments: [],
    recordings: [],
    whiteboard_link: null,
    active_recording_lock: null,
    ...overrides,
  } as MeetingDetail;
}

function doc(overrides: Partial<DocsHubItem> = {}): DocsHubItem {
  return {
    id: 'doc-1',
    title: 'Meeting notes',
    page_count: 1,
    content_format: 'block',
    can_edit: true,
    ...overrides,
  } as DocsHubItem;
}

function page(overrides: Partial<DocsPageItem> = {}): DocsPageItem {
  return {
    id: 'page-1',
    doc_id: 'doc-1',
    title: 'Notes',
    parent_id: null,
    sort_order: 1000,
    depth: 0,
    content_format: 'block',
    content_blocks: [{ type: 'paragraph', text: 'Initial' }],
    content_text: null,
    source_type: 'docs_page',
    source_page_id: 'source-page-1',
    can_edit: true,
    trashed_at: null,
    created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
    ...overrides,
  } as DocsPageItem;
}

function loadedState(
  overrides: Partial<MeetingDetailState> = {},
): MeetingDetailState {
  return {
    ...MEETING_DETAIL_INITIAL_STATE,
    meeting: meeting(),
    notesDoc: doc(),
    notesPage: page(),
    loading: false,
    error: null,
    detailOpen: false,
    ...overrides,
  };
}

describe('meeting workspace layout model', () => {
  it('marks loads as in-flight and clears stale errors', () => {
    const state = meetingDetailReducer(
      loadedState({ error: 'Previous failure' }),
      { type: 'loadStarted' },
    );

    expect(state.loading).toBe(true);
    expect(state.error).toBeNull();
    expect(state.meeting?.id).toBe('meeting-1');
  });

  it('stores meeting detail and selected notes after a successful load', () => {
    const nextMeeting = meeting({ id: 'meeting-2', title: 'Review' });
    const nextDoc = doc({ id: 'doc-2', title: 'Review notes' });
    const nextPage = page({
      id: 'page-2',
      title: 'Summary',
      content_blocks: [{ type: 'heading', text: 'Action items' }],
    });

    const state = meetingDetailReducer(
      loadedState({
        detailOpen: true,
        error: 'Previous failure',
        loading: true,
      }),
      {
        type: 'loadSucceeded',
        meeting: nextMeeting,
        notesDoc: nextDoc,
        notesPage: nextPage,
      },
    );

    expect(state).toMatchObject({
      meeting: nextMeeting,
      notesDoc: nextDoc,
      notesPage: nextPage,
      loading: false,
      error: null,
      detailOpen: true,
    });
  });

  it('clears loaded data and stores the error after a failed load', () => {
    const state = meetingDetailReducer(loadedState({ loading: true }), {
      type: 'loadFailed',
      error: 'Unable to load workspace',
    });

    expect(state).toMatchObject({
      meeting: null,
      notesDoc: null,
      notesPage: null,
      loading: false,
      error: 'Unable to load workspace',
    });
  });

  it('updates the detail drawer state', () => {
    expect(
      meetingDetailReducer(loadedState(), {
        type: 'setDetailOpen',
        open: true,
      }).detailOpen,
    ).toBe(true);

    expect(
      meetingDetailReducer(loadedState({ detailOpen: true }), {
        type: 'setDetailOpen',
        open: false,
      }).detailOpen,
    ).toBe(false);
  });

  it('replaces the selected notes page', () => {
    const nextPage = page({ id: 'page-2', title: 'Follow-up notes' });
    const state = meetingDetailReducer(loadedState(), {
      type: 'setNotesPage',
      notesPage: nextPage,
    });

    expect(state.notesPage).toBe(nextPage);
  });

  it('does not update notes content when no page is selected', () => {
    const state = loadedState({ notesPage: null });
    const nextState = meetingDetailReducer(state, {
      type: 'updateNotesContent',
      content: [{ type: 'paragraph', text: 'Draft' }],
    });

    expect(nextState).toBe(state);
  });

  it('replaces the selected notes page content', () => {
    const state = loadedState();
    const content = [{ type: 'paragraph', text: 'Updated' }];
    const nextState = meetingDetailReducer(state, {
      type: 'updateNotesContent',
      content,
    });

    expect(nextState).not.toBe(state);
    expect(nextState.notesPage).not.toBe(state.notesPage);
    expect(nextState.notesPage?.content_blocks).toBe(content);
    expect(nextState.notesPage?.title).toBe('Notes');
  });

  it('formats the meeting workspace date range', () => {
    expect(
      formatMeetingDetailRange(
        '2026-05-30T01:00:00',
        '2026-05-30T02:30:00',
        'UTC',
        'en-US',
      ),
    ).toContain(' - 02:30 AM');
  });
});
