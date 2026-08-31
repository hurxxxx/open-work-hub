import { describe, expect, it } from 'vitest';

import type { MeetingListItem } from '../../api/meeting-api';
import {
  INITIAL_MEETING_LIST_VIEW_STATE,
  buildMeetingListRows,
  consumeMeetingCreateSearchParam,
  createMeetingTabSearchParams,
  meetingListViewReducer,
  resolveMeetingScope,
  resolveMeetingTab,
} from './meeting-list-view-model';

function item(id: string): MeetingListItem {
  return {
    id,
    title: `Meeting ${id}`,
  } as MeetingListItem;
}

function listItem(
  id: string,
  overrides: Partial<MeetingListItem> = {},
): MeetingListItem {
  return {
    attendee_count: 2,
    doc_link_count: 1,
    end_at: '2026-01-02T11:30:00',
    id,
    organizer_name: 'D. Kim',
    start_at: '2026-01-02T10:00:00',
    status: 'scheduled',
    task_link_count: 3,
    title: `Meeting ${id}`,
    ...overrides,
  } as MeetingListItem;
}

describe('meeting list view model', () => {
  it('resolves tabs and meeting scopes with upcoming as the fallback', () => {
    expect(resolveMeetingTab('mine')).toBe('mine');
    expect(resolveMeetingTab('recordings')).toBe('recordings');
    expect(resolveMeetingTab('unknown')).toBe('upcoming');
    expect(resolveMeetingTab(null)).toBe('upcoming');

    expect(resolveMeetingScope('upcoming')).toBe('upcoming');
    expect(resolveMeetingScope('mine')).toBe('mine');
    expect(resolveMeetingScope('recordings')).toBe('mine');
  });

  it('builds tab search params without interpreting unrelated params', () => {
    expect(
      createMeetingTabSearchParams({
        searchParams: new URLSearchParams('id=meeting-1&create=1'),
        tab: 'mine',
      }).toString(),
    ).toBe('id=meeting-1&create=1&tab=mine');
  });

  it('consumes create requests', () => {
    expect(
      consumeMeetingCreateSearchParam(
        new URLSearchParams('tab=mine&create=1'),
      )?.toString(),
    ).toBe('tab=mine');
    expect(
      consumeMeetingCreateSearchParam(new URLSearchParams('tab=mine')),
    ).toBeNull();
  });

  it('reduces load and create modal state', () => {
    const loading = meetingListViewReducer(INITIAL_MEETING_LIST_VIEW_STATE, {
      type: 'load-started',
    });
    const loaded = meetingListViewReducer(loading, {
      items: [item('meeting-1')],
      type: 'load-succeeded',
    });
    const opened = meetingListViewReducer(loaded, { type: 'create-opened' });
    const failed = meetingListViewReducer(opened, {
      error: 'Failed',
      type: 'load-failed',
    });

    expect(loading).toMatchObject({ error: null, loading: true });
    expect(loaded).toMatchObject({
      items: [item('meeting-1')],
      loading: false,
    });
    expect(opened.createOpen).toBe(true);
    expect(
      meetingListViewReducer(opened, { type: 'create-closed' }).createOpen,
    ).toBe(false);
    expect(failed).toMatchObject({
      createOpen: true,
      error: 'Failed',
      items: [],
      loading: false,
    });
  });

  it('projects sorted meeting list rows with active and status display state', () => {
    const rows = buildMeetingListRows({
      activeId: 'meeting-1',
      items: [
        listItem('meeting-2', {
          start_at: '2026-01-03T10:00:00',
          status: 'completed',
        }),
        listItem('meeting-1', {
          start_at: '2026-01-02T10:00:00',
          status: 'in_progress',
        }),
      ],
      locale: 'en-US',
      timeZone: 'UTC',
    });

    expect(rows.map((row) => row.item.id)).toEqual(['meeting-1', 'meeting-2']);
    expect(rows[0]).toMatchObject({
      isActive: true,
      statusClassName:
        'bg-[var(--ui-color-success)]/15 text-[var(--ui-color-success)]',
      statusLabelKey: 'meeting.inProgress',
    });
    expect(rows[0].timeRange).toContain('10:00');
    expect(rows[0].timeRange).toContain('11:30');
  });

  it('projects unknown meeting statuses with fallback copy and classes', () => {
    const [row] = buildMeetingListRows({
      activeId: null,
      items: [listItem('meeting-1', { status: 'paused' as never })],
      locale: 'en-US',
      timeZone: 'UTC',
    });

    expect(row.isActive).toBe(false);
    expect(row.statusLabelKey).toBeNull();
    expect(row.statusClassName).toBe(
      'bg-app-ink/10 text-app-ink/60 dark:text-app-ink/70',
    );
  });
});
