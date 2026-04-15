import { describe, expect, it } from 'vitest';

import type { DocsPageItem } from './docs-api';
import {
  applyReorder,
  collectDescendantIds,
  computeDropTarget,
  flattenVisibleTree,
  resolveDropZone,
  sortedChildren,
} from './docs-page-reorder';

function makePage(overrides: Partial<DocsPageItem> & Pick<DocsPageItem, 'id' | 'sort_order' | 'title'>): DocsPageItem {
  return {
    doc_id: 'doc-1',
    source_type: 'native_doc_page',
    source_page_id: overrides.id,
    parent_id: null,
    content_blocks: null,
    created_by_id: 'user-1',
    created_by_name: 'Tester',
    created_at: '2026-04-14T00:00:00',
    updated_at: '2026-04-14T00:00:00',
    trashed_at: null,
    can_edit: true,
    realtime_collab: false,
    ...overrides,
  };
}

function makeTree(): DocsPageItem[] {
  return [
    makePage({ id: 'A', title: 'Alpha', sort_order: 0 }),
    makePage({ id: 'B', title: 'Bravo', sort_order: 1000 }),
    makePage({ id: 'C', title: 'Charlie', sort_order: 2000 }),
    makePage({ id: 'B1', title: 'Bravo-1', sort_order: 0, parent_id: 'B' }),
    makePage({ id: 'B2', title: 'Bravo-2', sort_order: 1000, parent_id: 'B' }),
  ];
}

describe('resolveDropZone', () => {
  const rect = { top: 100, height: 40 };
  it('returns before when pointer near top', () => {
    expect(resolveDropZone(104, rect)).toBe('before');
  });
  it('returns inside when pointer in middle', () => {
    expect(resolveDropZone(120, rect)).toBe('inside');
  });
  it('returns after when pointer near bottom', () => {
    expect(resolveDropZone(138, rect)).toBe('after');
  });
});

describe('sortedChildren', () => {
  it('returns siblings under a parent sorted by sort_order', () => {
    const pages = makeTree();
    expect(sortedChildren(pages, 'B').map((p) => p.id)).toEqual(['B1', 'B2']);
    expect(sortedChildren(pages, null).map((p) => p.id)).toEqual(['A', 'B', 'C']);
  });
});

describe('collectDescendantIds', () => {
  it('collects node and all nested descendants', () => {
    const pages = [
      ...makeTree(),
      makePage({ id: 'B1a', title: 'Bravo-1-a', sort_order: 0, parent_id: 'B1' }),
    ];
    const ids = collectDescendantIds(pages, 'B');
    expect(Array.from(ids).sort()).toEqual(['B', 'B1', 'B1a', 'B2']);
  });
});

describe('flattenVisibleTree', () => {
  it('omits children under collapsed parents', () => {
    const pages = makeTree();
    const flat = flattenVisibleTree(pages, new Set());
    expect(flat.map((node) => node.id)).toEqual(['A', 'B', 'C']);
  });
  it('includes children under expanded parents', () => {
    const pages = makeTree();
    const flat = flattenVisibleTree(pages, new Set(['B']));
    expect(flat.map((node) => node.id)).toEqual(['A', 'B', 'B1', 'B2', 'C']);
    expect(flat.find((node) => node.id === 'B1')?.depth).toBe(1);
  });
});

describe('computeDropTarget', () => {
  it('maps before to insert at overIndex of same parent', () => {
    const pages = makeTree();
    expect(computeDropTarget(pages, 'C', 'before')).toEqual({ parentId: null, index: 2, zone: 'before' });
  });
  it('maps after to insert at overIndex + 1 of same parent', () => {
    const pages = makeTree();
    expect(computeDropTarget(pages, 'A', 'after')).toEqual({ parentId: null, index: 1, zone: 'after' });
  });
  it('maps inside to append into that node', () => {
    const pages = makeTree();
    expect(computeDropTarget(pages, 'B', 'inside')).toEqual({ parentId: 'B', index: 2, zone: 'inside' });
  });
});

describe('applyReorder — sibling reorder within same parent', () => {
  it('moves A below B without skipping to the last sibling slot', () => {
    const pages = makeTree();
    const result = applyReorder(pages, 'A', { parentId: null, index: 2, zone: 'after' });
    expect(result).not.toBeNull();
    const roots = sortedChildren(result!.nextPages, null).map((p) => p.id);
    expect(roots).toEqual(['B', 'A', 'C']);
    expect(result!.patches.map((patch) => `${patch.id}:${patch.sort_order}`)).toEqual(['B:0', 'A:1000']);
  });

  it('moves A after C at root', () => {
    const pages = makeTree();
    const result = applyReorder(pages, 'A', { parentId: null, index: 3, zone: 'after' });
    expect(result).not.toBeNull();
    const roots = sortedChildren(result!.nextPages, null).map((p) => p.id);
    expect(roots).toEqual(['B', 'C', 'A']);
    // A moves to index 2 → 2000, B drops to 0, C drops to 1000
    const patchIds = result!.patches.map((patch) => patch.id).sort();
    expect(patchIds).toEqual(['A', 'B', 'C'].sort());
    const patchA = result!.patches.find((p) => p.id === 'A')!;
    expect(patchA.parent_changed).toBe(false);
    expect(patchA.sort_order).toBe(2000);
  });

  it('is a no-op when dropping on original slot', () => {
    const pages = makeTree();
    // A is at index 0 in root; dropping "before A" (index 0) is a no-op
    expect(applyReorder(pages, 'A', { parentId: null, index: 0, zone: 'before' })).toBeNull();
    // "after A" (index 1) is also a no-op
    expect(applyReorder(pages, 'A', { parentId: null, index: 1, zone: 'after' })).toBeNull();
  });
});

describe('applyReorder — move to new parent', () => {
  it('nests C inside B and renumbers both parents', () => {
    const pages = makeTree();
    const result = applyReorder(pages, 'C', { parentId: 'B', index: 2, zone: 'inside' });
    expect(result).not.toBeNull();
    const bChildren = sortedChildren(result!.nextPages, 'B').map((p) => p.id);
    expect(bChildren).toEqual(['B1', 'B2', 'C']);
    const rootIds = sortedChildren(result!.nextPages, null).map((p) => p.id);
    expect(rootIds).toEqual(['A', 'B']);
    const patchC = result!.patches.find((p) => p.id === 'C')!;
    expect(patchC.parent_changed).toBe(true);
    expect(patchC.parent_id).toBe('B');
    expect(patchC.sort_order).toBe(2000);
  });

  it('moves B1 to root between A and B', () => {
    const pages = makeTree();
    const result = applyReorder(pages, 'B1', { parentId: null, index: 1, zone: 'before' });
    expect(result).not.toBeNull();
    const rootIds = sortedChildren(result!.nextPages, null).map((p) => p.id);
    expect(rootIds).toEqual(['A', 'B1', 'B', 'C']);
    const bChildren = sortedChildren(result!.nextPages, 'B').map((p) => p.id);
    expect(bChildren).toEqual(['B2']);
    const patchB1 = result!.patches.find((p) => p.id === 'B1')!;
    expect(patchB1.parent_changed).toBe(true);
    expect(patchB1.parent_id).toBeNull();
  });
});
