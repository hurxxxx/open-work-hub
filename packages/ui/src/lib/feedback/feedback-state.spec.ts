import { describe, expect, it, vi } from 'vitest';

import {
  createFeedbackRecord,
  dismissFeedback,
  EMPTY_FEEDBACK_QUEUE,
  enqueueFeedback,
  FEEDBACK_DURATION_MS,
  FEEDBACK_PENDING_LIMIT,
  FEEDBACK_VISIBLE_LIMIT,
  feedbackToneClass,
  type FeedbackInput,
  type FeedbackQueue,
} from './feedback-state';

function record(id: string, overrides: Partial<FeedbackInput> = {}) {
  return createFeedbackRecord(id, { title: id, tone: 'info', ...overrides });
}

function enqueueMany(count: number): FeedbackQueue {
  let queue = EMPTY_FEEDBACK_QUEUE;
  for (let index = 0; index < count; index += 1) {
    queue = enqueueFeedback(queue, record(`feedback-${index}`));
  }
  return queue;
}

describe('feedback state', () => {
  it('uses the shared passive duration and polite announcement by default', () => {
    expect(FEEDBACK_DURATION_MS).toBe(6000);
    expect(record('default').announcement).toBe('polite');
  });

  it('keeps three visible items and promotes pending feedback FIFO', () => {
    const queue = enqueueMany(FEEDBACK_VISIBLE_LIMIT + 2);
    expect(queue.visible.map((item) => item.id)).toEqual([
      'feedback-0',
      'feedback-1',
      'feedback-2',
    ]);
    expect(queue.pending.map((item) => item.id)).toEqual([
      'feedback-3',
      'feedback-4',
    ]);
    const next = dismissFeedback(queue, 'feedback-1');
    expect(next.visible.map((item) => item.id)).toEqual([
      'feedback-0',
      'feedback-2',
      'feedback-3',
    ]);
    expect(next.pending.map((item) => item.id)).toEqual(['feedback-4']);
  });

  it('replaces matching records without changing their position', () => {
    const queue = enqueueFeedback(
      enqueueFeedback(
        EMPTY_FEEDBACK_QUEUE,
        record('first', { dedupeKey: 'same' }),
      ),
      record('second', { dedupeKey: 'same' }),
    );
    expect(queue.visible.map((item) => item.id)).toEqual(['second']);
  });

  it('bounds pending feedback and drops the oldest pending item', () => {
    const queue = enqueueMany(
      FEEDBACK_VISIBLE_LIMIT + FEEDBACK_PENDING_LIMIT + 2,
    );
    expect(queue.pending).toHaveLength(FEEDBACK_PENDING_LIMIT);
    expect(queue.pending[0]?.id).toBe('feedback-5');
  });

  it('preserves action and announcement semantics', () => {
    const onAction = vi.fn();
    const feedback = createFeedbackRecord('action', {
      action: { altText: 'Undo the save', label: 'Undo', onAction },
      announcement: 'assertive',
      title: 'Saved',
      tone: 'success',
    });
    expect(feedback.action?.onAction).toBe(onAction);
    expect(feedbackToneClass('success')).toContain('var(--ui-color-success)');
    expect(feedbackToneClass('error')).toContain('var(--ui-color-danger)');
  });
});
