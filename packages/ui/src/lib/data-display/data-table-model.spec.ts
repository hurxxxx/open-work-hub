import { describe, expect, it } from 'vitest';

import {
  getDataTableRowPadding,
  getDataTableSortIndicator,
  isDataTableRowSelected,
  shouldActivateDataTableRowKey,
} from './data-table-model';

describe('data table model', () => {
  it('projects density into stable row padding classes', () => {
    expect(getDataTableRowPadding('dense')).toContain('px-3');
    expect(getDataTableRowPadding('comfortable')).toContain('px-4');
  });

  it('resolves selected rows with the configured row id accessor', () => {
    const row = { id: 'row-1', label: 'First' };

    expect(
      isDataTableRowSelected(row, {
        selectedRowId: 'row-1',
        getRowId: (item) => item.id,
      }),
    ).toBe(true);
    expect(
      isDataTableRowSelected(row, {
        selectedRowId: 'row-2',
        getRowId: (item) => item.id,
      }),
    ).toBe(false);
    expect(isDataTableRowSelected(row, { selectedRowId: 'row-1' })).toBe(false);
  });

  it('projects sortable header indicators', () => {
    expect(getDataTableSortIndicator('asc')).toBe(' ↑');
    expect(getDataTableSortIndicator('desc')).toBe(' ↓');
    expect(getDataTableSortIndicator(false)).toBe('');
  });

  it('activates row keyboard actions only for enter and space', () => {
    expect(shouldActivateDataTableRowKey('Enter')).toBe(true);
    expect(shouldActivateDataTableRowKey(' ')).toBe(true);
    expect(shouldActivateDataTableRowKey('Escape')).toBe(false);
  });
});
