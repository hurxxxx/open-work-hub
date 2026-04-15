/**
 * Shared reorder helpers for the PMS sidebar. Three item kinds all share the
 * same pattern — flat list scoped to a parent, stable `sort_order` field,
 * optional "move between parents" semantics:
 *
 *   1. Folders       — flat, parent = team_id
 *   2. Task Lists    — flat, parent = folder_id (nullable) + cross-folder move
 *   3. Space Docs    — flat, parent = team_id (no cross-parent move)
 *
 * `applyFlatReorder` rebalances the affected sibling buckets to `index * 1000`
 * and emits one patch per changed row, mirroring the tree helpers in
 * [docs-page-reorder.ts](apps/web/src/domains/docs/docs-page-reorder.ts).
 */

export type FlatDropZone = 'before' | 'after';

export interface FlatDropTarget {
  parentId: string | null;
  index: number;
  zone: FlatDropZone;
}

export interface FlatReorderPatch<Id extends string = string> {
  id: Id;
  parent_id: string | null;
  sort_order: number;
  parent_changed: boolean;
}

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

const SORT_STEP = 1000;

function compareItems(left: ReorderableItem, right: ReorderableItem): number {
  if (left.sort_order !== right.sort_order) return left.sort_order - right.sort_order;
  return left.name.localeCompare(right.name, 'ko');
}

export function sortedSiblings<T extends ReorderableItem>(items: T[], parentId: string | null): T[] {
  return items
    .filter((item) => (item.parent_id ?? null) === parentId)
    .slice()
    .sort(compareItems);
}

/**
 * Row-relative drop zone. Flat lists never accept "inside" drops (leaf rows),
 * so we split each row in half: upper 50% = before, lower 50% = after.
 */
export function resolveFlatDropZone(pointerY: number, rect: { top: number; height: number }): FlatDropZone {
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
  const { allowCrossParent = true } = options;
  const active = items.find((item) => item.id === activeId);
  if (!active) return null;
  const previousParentId = active.parent_id ?? null;
  const nextParentId = target.parentId;
  const parentChanged = previousParentId !== nextParentId;
  let insertionIndex = target.index;

  if (parentChanged && !allowCrossParent) return null;

  if (!parentChanged) {
    const siblings = sortedSiblings(items, previousParentId);
    const currentIndex = siblings.findIndex((sibling) => sibling.id === activeId);
    if (currentIndex === -1) return null;
    insertionIndex = target.index > currentIndex ? target.index - 1 : target.index;
    if (insertionIndex === currentIndex) return null;
  }

  const byParent = new Map<string | null, T[]>();
  for (const item of items) {
    const key = item.parent_id ?? null;
    const bucket = byParent.get(key);
    if (bucket) bucket.push(item);
    else byParent.set(key, [item]);
  }
  for (const bucket of byParent.values()) bucket.sort(compareItems);

  const previousBucket = (byParent.get(previousParentId) ?? []).filter((item) => item.id !== activeId);
  byParent.set(previousParentId, previousBucket);

  const destinationBucket = parentChanged
    ? (byParent.get(nextParentId) ?? []).slice()
    : previousBucket.slice();
  const clampedIndex = Math.max(0, Math.min(insertionIndex, destinationBucket.length));
  destinationBucket.splice(clampedIndex, 0, { ...active, parent_id: nextParentId });
  byParent.set(nextParentId, destinationBucket);

  const touchedParents = new Set<string | null>([nextParentId]);
  if (parentChanged) touchedParents.add(previousParentId);

  const patches: FlatReorderPatch<T['id']>[] = [];
  const updatedById = new Map<string, T>();

  for (const parentId of touchedParents) {
    const bucket = byParent.get(parentId) ?? [];
    bucket.forEach((item, index) => {
      const nextSortOrder = index * SORT_STEP;
      const isActive = item.id === activeId;
      const sortChanged = item.sort_order !== nextSortOrder;
      const parentMoved = isActive && parentChanged;
      if (!sortChanged && !parentMoved) {
        updatedById.set(item.id, item);
        return;
      }
      const updated = { ...item, sort_order: nextSortOrder, parent_id: parentId } as T;
      updatedById.set(item.id, updated);
      patches.push({
        id: item.id as T['id'],
        parent_id: parentId,
        sort_order: nextSortOrder,
        parent_changed: parentMoved,
      });
    });
  }

  if (patches.length === 0) return null;

  const nextItems = items.map((item) => updatedById.get(item.id) ?? item);
  return { nextItems, patches };
}
