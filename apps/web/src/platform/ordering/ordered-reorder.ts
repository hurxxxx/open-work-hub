export interface OrderedReorderItem<Id extends string = string> {
  id: Id;
  parent_id: string | null;
  sort_order: number;
}

export interface OrderedReorderTarget {
  parentId: string | null;
  index: number;
}

export interface OrderedReorderPatch<Id extends string = string> {
  id: Id;
  parent_id: string | null;
  sort_order: number;
  parent_changed: boolean;
}

export interface OrderedReorderResult<T extends OrderedReorderItem> {
  nextItems: T[];
  patches: OrderedReorderPatch<T['id']>[];
}

export type OrderedItemComparator<T extends OrderedReorderItem> = (
  left: T,
  right: T,
) => number;

export interface OrderedReorderOptions<T extends OrderedReorderItem> {
  allowCrossParent?: boolean;
  compareItems: OrderedItemComparator<T>;
  sortStep?: number;
}

const DEFAULT_SORT_STEP = 1000;

export function compareOrderedItemsByText<T extends OrderedReorderItem>(
  left: T,
  right: T,
  getText: (item: T) => string,
): number {
  if (left.sort_order !== right.sort_order)
    return left.sort_order - right.sort_order;
  return getText(left).localeCompare(getText(right), 'ko');
}

export function sortedOrderedSiblings<T extends OrderedReorderItem>(
  items: T[],
  parentId: string | null,
  compareItems: OrderedItemComparator<T>,
): T[] {
  return items
    .filter((item) => (item.parent_id ?? null) === parentId)
    .slice()
    .sort(compareItems);
}

/**
 * Plans a reorder for ordered sibling buckets with nullable parent ids.
 *
 * The planner removes the active item from its source bucket, inserts it into
 * the destination bucket, then rebalances every touched bucket to
 * `index * sortStep`. Domain modules keep ownership of drag/drop rules and
 * labels; this helper owns the shared order mutation contract.
 */
export function applyOrderedReorder<T extends OrderedReorderItem>(
  items: T[],
  activeId: string,
  target: OrderedReorderTarget,
  options: OrderedReorderOptions<T>,
): OrderedReorderResult<T> | null {
  const {
    allowCrossParent = true,
    compareItems,
    sortStep = DEFAULT_SORT_STEP,
  } = options;
  const active = items.find((item) => item.id === activeId);
  if (!active) return null;

  const previousParentId = active.parent_id ?? null;
  const nextParentId = target.parentId;
  const parentChanged = previousParentId !== nextParentId;
  let insertionIndex = target.index;

  if (parentChanged && !allowCrossParent) return null;

  if (!parentChanged) {
    const siblings = sortedOrderedSiblings(
      items,
      previousParentId,
      compareItems,
    );
    const currentIndex = siblings.findIndex(
      (sibling) => sibling.id === activeId,
    );
    if (currentIndex === -1) return null;
    insertionIndex =
      target.index > currentIndex ? target.index - 1 : target.index;
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

  const previousBucket = (byParent.get(previousParentId) ?? []).filter(
    (item) => item.id !== activeId,
  );
  byParent.set(previousParentId, previousBucket);

  const destinationBucket = parentChanged
    ? (byParent.get(nextParentId) ?? []).slice()
    : previousBucket.slice();
  const clampedIndex = Math.max(
    0,
    Math.min(insertionIndex, destinationBucket.length),
  );
  destinationBucket.splice(clampedIndex, 0, {
    ...active,
    parent_id: nextParentId,
  } as T);
  byParent.set(nextParentId, destinationBucket);

  const touchedParents = new Set<string | null>([nextParentId]);
  if (parentChanged) touchedParents.add(previousParentId);

  const patches: OrderedReorderPatch<T['id']>[] = [];
  const updatedById = new Map<string, T>();

  for (const parentId of touchedParents) {
    const bucket = byParent.get(parentId) ?? [];
    bucket.forEach((item, index) => {
      const nextSortOrder = index * sortStep;
      const isActive = item.id === activeId;
      const sortChanged = item.sort_order !== nextSortOrder;
      const parentMoved = isActive && parentChanged;
      if (!sortChanged && !parentMoved) {
        updatedById.set(item.id, item);
        return;
      }

      const updated = {
        ...item,
        sort_order: nextSortOrder,
        parent_id: parentId,
      } as T;
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
