import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AccessibleMultiSelect } from './AccessibleMultiSelect';

function renderFilter(onChange = vi.fn()) {
  render(
    <AccessibleMultiSelect
      allLabel="All"
      buttonLabel={(summary) => `Department: ${summary}`}
      label="Department"
      noResultsLabel="No results"
      onChange={onChange}
      options={['Engineering', 'Operations']}
      searchLabel="Search departments"
      searchPlaceholder="Search"
      selected={[]}
      selectedText={(count) => `${count} selected`}
    />,
  );
  return onChange;
}

describe('AccessibleMultiSelect', () => {
  it('exposes its expanded state and toggles a native checkbox', () => {
    const onChange = renderFilter();
    const trigger = screen.getByRole('button', { name: 'Department: All' });

    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(screen.getByRole('checkbox', { name: 'Engineering' }));
    expect(onChange).toHaveBeenCalledWith(['Engineering']);
  });

  it('announces an empty search result', () => {
    renderFilter();
    fireEvent.click(screen.getByRole('button', { name: 'Department: All' }));
    fireEvent.change(
      screen.getByRole('searchbox', { name: 'Search departments' }),
      {
        target: { value: 'missing' },
      },
    );

    expect(screen.getByRole('status').textContent).toContain('No results');
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    renderFilter();
    const trigger = screen.getByRole('button', { name: 'Department: All' });
    fireEvent.click(trigger);

    const search = screen.getByRole('searchbox', {
      name: 'Search departments',
    });
    fireEvent.keyDown(search, { key: 'Escape' });

    await waitFor(() => expect(document.activeElement).toBe(trigger));
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });
});
