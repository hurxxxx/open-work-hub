import type { DocsPageItem } from './docs-api';

export type DropZone = 'before' | 'after' | 'inside';

export interface DropTarget {
  parentId: string | null;
  index: number;
  zone: DropZone;
}

export interface ReorderPatch {
  id: string;
  parent_id: string | null;
  sort_order: number;
  parent_changed: boolean;
}

export interface ReorderResult {
  nextPages: DocsPageItem[];
  patches: ReorderPatch[];
}

const SORT_STEP = 1000;

function comparePages(left: DocsPageItem, right: DocsPageItem): number {
  if (left.sort_order !== right.sort_order) return left.sort_order - right.sort_order;
  return left.title.localeCompare(right.title, 'ko');
}

export function sortedChildren(pages: DocsPageItem[], parentId: string | null): DocsPageItem[] {
  return pages
    .filter((page) => (page.parent_id ?? null) === parentId)
    .slice()
    .sort(comparePages);
}

export function collectDescendantIds(pages: DocsPageItem[], rootId: string): Set<string> {
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
    const current = stack.pop()!;
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
export function resolveDropZone(pointerY: number, rect: { top: number; height: number }): DropZone {
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
 * rewritten to `index * SORT_STEP`. This keeps the server contract simple and
 * leaves large gaps for future inserts without touching unrelated rows.
 */
export function applyReorder(
  pages: DocsPageItem[],
  activeId: string,
  target: DropTarget,
): ReorderResult | null {
  const active = pages.find((page) => page.id === activeId);
  if (!active) return null;
  const previousParentId = active.parent_id ?? null;
  const nextParentId = target.parentId;
  const parentChanged = previousParentId !== nextParentId;
  let insertionIndex = target.index;

  if (!parentChanged) {
    const siblings = sortedChildren(pages, previousParentId);
    const currentIndex = siblings.findIndex((sibling) => sibling.id === activeId);
    if (currentIndex === -1) return null;
    insertionIndex = target.index > currentIndex ? target.index - 1 : target.index;
    if (insertionIndex === currentIndex) return null;
  }

  const byParent = new Map<string | null, DocsPageItem[]>();
  for (const page of pages) {
    const key = page.parent_id ?? null;
    const bucket = byParent.get(key);
    if (bucket) bucket.push(page);
    else byParent.set(key, [page]);
  }
  for (const bucket of byParent.values()) bucket.sort(comparePages);

  const previousBucket = (byParent.get(previousParentId) ?? []).filter((page) => page.id !== activeId);
  byParent.set(previousParentId, previousBucket);

  const destinationBucket = parentChanged
    ? (byParent.get(nextParentId) ?? []).slice()
    : previousBucket.slice();
  const clampedIndex = Math.max(0, Math.min(insertionIndex, destinationBucket.length));
  destinationBucket.splice(clampedIndex, 0, { ...active, parent_id: nextParentId });
  byParent.set(nextParentId, destinationBucket);

  const touchedParents = new Set<string | null>([nextParentId]);
  if (parentChanged) touchedParents.add(previousParentId);

  const patches: ReorderPatch[] = [];
  const updatedById = new Map<string, DocsPageItem>();

  for (const parentId of touchedParents) {
    const bucket = byParent.get(parentId) ?? [];
    bucket.forEach((page, index) => {
      const nextSortOrder = index * SORT_STEP;
      const isActive = page.id === activeId;
      const sortChanged = page.sort_order !== nextSortOrder;
      const parentMoved = isActive && parentChanged;
      if (!sortChanged && !parentMoved) {
        updatedById.set(page.id, page);
        return;
      }
      const updated: DocsPageItem = {
        ...page,
        sort_order: nextSortOrder,
        parent_id: parentId,
      };
      updatedById.set(page.id, updated);
      patches.push({
        id: page.id,
        parent_id: parentId,
        sort_order: nextSortOrder,
        parent_changed: parentMoved,
      });
    });
  }

  if (patches.length === 0) return null;

  const nextPages = pages.map((page) => updatedById.get(page.id) ?? page);
  return { nextPages, patches };
}
