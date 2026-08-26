// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { FeedbackProvider, useFeedback } from './feedback-provider';

const labels = {
  close: 'Close feedback',
  item: 'Feedback',
  region: 'Feedback region ({hotkey})',
};

afterEach(cleanup);

function PassiveTrigger() {
  const feedback = useFeedback();
  return (
    <button
      onClick={() => feedback.success('Saved', 'The change was saved.')}
      type="button"
    >
      Show feedback
    </button>
  );
}

function ActionTrigger({ onAction }: { onAction: () => void }) {
  const feedback = useFeedback();
  return (
    <button
      onClick={() =>
        feedback.show({
          action: {
            altText: 'Undo the saved change',
            label: 'Undo',
            onAction,
          },
          title: 'Saved',
          tone: 'success',
        })
      }
      type="button"
    >
      Show actionable feedback
    </button>
  );
}

describe('FeedbackProvider', () => {
  it('uses localized labels and lets the user dismiss feedback', async () => {
    render(
      <FeedbackProvider labels={labels}>
        <PassiveTrigger />
      </FeedbackProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Show feedback' }));
    expect(screen.getByText('Saved')).toBeTruthy();
    expect(screen.getByLabelText('Feedback region (F8)')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Close feedback' }));
    await waitFor(() => expect(screen.queryByText('Saved')).toBeNull());
  });

  it('runs a localized action and dismisses its feedback', async () => {
    const onAction = vi.fn();
    render(
      <FeedbackProvider labels={labels}>
        <ActionTrigger onAction={onAction} />
      </FeedbackProvider>,
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Show actionable feedback' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(onAction).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByText('Saved')).toBeNull());
  });
});
