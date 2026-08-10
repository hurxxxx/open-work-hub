import { describe, expect, it } from 'vitest';

import {
  createInitialPickerState,
  pickerReducer,
  projectPickerItems,
} from './picker-model';

type Item = {
  id: string;
  title: string;
};

function item(id: string, title = `Item ${id}`): Item {
  return { id, title };
}

describe('picker-model', () => {
  it('tracks generic picker load, query, submit, failure, and reset transitions', () => {
    const initialState = createInitialPickerState<Item>();
    const dirtyState = {
      ...initialState,
      items: [item('old')],
      query: 'old',
      submittingId: 'old',
      error: 'Old error',
    };

    expect(
      pickerReducer(dirtyState, { type: 'load', resetQuery: true }, initialState),
    ).toEqual({
      ...dirtyState,
      query: '',
      loading: true,
      submittingId: null,
      error: null,
    });

    const loaded = pickerReducer(initialState, {
      type: 'loaded',
      items: [item('one')],
    }, initialState);
    expect(loaded).toMatchObject({ items: [item('one')], loading: false });

    const queried = pickerReducer(loaded, {
      type: 'query',
      value: 'first',
    }, initialState);
    expect(queried.query).toBe('first');

    const submitting = pickerReducer(queried, {
      type: 'submit',
      itemId: 'one',
    }, initialState);
    expect(submitting).toMatchObject({ submittingId: 'one', error: null });

    expect(
      pickerReducer(submitting, {
        type: 'submit-failed',
        message: 'Attach failed',
      }, initialState),
    ).toMatchObject({ submittingId: null, error: 'Attach failed' });

    expect(
      pickerReducer(submitting, {
        type: 'submit-failed',
        clearSubmitting: false,
        message: 'Attach failed',
      }, initialState),
    ).toMatchObject({ submittingId: 'one', error: 'Attach failed' });

    expect(pickerReducer(dirtyState, { type: 'reset' }, initialState)).toBe(
      initialState,
    );
  });

  it('projects items by exclusion, normalized query, and limit in input order', () => {
    const items = [
      item('excluded', 'Launch planning'),
      item('one', 'Launch planning'),
      item('two', 'Operations sync'),
      item('three', 'LAUNCH review'),
    ];

    expect(
      projectPickerItems({
        items,
        excludeIds: ['excluded'],
        getItemId: (candidate) => candidate.id,
        limit: 2,
        matchesQuery: (candidate, query) =>
          candidate.title.toLowerCase().includes(query),
        query: ' launch ',
      }),
    ).toEqual([items[1], items[3]]);
  });

  it('supports projection without local query filtering', () => {
    const items = [
      item('excluded', 'Launch planning'),
      item('one', 'Operations sync'),
      item('two', 'Roadmap'),
    ];

    expect(
      projectPickerItems({
        items,
        excludeIds: ['excluded'],
        getItemId: (candidate) => candidate.id,
        limit: 2,
        query: 'launch',
      }),
    ).toEqual([items[1], items[2]]);
  });
});
