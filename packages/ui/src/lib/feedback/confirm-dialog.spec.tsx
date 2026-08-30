import { useRef, useState } from 'react';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { ConfirmDialog } from './confirm-dialog';

afterEach(cleanup);

describe('ConfirmDialog', () => {
  it('restores focus to the control that opened a conditionally mounted dialog', async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Open confirmation
          </button>
          {open ? (
            <ConfirmDialog
              cancelLabel="Cancel"
              confirmLabel="Confirm"
              description="Confirm the action"
              onCancel={() => setOpen(false)}
              onConfirm={() => setOpen(false)}
              open
              title="Confirmation"
            />
          ) : null}
        </>
      );
    }

    render(<Harness />);
    const trigger = screen.getByRole('button', { name: 'Open confirmation' });
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it('uses an explicit return target when the menu item that opened it unmounts', async () => {
    function MenuHarness() {
      const [menuOpen, setMenuOpen] = useState(false);
      const [dialogOpen, setDialogOpen] = useState(false);
      const actionButtonRef = useRef<HTMLButtonElement | null>(null);
      return (
        <>
          <button
            ref={actionButtonRef}
            type="button"
            onClick={() => setMenuOpen(true)}
          >
            Member actions
          </button>
          {menuOpen ? (
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                setDialogOpen(true);
              }}
            >
              Remove member
            </button>
          ) : null}
          {dialogOpen ? (
            <ConfirmDialog
              cancelLabel="Cancel"
              confirmLabel="Remove"
              description="Remove this member"
              onCancel={() => setDialogOpen(false)}
              onConfirm={() => setDialogOpen(false)}
              open
              returnFocusRef={actionButtonRef}
              title="Remove member"
              variant="danger"
            />
          ) : null}
        </>
      );
    }

    render(<MenuHarness />);
    const actionButton = screen.getByRole('button', {
      name: 'Member actions',
    });
    fireEvent.click(actionButton);
    const menuItem = screen.getByRole('button', { name: 'Remove member' });
    menuItem.focus();
    fireEvent.click(menuItem);

    const confirmButton = await screen.findByRole('button', { name: 'Remove' });
    expect(confirmButton.className).toContain('bg-ui-danger-bg');
    expect(confirmButton.className).toContain('text-ui-danger-text');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(document.activeElement).toBe(actionButton));
  });
});
