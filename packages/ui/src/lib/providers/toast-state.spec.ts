import { describe, expect, it } from 'vitest';

import {
  appendToastRecord,
  createToastRecord,
  dismissToastRecord,
  toastToneClass,
  type ToastRecord,
} from './toast-state';

describe('toast state', () => {
  it('creates and appends toast records without mutating the current list', () => {
    const current: ToastRecord[] = [
      createToastRecord({
        id: 'info-1',
        title: 'Existing',
        tone: 'info',
      }),
    ];
    const nextToast = createToastRecord({
      id: 'success-2',
      title: 'Saved',
      description: 'Changes persisted',
      tone: 'success',
    });

    const next = appendToastRecord(current, nextToast);

    expect(current).toHaveLength(1);
    expect(next).toEqual([
      {
        id: 'info-1',
        title: 'Existing',
        tone: 'info',
      },
      {
        id: 'success-2',
        title: 'Saved',
        description: 'Changes persisted',
        tone: 'success',
      },
    ]);
  });

  it('dismisses matching toast records by id', () => {
    const first = createToastRecord({
      id: 'first',
      title: 'First',
      tone: 'info',
    });
    const second = createToastRecord({
      id: 'second',
      title: 'Second',
      tone: 'error',
    });

    expect(dismissToastRecord([first, second], 'first')).toEqual([second]);
    expect(dismissToastRecord([first, second], 'missing')).toEqual([
      first,
      second,
    ]);
  });

  it('projects tone-specific class names', () => {
    expect(toastToneClass('info')).toContain('bg-ui-surface-raised');
    expect(toastToneClass('success')).toContain('var(--ui-color-success)');
    expect(toastToneClass('error')).toContain('var(--ui-color-danger)');
  });
});
