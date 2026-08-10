import { describe, expect, it } from 'vitest';

import {
  buildTaskDetailChecklistItemPayload,
  getTaskDetailChecklistProgress,
} from './useTaskDetailChecklist';

describe('task detail checklist helpers', () => {
  it('builds a trimmed create payload with the current sort order', () => {
    expect(
      buildTaskDetailChecklistItemPayload({
        sortOrder: 3,
        text: '  Confirm rollout  ',
      }),
    ).toEqual({
      sort_order: 3,
      text: 'Confirm rollout',
    });
  });

  it('counts completed checklist items', () => {
    expect(
      getTaskDetailChecklistProgress([
        { completed: true },
        { completed: false },
        { completed: true },
      ]),
    ).toEqual({ done: 2, total: 3 });
  });
});
