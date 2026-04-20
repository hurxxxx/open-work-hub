import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Dialog } from '@aidoo/ui';
import { ArrowDown, ArrowUp, FileText, FolderOpen, List as ListIcon } from 'lucide-react';

import {
  getDocsItemPrimaryContainerSortOrder,
  type DocsHubItem,
} from '@/src/domains/docs/docs-api';
import type { PmsFolder, PmsTaskList } from '@/src/domains/pms/pms-api';
import {
  applyFlatReorder,
  computeFlatDropTarget,
  sortedSiblings,
  type ReorderableItem,
} from '@/src/domains/pms/pms-sidebar-reorder';

type DraftList = Pick<PmsTaskList, 'id' | 'name' | 'folder_id' | 'sort_order' | 'issue_count'>;
type DraftDoc = {
  id: string;
  title: string;
  sort_order: number;
};

interface SpaceOrderEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  spaceName: string;
  folders: PmsFolder[];
  lists: PmsTaskList[];
  docs: DocsHubItem[];
  onSave: (payload: { lists: DraftList[]; docs: DraftDoc[] }) => Promise<void>;
}

const ROOT_VALUE = '__root__';

function compareByOrderThenName(left: { sort_order: number; name: string }, right: { sort_order: number; name: string }) {
  if (left.sort_order !== right.sort_order) return left.sort_order - right.sort_order;
  return left.name.localeCompare(right.name, 'ko');
}

function toListItems(lists: DraftList[]): ReorderableItem[] {
  return lists.map((list) => ({
    id: list.id,
    parent_id: list.folder_id ?? null,
    sort_order: list.sort_order,
    name: list.name,
  }));
}

function toDocItems(docs: DraftDoc[]): ReorderableItem[] {
  return docs.map((doc) => ({
    id: doc.id,
    parent_id: null,
    sort_order: doc.sort_order,
    name: doc.title,
  }));
}

