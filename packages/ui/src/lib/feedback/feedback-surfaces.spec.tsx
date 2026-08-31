// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ContentState } from '../data-display/content-state';
import { ContextNote } from './context-note';
import { FormMessage } from './form-message';
import { InlineNotice } from './inline-notice';
import { StatusSlot } from './status-slot';

afterEach(cleanup);

describe('feedback surfaces', () => {
  it('keeps a StatusSlot mounted at the same size', () => {
    const { rerender } = render(<StatusSlot message={null} size="compact" />);
    expect(screen.getByRole('status').getAttribute('data-state')).toBe('empty');
    rerender(
      <StatusSlot
        message="Connection restored"
        size="compact"
        tone="success"
      />,
    );
    expect(screen.getByRole('status').getAttribute('data-state')).toBe(
      'populated',
    );
  });

  it('supports an assertive status action', () => {
    const onClick = vi.fn();
    render(
      <StatusSlot
        action={{ label: 'Retry', onClick }}
        announce="assertive"
        message="Refresh failed"
        size="regular"
        tone="error"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('keeps a form message id and footprint before an error', () => {
    const { rerender } = render(
      <FormMessage id="name-message" message={null} variant="field" />,
    );
    expect(screen.getByRole('alert').id).toBe('name-message');
    rerender(
      <FormMessage
        id="name-message"
        message="Name is required"
        variant="field"
      />,
    );
    expect(screen.getByText('Name is required').id).toBe('name-message');
  });

  it('uses replacement semantics for blocking content errors', () => {
    render(
      <ContentState
        description="Try again later."
        kind="error"
        size="fill"
        title="Could not load records"
      />,
    );
    expect(screen.getByRole('alert')).toBeTruthy();
  });

  it('keeps static context notes out of live regions', () => {
    render(<ContextNote tone="warning">Store this key safely.</ContextNote>);
    const note = screen.getByText('Store this key safely.').parentElement
      ?.parentElement;
    expect(note?.getAttribute('role')).toBeNull();
  });

  it('uses accessible semantic warning colors for inline notices', () => {
    render(<InlineNotice tone="warning">Request access.</InlineNotice>);

    expect(
      screen.getByText('Request access.').parentElement?.className,
    ).toContain('text-[var(--ui-color-warning-text)]');
  });
});
