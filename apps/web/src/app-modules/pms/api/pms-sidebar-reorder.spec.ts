import { describe, expect, it } from 'vitest';

import {
  applyFlatReorder,
  computeFlatDropTarget,
  resolveFlatDropZone,
  sortedSiblings,
  type ReorderableItem,
} from './pms-sidebar-reorder';

type Row = ReorderableItem;

function makeRow(overrides: Partial<Row> & Pick<Row, 'id' | 'name' | 'sort_order'>): Row {
  return { parent_id: null, ...overrides };
}

function makeFolders(): Row[] {
  return [
    makeRow({ id: 'F-A', name: 'Alpha', sort_order: 0 }),
    makeRow({ id: 'F-B', name: 'Bravo', sort_order: 1000 }),
    makeRow({ id: 'F-C', name: 'Charlie', sort_order: 2000 }),
  ];
}

function makeListsAcrossFolders(): Row[] {
  return [
    makeRow({ id: 'L-1', name: 'List 1', sort_order: 0, parent_id: 'F-A' }),
    makeRow({ id: 'L-2', name: 'List 2', sort_order: 1000, parent_id: 'F-A' }),
    makeRow({ id: 'L-3', name: 'List 3', sort_order: 0, parent_id: 'F-B' }),
  ];
}

function expectPresent<T>(value: T | null | undefined): T {
  expect(value).not.toBeNull();
  expect(value).not.toBeUndefined();
  return value as T;
}

describe('resolveFlatDropZone', () => {
  const rect = { top: 100, height: 40 };
  it('returns before for upper half', () => {
    expect(resolveFlatDropZone(110, rect)).toBe('before');
  });
  it('returns after for lower half', () => {
    expect(resolveFlatDropZone(130, rect)).toBe('after');
  });
});

describe('sortedSiblings', () => {
  it('filters by parent and sorts by sort_order then name', () => {
    const items = makeListsAcrossFolders();
    expect(sortedSiblings(items, 'F-A').map((row) => row.id)).toEqual(['L-1', 'L-2']);
    expect(sortedSiblings(items, 'F-B').map((row) => row.id)).toEqual(['L-3']);
  });
});

describe('computeFlatDropTarget', () => {
  it('resolves before/after to insert index in same parent', () => {
    const items = makeFolders();
    expect(computeFlatDropTarget(items, 'F-B', 'before')).toEqual({ parentId: null, index: 1, zone: 'before' });
    expect(computeFlatDropTarget(items, 'F-B', 'after')).toEqual({ parentId: null, index: 2, zone: 'after' });
  });
});

describe('applyFlatReorder — sibling reorder', () => {
  it('moves folder A below B without skipping to the last slot', () => {
    const items = makeFolders();
    const target = computeFlatDropTarget(items, 'F-B', 'after');
    expect(target).not.toBeNull();
    const result = applyFlatReorder(items, 'F-A', expectPresent(target));
    expect(result).not.toBeNull();
    const next = expectPresent(result);
    expect(sortedSiblings(next.nextItems, null).map((row) => row.id)).toEqual(['F-B', 'F-A', 'F-C']);
    expect(next.patches.map((patch) => `${patch.id}:${patch.sort_order}`)).toEqual(['F-B:0', 'F-A:1000']);
  });

  it('moves folder A below C at root', () => {
    const items = makeFolders();
    const result = applyFlatReorder(items, 'F-A', { parentId: null, index: 3, zone: 'after' });
    expect(result).not.toBeNull();
    const next = expectPresent(result);
    expect(sortedSiblings(next.nextItems, null).map((row) => row.id)).toEqual(['F-B', 'F-C', 'F-A']);
    // A lands at index 2 → sort_order 2000; B drops to 0; C drops to 1000
    const patchA = expectPresent(next.patches.find((p) => p.id === 'F-A'));
    expect(patchA.parent_changed).toBe(false);
    expect(patchA.sort_order).toBe(2000);
  });

  it('is a no-op when dropping on original slot', () => {
    const items = makeFolders();
    expect(applyFlatReorder(items, 'F-A', { parentId: null, index: 0, zone: 'before' })).toBeNull();
    expect(applyFlatReorder(items, 'F-A', { parentId: null, index: 1, zone: 'after' })).toBeNull();
    expect(applyFlatReorder(items, 'F-B', { parentId: null, index: 2, zone: 'before' })).toBeNull();
  });
});

describe('applyFlatReorder — cross-parent move', () => {
  it('moves a list from folder A into folder B', () => {
    const items = makeListsAcrossFolders();
    const result = applyFlatReorder(items, 'L-1', { parentId: 'F-B', index: 1, zone: 'after' });
    expect(result).not.toBeNull();
    const next = expectPresent(result);
    expect(sortedSiblings(next.nextItems, 'F-A').map((row) => row.id)).toEqual(['L-2']);
    expect(sortedSiblings(next.nextItems, 'F-B').map((row) => row.id)).toEqual(['L-3', 'L-1']);
    const patchL1 = expectPresent(next.patches.find((p) => p.id === 'L-1'));
    expect(patchL1.parent_changed).toBe(true);
    expect(patchL1.parent_id).toBe('F-B');
    expect(patchL1.sort_order).toBe(1000);
  });

  it('rejects cross-parent move when allowCrossParent is false', () => {
    const items = makeListsAcrossFolders();
    const result = applyFlatReorder(
      items,
      'L-1',
      { parentId: 'F-B', index: 0, zone: 'before' },
      { allowCrossParent: false },
    );
    expect(result).toBeNull();
  });

  it('moves a list to root (parent_id null)', () => {
    const items = makeListsAcrossFolders();
    const result = applyFlatReorder(items, 'L-2', { parentId: null, index: 0, zone: 'before' });
    expect(result).not.toBeNull();
    const next = expectPresent(result);
    const patchL2 = expectPresent(next.patches.find((p) => p.id === 'L-2'));
    expect(patchL2.parent_changed).toBe(true);
    expect(patchL2.parent_id).toBeNull();
  });
});
