import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ToastProvider, ToastViewport, useToast } from './toast-provider';

function ToastTrigger() {
  const toast = useToast();

  return (
    <button
      type="button"
      onClick={() => toast.success('Saved', 'The change was saved.')}
    >
      Show toast
    </button>
  );
}

describe('ToastProvider', () => {
  it('lets the user immediately dismiss a visible toast', async () => {
    render(
      <ToastProvider closeLabel="Close notification">
        <ToastTrigger />
        <ToastViewport />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Show toast' }));

    expect(screen.getByText('Saved')).toBeTruthy();
    const closeButton = screen.getByRole('button', {
      name: 'Close notification',
    });
    expect(closeButton.getAttribute('title')).toBe('Close notification');

    fireEvent.click(closeButton);

    await waitFor(() => expect(screen.queryByText('Saved')).toBeNull());
  });
});