export function SpaceOrderEditorModal({
  isOpen,
  onClose,
  spaceName,
  folders,
  lists,
  docs,
  onSave,
}: SpaceOrderEditorModalProps) {
  const orderedFolders = useMemo(
    () => [...folders].sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name, 'ko')),
    [folders],
  );
  const [draftLists, setDraftLists] = useState<DraftList[]>([]);
  const [draftDocs, setDraftDocs] = useState<DraftDoc[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wasOpenRef = useRef(false);

  useEffect(() => {
    if (isOpen && !wasOpenRef.current) {
      setDraftLists(
        lists.map((list) => ({
          id: list.id,
          name: list.name,
          folder_id: list.folder_id,
          sort_order: list.sort_order,
          issue_count: list.issue_count,
        })),
      );
      setDraftDocs(
        docs.map((doc) => ({
          id: doc.id,
          title: doc.title,
          sort_order: getDocsItemPrimaryContainerSortOrder(doc),
        })),
      );
      setSaving(false);
      setError(null);
    }
    wasOpenRef.current = isOpen;
  }, [docs, isOpen, lists]);

  const originalListMap = useMemo(
    () => new Map(lists.map((list) => [list.id, { folder_id: list.folder_id ?? null, sort_order: list.sort_order }])),
    [lists],
  );
  const originalDocMap = useMemo(
    () => new Map(docs.map((doc) => [doc.id, { sort_order: getDocsItemPrimaryContainerSortOrder(doc) }])),
    [docs],
  );

  const changedListCount = useMemo(
    () => draftLists.filter((list) => {
      const original = originalListMap.get(list.id);
      return original && (original.folder_id !== (list.folder_id ?? null) || original.sort_order !== list.sort_order);
    }).length,
    [draftLists, originalListMap],
  );
  const changedDocCount = useMemo(
    () => draftDocs.filter((doc) => {
      const original = originalDocMap.get(doc.id);
      return original && original.sort_order !== doc.sort_order;
    }).length,
    [draftDocs, originalDocMap],
  );
  const isDirty = changedListCount > 0 || changedDocCount > 0;

  function requestClose() {
    if (saving) return;
    if (isDirty && !window.confirm('저장하지 않은 순서 변경이 있습니다. 닫을까요?')) {
      return;
    }
    onClose();
  }

  function commitListItems(nextItems: ReorderableItem[]) {
    const patchMap = new Map(nextItems.map((item) => [item.id, item]));
    setDraftLists((current) => current.map((list) => {
      const next = patchMap.get(list.id);
      return next ? { ...list, folder_id: next.parent_id, sort_order: next.sort_order } : list;
    }));
  }

  function commitDocItems(nextItems: ReorderableItem[]) {
    const patchMap = new Map(nextItems.map((item) => [item.id, item]));
    setDraftDocs((current) => current.map((doc) => {
      const next = patchMap.get(doc.id);
      return next ? { ...doc, sort_order: next.sort_order } : doc;
    }));
  }

  function moveListStep(listId: string, direction: 'up' | 'down') {
    const items = toListItems(draftLists);
    const active = items.find((item) => item.id === listId);
    if (!active) return;
    const siblings = sortedSiblings(items, active.parent_id ?? null);
    const currentIndex = siblings.findIndex((item) => item.id === listId);
    if (currentIndex < 0) return;
    if (direction === 'up') {
      if (currentIndex === 0) return;
      const target = computeFlatDropTarget(items, siblings[currentIndex - 1].id, 'before');
      if (!target) return;
      const result = applyFlatReorder(items, listId, target);
      if (!result) return;
      commitListItems(result.nextItems);
      return;
    }
    if (currentIndex >= siblings.length - 1) return;
    const target = computeFlatDropTarget(items, siblings[currentIndex + 1].id, 'after');
    if (!target) return;
    const result = applyFlatReorder(items, listId, target);
    if (!result) return;
    commitListItems(result.nextItems);
  }

  function moveListParent(listId: string, nextParentId: string | null) {
    const items = toListItems(draftLists);
    const target = {
      parentId: nextParentId,
      index: sortedSiblings(items, nextParentId).length,
      zone: 'after' as const,
    };
    const result = applyFlatReorder(items, listId, target);
    if (!result) return;
    commitListItems(result.nextItems);
  }

  function moveDocStep(docId: string, direction: 'up' | 'down') {
    const items = toDocItems(draftDocs);
    const siblings = sortedSiblings(items, null);
    const currentIndex = siblings.findIndex((item) => item.id === docId);
    if (currentIndex < 0) return;
    if (direction === 'up') {
      if (currentIndex === 0) return;
      const target = computeFlatDropTarget(items, siblings[currentIndex - 1].id, 'before');
      if (!target) return;
      const result = applyFlatReorder(items, docId, target, { allowCrossParent: false });
      if (!result) return;
      commitDocItems(result.nextItems);
      return;
    }
    if (currentIndex >= siblings.length - 1) return;
    const target = computeFlatDropTarget(items, siblings[currentIndex + 1].id, 'after');
    if (!target) return;
    const result = applyFlatReorder(items, docId, target, { allowCrossParent: false });
    if (!result) return;
    commitDocItems(result.nextItems);
  }

  async function handleSave() {
    if (saving || !isDirty) {
      onClose();
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({ lists: draftLists, docs: draftDocs });
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : '순서를 저장하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  }

  const rootLists = useMemo(
    () => draftLists.filter((list) => !list.folder_id).sort((left, right) => compareByOrderThenName(left, right)),
    [draftLists],
  );
  const docsOrdered = useMemo(
    () => [...draftDocs].sort((left, right) => left.sort_order - right.sort_order || left.title.localeCompare(right.title, 'ko')),
    [draftDocs],
  );

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) requestClose(); }}
      title={`${spaceName} 순서 편집`}
      maxWidth="max-w-5xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full items-center justify-between gap-3">
          <div className="app-text-caption text-app-ink/50">
            {isDirty ? `${changedListCount + changedDocCount}개의 변경사항이 있습니다.` : '변경사항이 없습니다.'}
          </div>
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={requestClose} disabled={saving}>
              취소
            </Button>
            <Button variant="primary" onClick={handleSave} disabled={saving}>
              {saving ? '저장 중...' : '저장'}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-6 text-app-ink">
        <div className="rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-3">
          <div className="app-text-control-sm text-app-ink">전용 편집 화면</div>
          <div className="app-text-body mt-1 text-app-ink/60">
            여기서는 순서만 조정합니다. 사이드바의 이동, 메뉴, 이름 변경과 분리해 draft로 편집한 뒤 저장 시 한 번에 반영합니다.
          </div>
        </div>

        {error ? (
          <div className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]">
            {error}
          </div>
        ) : null}

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.8fr)]">
          <section className="rounded-lg border border-app-border bg-app-bg">
            <div className="border-b border-app-border px-4 py-3">
              <div className="app-text-control-sm text-app-ink">Lists</div>
              <div className="app-text-caption text-app-ink/50">위/아래 이동과 폴더 이동을 draft로 편집합니다.</div>
            </div>
            <div className="space-y-5 px-4 py-4">
              <div className="space-y-2">
                <div className="app-text-overline text-app-ink/40">Root Lists</div>
                {rootLists.length === 0 ? (
                  <div className="app-text-body rounded-md border border-dashed border-app-border px-3 py-4 text-app-ink/40">
                    루트에 있는 리스트가 없습니다.
                  </div>
                ) : rootLists.map((list, index) => (
                  <div key={list.id} className="flex items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
                    <ListIcon size={14} className="shrink-0 text-gray-500" />
                    <div className="min-w-0 flex-1">
                      <div className="app-text-control-sm truncate text-app-ink">{list.name}</div>
                      <div className="app-text-caption text-app-ink/40">이슈 {list.issue_count}개</div>
                    </div>
                    <select
                      value={list.folder_id ?? ROOT_VALUE}
                      onChange={(event) => moveListParent(list.id, event.target.value === ROOT_VALUE ? null : event.target.value)}
                      className="app-text-caption rounded-md border border-app-border bg-app-bg px-2 py-1 text-app-ink outline-none"
                    >
                      <option value={ROOT_VALUE}>루트</option>
                      {orderedFolders.map((folder) => (
                        <option key={folder.id} value={folder.id}>{folder.name}</option>
                      ))}
                    </select>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => moveListStep(list.id, 'up')}
                        disabled={index === 0}
                        className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                        title="위로"
                      >
                        <ArrowUp size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveListStep(list.id, 'down')}
                        disabled={index === rootLists.length - 1}
                        className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                        title="아래로"
                      >
                        <ArrowDown size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {orderedFolders.map((folder) => {
                const folderLists = draftLists
                  .filter((list) => list.folder_id === folder.id)
                  .sort((left, right) => compareByOrderThenName(left, right));
                return (
                  <div key={folder.id} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <FolderOpen size={14} className="text-gray-500" />
                      <div className="app-text-overline text-app-ink/50">{folder.name}</div>
                    </div>
                    {folderLists.length === 0 ? (
                      <div className="app-text-body rounded-md border border-dashed border-app-border px-3 py-4 text-app-ink/40">
                        이 폴더에는 리스트가 없습니다.
                      </div>
                    ) : folderLists.map((list, index) => (
                      <div key={list.id} className="flex items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
                        <ListIcon size={14} className="shrink-0 text-gray-500" />
                        <div className="min-w-0 flex-1">
                          <div className="app-text-control-sm truncate text-app-ink">{list.name}</div>
                          <div className="app-text-caption text-app-ink/40">이슈 {list.issue_count}개</div>
                        </div>
                        <select
                          value={list.folder_id ?? ROOT_VALUE}
                          onChange={(event) => moveListParent(list.id, event.target.value === ROOT_VALUE ? null : event.target.value)}
                          className="app-text-caption rounded-md border border-app-border bg-app-bg px-2 py-1 text-app-ink outline-none"
                        >
                          <option value={ROOT_VALUE}>루트</option>
                          {orderedFolders.map((option) => (
                            <option key={option.id} value={option.id}>{option.name}</option>
                          ))}
                        </select>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => moveListStep(list.id, 'up')}
                            disabled={index === 0}
                            className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                            title="위로"
                          >
                            <ArrowUp size={14} />
                          </button>
                          <button
                            type="button"
                            onClick={() => moveListStep(list.id, 'down')}
                            disabled={index === folderLists.length - 1}
                            className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                            title="아래로"
                          >
                            <ArrowDown size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-lg border border-app-border bg-app-bg">
            <div className="border-b border-app-border px-4 py-3">
              <div className="app-text-control-sm text-app-ink">Docs</div>
              <div className="app-text-caption text-app-ink/50">스페이스 문서 컬렉션 순서를 조정합니다.</div>
            </div>
            <div className="space-y-2 px-4 py-4">
              {docsOrdered.length === 0 ? (
                <div className="app-text-body rounded-md border border-dashed border-app-border px-3 py-4 text-app-ink/40">
                  문서 컬렉션이 없습니다.
                </div>
              ) : docsOrdered.map((doc, index) => (
                <div key={doc.id} className="flex items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
                  <FileText size={14} className="shrink-0 text-gray-500" />
                  <div className="min-w-0 flex-1">
                    <div className="app-text-control-sm truncate text-app-ink">{doc.title || 'Untitled'}</div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => moveDocStep(doc.id, 'up')}
                      disabled={index === 0}
                      className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                      title="위로"
                    >
                      <ArrowUp size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => moveDocStep(doc.id, 'down')}
                      disabled={index === docsOrdered.length - 1}
                      className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                      title="아래로"
                    >
                      <ArrowDown size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </Dialog>
  );
}
