import { describe, expect, it } from 'vitest';

import {
  applyOrderedReorder,
  compareOrderedItemsByText,
  sortedOrderedSiblings,
  type OrderedReorderItem,
} from './ordered-reorder';

interface Row extends OrderedReorderItem {
  label: string;
}

function makeRow(
  overrides: Partial<Row> & Pick<Row, 'id' | 'label' | 'sort_order'>,
): Row {
  return { parent_id: null, ...overrides };
}

function compareRows(left: Row, right: Row): number {
  return compareOrderedItemsByText(left, right, (row) => row.label);
}

function makeRows(): Row[] {
  return [
    makeRow({ id: 'A', label: 'Alpha', sort_order: 0 }),
    makeRow({ id: 'B', label: 'Bravo', sort_order: 1000 }),
    makeRow({ id: 'C', label: 'Charlie', sort_order: 2000 }),
    makeRow({ id: 'B1', label: 'Bravo 1', sort_order: 0, parent_id: 'B' }),
    makeRow({ id: 'B2', label: 'Bravo 2', sort_order: 1000, parent_id: 'B' }),
  ];
}

function expectPresent<T>(value: T | null | undefined): T {
  expect(value).not.toBeNull();
  expect(value).not.toBeUndefined();
  return value as T;
}

describe('sortedOrderedSiblings', () => {
  it('filters by parent and applies the caller-provided comparator', () => {
    const rows = [
      makeRow({ id: 'B', label: 'Bravo', sort_order: 0, parent_id: 'parent' }),
      makeRow({ id: 'A', label: 'Alpha', sort_order: 0, parent_id: 'parent' }),
      makeRow({ id: 'C', label: 'Charlie', sort_order: 0, parent_id: 'other' }),
    ];

    expect(
      sortedOrderedSiblings(rows, 'parent', compareRows).map((row) => row.id),
    ).toEqual(['A', 'B']);
  });
});

describe('applyOrderedReorder', () => {
  it('moves an item within a parent and adjusts target indexes after removal', () => {
    const result = applyOrderedReorder(
      makeRows(),
      'A',
      { parentId: null, index: 2 },
      { compareItems: compareRows },
    );
    const next = expectPresent(result);

    expect(
      sortedOrderedSiblings(next.nextItems, null, compareRows).map(
        (row) => row.id,
      ),
    ).toEqual(['B', 'A', 'C']);
    expect(
      next.patches.map(
        (patch) => `${patch.id}:${patch.sort_order}:${patch.parent_changed}`,
      ),
    ).toEqual(['B:0:false', 'A:1000:false']);
  });

  it('returns null for a same-parent no-op drop', () => {
    expect(
      applyOrderedReorder(
        makeRows(),
        'A',
        { parentId: null, index: 0 },
        { compareItems: compareRows },
      ),
    ).toBeNull();
    expect(
      applyOrderedReorder(
        makeRows(),
        'A',
        { parentId: null, index: 1 },
        { compareItems: compareRows },
      ),
    ).toBeNull();
  });

  it('moves an item across parents and renumbers both touched buckets', () => {
    const result = applyOrderedReorder(
      makeRows(),
      'C',
      { parentId: 'B', index: 5 },
      { compareItems: compareRows },
    );
    const next = expectPresent(result);

    expect(
      sortedOrderedSiblings(next.nextItems, null, compareRows).map(
        (row) => row.id,
      ),
    ).toEqual(['A', 'B']);
    expect(
      sortedOrderedSiblings(next.nextItems, 'B', compareRows).map(
        (row) => row.id,
      ),
    ).toEqual(['B1', 'B2', 'C']);
    expect(next.patches).toEqual([
      { id: 'C', parent_id: 'B', sort_order: 2000, parent_changed: true },
    ]);
  });

  it('rejects cross-parent moves when disabled', () => {
    const result = applyOrderedReorder(
      makeRows(),
      'B1',
      { parentId: null, index: 1 },
      { compareItems: compareRows, allowCrossParent: false },
    );

    expect(result).toBeNull();
  });

  it('supports a custom sort step in the generated patches', () => {
    const result = applyOrderedReorder(
      makeRows(),
      'A',
      { parentId: null, index: 3 },
      { compareItems: compareRows, sortStep: 10 },
    );
    const next = expectPresent(result);

    expect(
      next.patches.map((patch) => `${patch.id}:${patch.sort_order}`),
    ).toEqual(['B:0', 'C:10', 'A:20']);
  });
});
