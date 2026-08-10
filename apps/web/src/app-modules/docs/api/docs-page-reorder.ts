import type { DocsPageItem } from './docs-api';
import {
  applyOrderedReorder,
  compareOrderedItemsByText,
  sortedOrderedSiblings,
  type OrderedReorderPatch,
} from '@/src/platform/ordering/ordered-reorder';

export type DropZone = 'before' | 'after' | 'inside';

export interface DropTarget {
  parentId: string | null;
  index: number;
  zone: DropZone;
}

export type ReorderPatch = OrderedReorderPatch;

export interface ReorderResult {
  nextPages: DocsPageItem[];
  patches: ReorderPatch[];
}

function comparePages(left: DocsPageItem, right: DocsPageItem): number {
  return compareOrderedItemsByText(left, right, (page) => page.title);
}

export function sortedChildren(
  pages: DocsPageItem[],
  parentId: string | null,
): DocsPageItem[] {
  return sortedOrderedSiblings(pages, parentId, comparePages);
}

export function collectDescendantIds(
  pages: DocsPageItem[],
  rootId: string,
): Set<string> {
  const childrenByParent = new Map<string | null, DocsPageItem[]>();
  for (const page of pages) {
    const key = page.parent_id ?? null;
    const bucket = childrenByParent.get(key);
    if (bucket) bucket.push(page);
    else childrenByParent.set(key, [page]);
  }
  const result = new Set<string>();
  const stack = [rootId];
  while (stack.length > 0) {
    const current = stack.pop();
    if (current === undefined) break;
    if (result.has(current)) continue;
    result.add(current);
    const kids = childrenByParent.get(current) ?? [];
    for (const kid of kids) stack.push(kid.id);
  }
  return result;
}

export function flattenVisibleTree(
  pages: DocsPageItem[],
  expanded: Set<string>,
): { id: string; depth: number; parentId: string | null }[] {
  const out: { id: string; depth: number; parentId: string | null }[] = [];
  const walk = (parentId: string | null, depth: number) => {
    for (const child of sortedChildren(pages, parentId)) {
      out.push({ id: child.id, depth, parentId });
      if (expanded.has(child.id)) walk(child.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

/**
 * Decide which drop zone applies given pointer position within a row.
 * - Top 25%: before (sibling above)
 * - Bottom 25%: after (sibling below)
 * - Middle 50%: inside (become child)
 */
export function resolveDropZone(
  pointerY: number,
  rect: { top: number; height: number },
): DropZone {
  const offset = pointerY - rect.top;
  const ratio = rect.height > 0 ? offset / rect.height : 0.5;
  if (ratio < 0.25) return 'before';
  if (ratio > 0.75) return 'after';
  return 'inside';
}

/**
 * Given a drop event on an existing row, compute the resulting parent + insert index.
 */
export function computeDropTarget(
  pages: DocsPageItem[],
  overPageId: string,
  zone: DropZone,
): DropTarget | null {
  const over = pages.find((page) => page.id === overPageId);
  if (!over) return null;
  const overParentId = over.parent_id ?? null;

  if (zone === 'inside') {
    const kids = sortedChildren(pages, over.id);
    return { parentId: over.id, index: kids.length, zone };
  }

  const siblings = sortedChildren(pages, overParentId);
  const overIndex = siblings.findIndex((sibling) => sibling.id === over.id);
  if (overIndex === -1) return null;
  const insertIndex = zone === 'before' ? overIndex : overIndex + 1;
  return { parentId: overParentId, index: insertIndex, zone };
}

/**
 * Produce the next `pages` list and the minimal PATCH set needed after moving
 * `activeId` into the given target. The caller is responsible for rejecting
 * moves that would create a cycle (active is ancestor of target).
 *
 * Rebalancing strategy: every affected sibling group gets its `sort_order`
 * rewritten to the platform ordering step. This keeps the server contract
 * simple and leaves large gaps for future inserts without touching unrelated
 * rows.
 */
export function applyReorder(
  pages: DocsPageItem[],
  activeId: string,
  target: DropTarget,
): ReorderResult | null {
  const result = applyOrderedReorder(pages, activeId, target, {
    compareItems: comparePages,
  });
  if (!result) return null;
  return { nextPages: result.nextItems, patches: result.patches };
}
