import {
  getDocsItemPrimaryTargetSortOrder,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';
import type { PmsFolder, PmsTaskList } from '../api/pms-api';
import {
  applyFlatReorder,
  computeFlatDropTarget,
  sortedSiblings,
  type ReorderableItem,
} from '../api/pms-sidebar-reorder';

export type SpaceOrderDirection = 'up' | 'down';

export type SpaceOrderDraftList = Pick<
  PmsTaskList,
  'id' | 'name' | 'folder_id' | 'sort_order' | 'task_count'
>;

export type SpaceOrderDraftDoc = {
  id: string;
  title: string;
  sort_order: number;
};

export type SpaceOrderDraft = {
  lists: SpaceOrderDraftList[];
  docs: SpaceOrderDraftDoc[];
};

export type SpaceOrderDirtySummary = {
  changedListCount: number;
  changedDocCount: number;
  changedCount: number;
  isDirty: boolean;
};

export type SpaceOrderSavePayload = {
  lists: SpaceOrderDraftList[];
  docs: SpaceOrderDraftDoc[];
};

export function createSpaceOrderDraft({
  lists,
  docs,
}: {
  lists: PmsTaskList[];
  docs: DocsHubItem[];
}): SpaceOrderDraft {
  return {
    lists: lists
      .filter((list) => !list.archived)
      .map((list) => ({
        id: list.id,
        name: list.name,
        folder_id: list.folder_id,
        sort_order: list.sort_order,
        task_count: list.task_count,
      })),
    docs: docs.map((doc) => ({
      id: doc.id,
      title: doc.title,
      sort_order: getDocsItemPrimaryTargetSortOrder(doc),
    })),
  };
}

export function sortSpaceOrderFolders(
  folders: PmsFolder[],
  locale: string,
): PmsFolder[] {
  return Array.from(folders).sort(
    (left, right) =>
      left.sort_order - right.sort_order ||
      left.name.localeCompare(right.name, locale),
  );
}

export function getRootSpaceOrderDraftLists(
  draft: SpaceOrderDraft,
  locale: string,
): SpaceOrderDraftList[] {
  return getSpaceOrderDraftListsForParent(draft, null, locale);
}

export function getSpaceOrderDraftListsForParent(
  draft: SpaceOrderDraft,
  parentId: string | null,
  locale: string,
): SpaceOrderDraftList[] {
  return draft.lists
    .filter((list) => (list.folder_id ?? null) === parentId)
    .slice()
    .sort((left, right) => compareByOrderThenName(left, right, locale));
}

export function getOrderedSpaceOrderDraftDocs(
  draft: SpaceOrderDraft,
  locale: string,
): SpaceOrderDraftDoc[] {
  return Array.from(draft.docs).sort(
    (left, right) =>
      left.sort_order - right.sort_order ||
      left.title.localeCompare(right.title, locale),
  );
}

export function summarizeSpaceOrderDraftChanges({
  draft,
  originalLists,
  originalDocs,
}: {
  draft: SpaceOrderDraft;
  originalLists: PmsTaskList[];
  originalDocs: DocsHubItem[];
}): SpaceOrderDirtySummary {
  const originalListMap = new Map(
    originalLists.map((list) => [
      list.id,
      {
        folder_id: list.folder_id ?? null,
        sort_order: list.sort_order,
      },
    ]),
  );
  const originalDocMap = new Map(
    originalDocs.map((doc) => [
      doc.id,
      { sort_order: getDocsItemPrimaryTargetSortOrder(doc) },
    ]),
  );
  const changedListCount = draft.lists.filter((list) => {
    const original = originalListMap.get(list.id);
    return (
      original &&
      (original.folder_id !== (list.folder_id ?? null) ||
        original.sort_order !== list.sort_order)
    );
  }).length;
  const changedDocCount = draft.docs.filter((doc) => {
    const original = originalDocMap.get(doc.id);
    return original && original.sort_order !== doc.sort_order;
  }).length;
  const changedCount = changedListCount + changedDocCount;
  return {
    changedListCount,
    changedDocCount,
    changedCount,
    isDirty: changedCount > 0,
  };
}

export function moveSpaceOrderDraftListStep(
  draft: SpaceOrderDraft,
  listId: string,
  direction: SpaceOrderDirection,
): SpaceOrderDraft {
  const items = toListItems(draft.lists);
  const active = items.find((item) => item.id === listId);
  if (!active) return draft;
  const siblings = sortedSiblings(items, active.parent_id ?? null);
  const currentIndex = siblings.findIndex((item) => item.id === listId);
  if (currentIndex < 0) return draft;
  if (direction === 'up') {
    if (currentIndex === 0) return draft;
    const target = computeFlatDropTarget(
      items,
      siblings[currentIndex - 1].id,
      'before',
    );
    if (!target) return draft;
    const result = applyFlatReorder(items, listId, target);
    return result ? commitListItems(draft, result.nextItems) : draft;
  }
  if (currentIndex >= siblings.length - 1) return draft;
  const target = computeFlatDropTarget(
    items,
    siblings[currentIndex + 1].id,
    'after',
  );
  if (!target) return draft;
  const result = applyFlatReorder(items, listId, target);
  return result ? commitListItems(draft, result.nextItems) : draft;
}

export function moveSpaceOrderDraftListParent(
  draft: SpaceOrderDraft,
  listId: string,
  nextParentId: string | null,
): SpaceOrderDraft {
  const items = toListItems(draft.lists);
  const targetParentId = nextParentId ?? null;
  const result = applyFlatReorder(items, listId, {
    parentId: targetParentId,
    index: sortedSiblings(items, targetParentId).length,
    zone: 'after',
  });
  return result ? commitListItems(draft, result.nextItems) : draft;
}

export function moveSpaceOrderDraftDocStep(
  draft: SpaceOrderDraft,
  docId: string,
  direction: SpaceOrderDirection,
): SpaceOrderDraft {
  const items = toDocItems(draft.docs);
  const siblings = sortedSiblings(items, null);
  const currentIndex = siblings.findIndex((item) => item.id === docId);
  if (currentIndex < 0) return draft;
  if (direction === 'up') {
    if (currentIndex === 0) return draft;
    const target = computeFlatDropTarget(
      items,
      siblings[currentIndex - 1].id,
      'before',
    );
    if (!target) return draft;
    const result = applyFlatReorder(items, docId, target, {
      allowCrossParent: false,
    });
    return result ? commitDocItems(draft, result.nextItems) : draft;
  }
  if (currentIndex >= siblings.length - 1) return draft;
  const target = computeFlatDropTarget(
    items,
    siblings[currentIndex + 1].id,
    'after',
  );
  if (!target) return draft;
  const result = applyFlatReorder(items, docId, target, {
    allowCrossParent: false,
  });
  return result ? commitDocItems(draft, result.nextItems) : draft;
}

export function createSpaceOrderSavePayload(
  draft: SpaceOrderDraft,
): SpaceOrderSavePayload {
  return {
    lists: draft.lists.map((list) => ({ ...list })),
    docs: draft.docs.map((doc) => ({ ...doc })),
  };
}

function compareByOrderThenName(
  left: { sort_order: number; name: string },
  right: { sort_order: number; name: string },
  locale: string,
): number {
  if (left.sort_order !== right.sort_order) {
    return left.sort_order - right.sort_order;
  }
  return left.name.localeCompare(right.name, locale);
}

function toListItems(lists: SpaceOrderDraftList[]): ReorderableItem[] {
  return lists.map((list) => ({
    id: list.id,
    parent_id: list.folder_id ?? null,
    sort_order: list.sort_order,
    name: list.name,
  }));
}

function toDocItems(docs: SpaceOrderDraftDoc[]): ReorderableItem[] {
  return docs.map((doc) => ({
    id: doc.id,
    parent_id: null,
    sort_order: doc.sort_order,
    name: doc.title,
  }));
}

function commitListItems(
  draft: SpaceOrderDraft,
  nextItems: ReorderableItem[],
): SpaceOrderDraft {
  const patchMap = new Map(nextItems.map((item) => [item.id, item]));
  return {
    ...draft,
    lists: draft.lists.map((list) => {
      const next = patchMap.get(list.id);
      return next
        ? { ...list, folder_id: next.parent_id, sort_order: next.sort_order }
        : list;
    }),
  };
}

function commitDocItems(
  draft: SpaceOrderDraft,
  nextItems: ReorderableItem[],
): SpaceOrderDraft {
  const patchMap = new Map(nextItems.map((item) => [item.id, item]));
  return {
    ...draft,
    docs: draft.docs.map((doc) => {
      const next = patchMap.get(doc.id);
      return next ? { ...doc, sort_order: next.sort_order } : doc;
    }),
  };
}
