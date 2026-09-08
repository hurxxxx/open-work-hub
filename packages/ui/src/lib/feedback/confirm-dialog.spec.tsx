import { useRef, useState } from 'react';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Dialog } from '../primitives/dialog';
import { ConfirmDialog, useConfirm } from './confirm-dialog';

afterEach(cleanup);

describe('ConfirmDialog', () => {
  it.each(['Cancel', 'Escape'])(
    'keeps an underlying form open and restores its pending action after %s',
    async (action) => {
      function NestedHarness() {
        const [open, setOpen] = useState(true);
        const [saving, setSaving] = useState(false);
        const { confirm, confirmDialog } = useConfirm();
        const save = async () => {
          setSaving(true);
          try {
            const result = confirm({
              title: 'Confirm removal',
              description: 'This changes access immediately.',
              confirmLabel: 'Remove',
              cancelLabel: 'Cancel',
            });
            // Chromium blurs an action when the pending render disables it.
            // jsdom does not, so reproduce that focus loss before portal mount.
            if (document.activeElement instanceof HTMLElement) {
              document.activeElement.blur();
            }
            await result;
          } finally {
            setSaving(false);
          }
        };
        return (
          <>
            <Dialog
              closeLabel="Close editor"
              onOpenChange={(nextOpen) => {
                if (!saving) setOpen(nextOpen);
              }}
              open={open}
              title="Edit members"
            >
              <input aria-label="Member" defaultValue="Kept draft" />
              <button disabled={saving} onClick={() => void save()}>
                Save members
              </button>
            </Dialog>
            {confirmDialog}
          </>
        );
      }

      render(<NestedHarness />);
      const save = screen.getByRole('button', { name: 'Save members' });
      save.focus();
      fireEvent.click(save);
      const confirmation = await screen.findByRole('dialog', {
        name: 'Confirm removal',
      });
      expect(confirmation.className).toContain(
        'z-[var(--ui-z-dialog-elevated)]',
      );
      if (action === 'Escape') {
        fireEvent.keyDown(document, { key: 'Escape' });
      } else {
        const cancel = screen.getByRole('button', { name: 'Cancel' });
        fireEvent.pointerDown(cancel, { pointerType: 'mouse' });
        fireEvent.pointerUp(cancel, { pointerType: 'mouse' });
        fireEvent.click(cancel);
      }

      await waitFor(() => {
        expect(
          screen.queryByRole('dialog', { name: 'Confirm removal' }),
        ).toBeNull();
        expect(
          screen.getByRole('dialog', { name: 'Edit members' }),
        ).toBeTruthy();
        expect(document.activeElement).toBe(save);
      });
      expect(
        (screen.getByRole('textbox', { name: 'Member' }) as HTMLInputElement)
          .value,
      ).toBe('Kept draft');
    },
  );

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
