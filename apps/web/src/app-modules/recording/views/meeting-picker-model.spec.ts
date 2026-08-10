import { describe, expect, it } from 'vitest';
import type { MeetingListItem } from '@/src/app-modules/meeting/public-api';
import {
  INITIAL_MEETING_PICKER_STATE,
  filterMeetingsForPicker,
  meetingPickerReducer,
  sortMeetingsForPicker,
} from './meeting-picker-model';

function meeting(
  id: string,
  title: string,
  startAt = `2026-05-${id.padStart(2, '0')}T09:00:00Z`,
): MeetingListItem {
  return {
    id,
    title,
    start_at: startAt,
  } as MeetingListItem;
}

describe('meeting-picker-model', () => {
  it('tracks loading, failure, query, and submit state transitions', () => {
    const loading = meetingPickerReducer(INITIAL_MEETING_PICKER_STATE, {
      type: 'load',
    });
    expect(loading).toMatchObject({
      loading: true,
      query: '',
      submittingId: null,
      error: null,
    });

    const loaded = meetingPickerReducer(loading, {
      type: 'loaded',
      items: [meeting('1', 'Planning')],
    });
    expect(loaded.items).toHaveLength(1);
    expect(loaded.loading).toBe(false);

    const queried = meetingPickerReducer(loaded, {
      type: 'query',
      value: 'plan',
    });
    expect(queried.query).toBe('plan');

    const submitting = meetingPickerReducer(queried, {
      type: 'submit',
      meetingId: '1',
    });
    expect(submitting.submittingId).toBe('1');
    expect(submitting.error).toBeNull();

    const failedSubmit = meetingPickerReducer(submitting, {
      type: 'submit-failed',
      message: 'Attach failed',
    });
    expect(failedSubmit.error).toBe('Attach failed');

    const finished = meetingPickerReducer(failedSubmit, {
      type: 'submit-finished',
    });
    expect(finished.submittingId).toBeNull();

    const failedLoad = meetingPickerReducer(loaded, {
      type: 'failed',
      message: 'Load failed',
    });
    expect(failedLoad.items).toEqual([]);
    expect(failedLoad.loading).toBe(false);
    expect(failedLoad.error).toBe('Load failed');
  });

  it('sorts meetings newest first without mutating the original list', () => {
    const meetings = [
      meeting('old', 'Old', '2026-05-01T09:00:00Z'),
      meeting('new', 'New', '2026-05-03T09:00:00Z'),
      meeting('middle', 'Middle', '2026-05-02T09:00:00Z'),
    ];

    expect(sortMeetingsForPicker(meetings).map((item) => item.id)).toEqual([
      'new',
      'middle',
      'old',
    ]);
    expect(meetings.map((item) => item.id)).toEqual(['old', 'new', 'middle']);
  });

  it('filters by query and excluded meetings before applying the result limit', () => {
    const meetings = [
      meeting('1', 'Launch planning'),
      meeting('2', 'Launch review'),
      meeting('3', 'Operations sync'),
      meeting('4', 'Launch retro'),
    ];

    expect(
      filterMeetingsForPicker(meetings, {
        excludeMeetingIds: ['2'],
        query: ' launch ',
        limit: 2,
      }).map((item) => item.id),
    ).toEqual(['1', '4']);
  });

  it('returns the first matching meetings when query is blank', () => {
    const meetings = [meeting('1', 'One'), meeting('2', 'Two'), meeting('3', 'Three')];

    expect(
      filterMeetingsForPicker(meetings, {
        excludeMeetingIds: ['1'],
        query: ' ',
        limit: 1,
      }).map((item) => item.id),
    ).toEqual(['2']);
  });
});
