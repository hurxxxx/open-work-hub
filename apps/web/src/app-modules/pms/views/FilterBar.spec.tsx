import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { createDefaultIssueFilterParams } from '../api/pms-filters';
import { FilterBar } from './FilterBar';

describe('FilterBar', () => {
  it('opens mobile filters in a drawer and applies selected values', () => {
    const setFilterParams = vi.fn();
    const filterParams = createDefaultIssueFilterParams();

    render(
      <FilterBar
        taskListId="list-1"
        filterParams={filterParams}
        setFilterParams={setFilterParams}
        members={[]}
        milestones={[]}
        labels={[]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /필터/ }));

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('필터')).toBeTruthy();

    fireEvent.click(within(dialog).getByRole('button', { name: '우선순위' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '높음' }));

    expect(setFilterParams).toHaveBeenCalledWith({
      ...filterParams,
      priority: 'high',
    });
  });
});
