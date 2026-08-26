// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { DetailDrawer } from './detail-drawer';

function ExternalTriggerDrawer() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open drawer
      </button>
      <DetailDrawer
        closeLabel="Close drawer"
        onOpenChange={setOpen}
        open={open}
        title="Details"
      >
        <button type="button">Drawer action</button>
      </DetailDrawer>
    </>
  );
}

describe('DetailDrawer focus restoration', () => {
  it('returns focus to an external trigger after Escape', async () => {
    render(<ExternalTriggerDrawer />);
    const trigger = screen.getByRole('button', { name: 'Open drawer' });
    trigger.focus();
    fireEvent.click(trigger);
    await screen.findByRole('dialog', { name: 'Details' });
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Details' })).toBeNull(),
    );
    expect(document.activeElement).toBe(trigger);
  });
});
