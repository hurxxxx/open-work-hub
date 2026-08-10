import { describe, expect, it } from 'vitest';
import type { WhiteboardHubItem } from '../api/whiteboard-api';
import {
  INITIAL_WHITEBOARD_PICKER_STATE,
  filterWhiteboardsForPicker,
  whiteboardPickerReducer,
} from './whiteboard-picker-model';

function whiteboard(id: string, title: string): WhiteboardHubItem {
  return {
    id,
    title,
  } as WhiteboardHubItem;
}

describe('whiteboard-picker-model', () => {
  it('tracks loading, failure, query, and submit state transitions', () => {
    const loading = whiteboardPickerReducer(INITIAL_WHITEBOARD_PICKER_STATE, {
      type: 'load',
    });
    expect(loading.loading).toBe(true);
    expect(loading.error).toBeNull();

    const loaded = whiteboardPickerReducer(loading, {
      type: 'loaded',
      items: [whiteboard('1', 'Planning board')],
    });
    expect(loaded.items).toHaveLength(1);
    expect(loaded.loading).toBe(false);

    const queried = whiteboardPickerReducer(loaded, {
      type: 'query',
      value: 'plan',
    });
    expect(queried.query).toBe('plan');

    const submitting = whiteboardPickerReducer(queried, {
      type: 'submit',
      itemId: '1',
    });
    expect(submitting.submittingId).toBe('1');
    expect(submitting.error).toBeNull();

    const failedSubmit = whiteboardPickerReducer(submitting, {
      type: 'submit-failed',
      message: 'Connect failed',
    });
    expect(failedSubmit.error).toBe('Connect failed');

    const finished = whiteboardPickerReducer(failedSubmit, {
      type: 'submit-finished',
    });
    expect(finished.submittingId).toBeNull();

    const failedLoad = whiteboardPickerReducer(loaded, {
      type: 'failed',
      message: 'Load failed',
    });
    expect(failedLoad.items).toEqual([]);
    expect(failedLoad.loading).toBe(false);
    expect(failedLoad.error).toBe('Load failed');
  });

  it('filters by excluded ids and query before applying the result limit', () => {
    const whiteboards = [
      whiteboard('1', 'Launch planning'),
      whiteboard('2', 'Launch review'),
      whiteboard('3', 'Operations sync'),
      whiteboard('4', 'Launch retro'),
    ];

    expect(
      filterWhiteboardsForPicker(whiteboards, {
        query: ' launch ',
        excludeWhiteboardIds: ['2'],
        limit: 2,
      }).map((item) => item.id),
    ).toEqual(['1', '4']);
  });

  it('preserves the input order for matching whiteboards', () => {
    const whiteboards = [
      whiteboard('old', 'Project map'),
      whiteboard('new', 'Project map'),
      whiteboard('middle', 'Project map'),
    ];

    expect(
      filterWhiteboardsForPicker(whiteboards, {
        query: 'project',
        excludeWhiteboardIds: [],
      }).map((item) => item.id),
    ).toEqual(['old', 'new', 'middle']);
  });

  it('returns the first matching whiteboards when query is blank', () => {
    const whiteboards = [
      whiteboard('1', 'One'),
      whiteboard('2', 'Two'),
      whiteboard('3', 'Three'),
    ];

    expect(
      filterWhiteboardsForPicker(whiteboards, {
        query: ' ',
        excludeWhiteboardIds: ['1'],
        limit: 2,
      }).map((item) => item.id),
    ).toEqual(['2', '3']);
  });

  it('uses a 50 item default limit', () => {
    const whiteboards = Array.from({ length: 55 }, (_, index) =>
      whiteboard(String(index + 1), `Board ${index + 1}`),
    );

    const filtered = filterWhiteboardsForPicker(whiteboards, {
      query: '',
      excludeWhiteboardIds: [],
    });

    expect(filtered).toHaveLength(50);
    expect(filtered.at(0)?.id).toBe('1');
    expect(filtered.at(-1)?.id).toBe('50');
  });
});
