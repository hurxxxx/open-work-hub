import type { HrGroupItem } from './admin-api';

interface HrGroupRow {
  depth: number;
  item: HrGroupItem;
}

export function buildHrGroupRows(items: readonly HrGroupItem[]): HrGroupRow[] {
  const children = new Map<string | null, HrGroupItem[]>();
  const ids = new Set(items.map((item) => item.id));
  for (const item of items) {
    const parentId =
      item.parent_id && ids.has(item.parent_id) ? item.parent_id : null;
    const siblings = children.get(parentId) ?? [];
    siblings.push(item);
    children.set(parentId, siblings);
  }
  for (const siblings of children.values()) {
    siblings.sort((left, right) => left.name.localeCompare(right.name));
  }

  const rows: HrGroupRow[] = [];
  const visited = new Set<string>();
  const visit = (item: HrGroupItem, depth: number) => {
    if (visited.has(item.id)) return;
    visited.add(item.id);
    rows.push({ depth, item });
    for (const child of children.get(item.id) ?? []) visit(child, depth + 1);
  };
  for (const item of children.get(null) ?? []) visit(item, 0);
  for (const item of items) visit(item, 0);
  return rows;
}

export function descendantIds(
  items: readonly HrGroupItem[],
  hrGroupId: string,
): Set<string> {
  const descendants = new Set<string>([hrGroupId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const item of items) {
      if (
        item.parent_id &&
        descendants.has(item.parent_id) &&
        !descendants.has(item.id)
      ) {
        descendants.add(item.id);
        changed = true;
      }
    }
  }
  return descendants;
}
