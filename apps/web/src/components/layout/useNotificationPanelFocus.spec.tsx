// @vitest-environment jsdom

import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  NOTIFICATION_PANEL_ID,
  useNotificationPanelFocus,
} from './useNotificationPanelFocus';

function NotificationPanelFocusHarness() {
  const [open, setOpen] = useState(false);
  const focus = useNotificationPanelFocus(open, () =>
    setOpen((value) => !value),
  );

  return (
    <>
      <button onClick={focus.onToggle} type="button">
        Notifications
      </button>
      {open ? (
        <div id={NOTIFICATION_PANEL_ID} tabIndex={-1}>
          <button onClick={focus.onClose} type="button">
            Close panel
          </button>
        </div>
      ) : null}
    </>
  );
}

describe('useNotificationPanelFocus', () => {
  it('moves focus into the panel when it opens', async () => {
    render(<NotificationPanelFocusHarness />);

    fireEvent.click(screen.getByRole('button', { name: 'Notifications' }));

    await waitFor(() =>
      expect(document.activeElement?.id).toBe(NOTIFICATION_PANEL_ID),
    );
  });

  it('restores focus to the trigger after the panel closes', async () => {
    render(<NotificationPanelFocusHarness />);
    const trigger = screen.getByRole('button', { name: 'Notifications' });

    fireEvent.click(trigger);
    const closeButton = screen.getByRole('button', { name: 'Close panel' });
    closeButton.focus();
    fireEvent.click(closeButton);

    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});
