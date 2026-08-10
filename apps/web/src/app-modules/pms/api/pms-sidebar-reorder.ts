import {
  applyOrderedReorder,
  compareOrderedItemsByText,
  sortedOrderedSiblings,
  type OrderedReorderPatch,
} from '@/src/platform/ordering/ordered-reorder';

/**
 * PMS sidebar reorder facade. Folders, task lists, and space docs share the
 * platform ordered-sibling planner while this module keeps PMS names and flat
 * drop-zone behavior stable for callers.
 */

export type FlatDropZone = 'before' | 'after';

export interface FlatDropTarget {
  parentId: string | null;
  index: number;
  zone: FlatDropZone;
}

export type FlatReorderPatch<Id extends string = string> =
  OrderedReorderPatch<Id>;

export interface ReorderableItem<Id extends string = string> {
  id: Id;
  parent_id: string | null;
  sort_order: number;
  name: string;
}

export interface FlatReorderResult<T extends ReorderableItem> {
  nextItems: T[];
  patches: FlatReorderPatch<T['id']>[];
}

function compareItems(left: ReorderableItem, right: ReorderableItem): number {
  return compareOrderedItemsByText(left, right, (item) => item.name);
}

export function sortedSiblings<T extends ReorderableItem>(
  items: T[],
  parentId: string | null,
): T[] {
  return sortedOrderedSiblings(items, parentId, compareItems);
}

/**
 * Row-relative drop zone. Flat lists never accept "inside" drops (leaf rows),
 * so we split each row in half: upper 50% = before, lower 50% = after.
 */
export function resolveFlatDropZone(
  pointerY: number,
  rect: { top: number; height: number },
): FlatDropZone {
  const offset = pointerY - rect.top;
  const ratio = rect.height > 0 ? offset / rect.height : 0.5;
  return ratio < 0.5 ? 'before' : 'after';
}

export function computeFlatDropTarget<T extends ReorderableItem>(
  items: T[],
  overId: string,
  zone: FlatDropZone,
): FlatDropTarget | null {
  const over = items.find((item) => item.id === overId);
  if (!over) return null;
  const parentId = over.parent_id ?? null;
  const siblings = sortedSiblings(items, parentId);
  const overIndex = siblings.findIndex((sibling) => sibling.id === over.id);
  if (overIndex === -1) return null;
  const insertIndex = zone === 'before' ? overIndex : overIndex + 1;
  return { parentId, index: insertIndex, zone };
}

/**
 * Same semantics as `applyReorder` in docs-page-reorder.ts, but for flat
 * lists: no tree cycle check needed. If the destination parent differs from
 * the source parent, both buckets get renumbered.
 */
export function applyFlatReorder<T extends ReorderableItem>(
  items: T[],
  activeId: string,
  target: FlatDropTarget,
  options: { allowCrossParent?: boolean } = {},
): FlatReorderResult<T> | null {
  return applyOrderedReorder(items, activeId, target, {
    allowCrossParent: options.allowCrossParent,
    compareItems,
  });
}
