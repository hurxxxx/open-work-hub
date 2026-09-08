import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';

import { Dialog } from './dialog';

afterEach(cleanup);

function ExternalTriggerDialog({ conditional }: { conditional: boolean }) {
  const [open, setOpen] = useState(false);
  const dialog = (
    <Dialog
      actions={<button onClick={() => setOpen(false)}>Cancel</button>}
      closeLabel="Close form"
      onOpenChange={setOpen}
      open={open}
      title="Create resource"
    >
      <input aria-label="Name" />
    </Dialog>
  );

  return (
    <>
      <button onClick={() => setOpen(true)}>Open form</button>
      <button onClick={() => setOpen(true)}>Another form trigger</button>
      {conditional && !open ? null : dialog}
    </>
  );
}

describe('Dialog external trigger focus', () => {
  for (const conditional of [false, true]) {
    it.each(['Escape', 'Close form', 'Cancel'])(
      `returns focus after %s with conditional mounting ${conditional}`,
      async (action) => {
        render(<ExternalTriggerDialog conditional={conditional} />);
        const trigger = screen.getByRole('button', { name: 'Open form' });
        trigger.focus();
        fireEvent.click(trigger);
        const dialog = await screen.findByRole('dialog', {
          name: 'Create resource',
        });
        expect(dialog.contains(document.activeElement)).toBe(true);

        if (action === 'Escape') {
          fireEvent.keyDown(document, { key: 'Escape' });
        } else {
          fireEvent.click(screen.getByRole('button', { name: action }));
        }

        await waitFor(() => {
          expect(screen.queryByRole('dialog')).toBeNull();
          expect(document.activeElement).toBe(trigger);
        });
      },
    );
  }

  it('returns to the current trigger after reopening from another control', async () => {
    render(<ExternalTriggerDialog conditional={false} />);

    for (const name of ['Open form', 'Another form trigger']) {
      const trigger = screen.getByRole('button', { name });
      trigger.focus();
      fireEvent.click(trigger);
      await screen.findByRole('dialog');
      fireEvent.keyDown(document, { key: 'Escape' });
      await waitFor(() => expect(document.activeElement).toBe(trigger));
    }
  });
});
