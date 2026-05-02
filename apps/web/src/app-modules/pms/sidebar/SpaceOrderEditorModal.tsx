import { useEffect, useMemo, useRef, useState } from 'react';
import { Dialog } from '@aidoo/ui/primitives/dialog';
import { Button } from '@aidoo/ui/primitives/button';
import { ArrowDown, ArrowUp, FileText, FolderOpen, List as ListIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  getDocsItemPrimaryContainerSortOrder,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';
import type { PmsFolder, PmsTaskList } from '../api/pms-api';
import {
  applyFlatReorder,
  computeFlatDropTarget,
  sortedSiblings,
  type ReorderableItem,
} from '../api/pms-sidebar-reorder';

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

function compareByOrderThenName(left: { sort_order: number; name: string }, right: { sort_order: number; name: string }, locale: string) {
  if (left.sort_order !== right.sort_order) return left.sort_order - right.sort_order;
  return left.name.localeCompare(right.name, locale);
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
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const orderedFolders = useMemo(
    () => [...folders].sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name, locale)),
    [folders, locale],
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
    if (isDirty && !window.confirm(t('pms.orderEditor.closeDirtyConfirm'))) {
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
      setError(saveError instanceof Error ? saveError.message : t('pms.orderEditor.saveFailed'));
    } finally {
      setSaving(false);
    }
  }

  const rootLists = useMemo(
    () => draftLists.filter((list) => !list.folder_id).sort((left, right) => compareByOrderThenName(left, right, locale)),
    [draftLists, locale],
  );
  const docsOrdered = useMemo(
    () => [...draftDocs].sort((left, right) => left.sort_order - right.sort_order || left.title.localeCompare(right.title, locale)),
    [draftDocs, locale],
  );

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) requestClose(); }}
      title={t('pms.orderEditor.title', { spaceName })}
      maxWidth="max-w-5xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full items-center justify-between gap-3">
          <div className="app-text-caption text-app-ink/50">
            {isDirty ? t('pms.orderEditor.changedCount', { count: changedListCount + changedDocCount }) : t('pms.orderEditor.noChanges')}
          </div>
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={requestClose} disabled={saving}>
              {t('common:actions.cancel')}
            </Button>
            <Button variant="primary" onClick={handleSave} disabled={saving}>
              {saving ? t('common:actions.saving') : t('common:actions.save')}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-6 text-app-ink">
        <div className="rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-3">
          <div className="app-text-control-sm text-app-ink">{t('pms.orderEditor.dedicatedEditor')}</div>
          <div className="app-text-body mt-1 text-app-ink/60">
            {t('pms.orderEditor.description')}
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
              <div className="app-text-control-sm text-app-ink">{t('pms.spaceOverview.lists')}</div>
              <div className="app-text-caption text-app-ink/50">{t('pms.orderEditor.listsDescription')}</div>
            </div>
            <div className="space-y-5 px-4 py-4">
              <div className="space-y-2">
                <div className="app-text-overline text-app-ink/40">{t('pms.orderEditor.rootLists')}</div>
                {rootLists.length === 0 ? (
                  <div className="app-text-body rounded-md border border-dashed border-app-border px-3 py-4 text-app-ink/40">
                    {t('pms.orderEditor.noRootLists')}
                  </div>
                ) : rootLists.map((list, index) => (
                  <div key={list.id} className="flex items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
                    <ListIcon size={14} className="shrink-0 text-gray-500" />
                    <div className="min-w-0 flex-1">
                      <div className="app-text-control-sm truncate text-app-ink">{list.name}</div>
                      <div className="app-text-caption text-app-ink/40">{t('pms.spaceOverview.issueCount', { count: list.issue_count })}</div>
                    </div>
                    <select
                      value={list.folder_id ?? ROOT_VALUE}
                      onChange={(event) => moveListParent(list.id, event.target.value === ROOT_VALUE ? null : event.target.value)}
                      className="app-text-caption rounded-md border border-app-border bg-app-bg px-2 py-1 text-app-ink outline-none"
                    >
                      <option value={ROOT_VALUE}>{t('pms.orderEditor.root')}</option>
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
                        title={t('pms.orderEditor.moveUp')}
                      >
                        <ArrowUp size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveListStep(list.id, 'down')}
                        disabled={index === rootLists.length - 1}
                        className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                        title={t('pms.orderEditor.moveDown')}
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
                  .sort((left, right) => compareByOrderThenName(left, right, locale));
                return (
                  <div key={folder.id} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <FolderOpen size={14} className="text-gray-500" />
                      <div className="app-text-overline text-app-ink/50">{folder.name}</div>
                    </div>
                    {folderLists.length === 0 ? (
                      <div className="app-text-body rounded-md border border-dashed border-app-border px-3 py-4 text-app-ink/40">
                        {t('pms.orderEditor.noFolderLists')}
                      </div>
                    ) : folderLists.map((list, index) => (
                      <div key={list.id} className="flex items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
                        <ListIcon size={14} className="shrink-0 text-gray-500" />
                        <div className="min-w-0 flex-1">
                          <div className="app-text-control-sm truncate text-app-ink">{list.name}</div>
                          <div className="app-text-caption text-app-ink/40">{t('pms.spaceOverview.issueCount', { count: list.issue_count })}</div>
                        </div>
                        <select
                          value={list.folder_id ?? ROOT_VALUE}
                          onChange={(event) => moveListParent(list.id, event.target.value === ROOT_VALUE ? null : event.target.value)}
                          className="app-text-caption rounded-md border border-app-border bg-app-bg px-2 py-1 text-app-ink outline-none"
                        >
                          <option value={ROOT_VALUE}>{t('pms.orderEditor.root')}</option>
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
                            title={t('pms.orderEditor.moveUp')}
                          >
                            <ArrowUp size={14} />
                          </button>
                          <button
                            type="button"
                            onClick={() => moveListStep(list.id, 'down')}
                            disabled={index === folderLists.length - 1}
                            className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                            title={t('pms.orderEditor.moveDown')}
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
              <div className="app-text-control-sm text-app-ink">{t('pms.spaceOverview.docs')}</div>
              <div className="app-text-caption text-app-ink/50">{t('pms.orderEditor.docsDescription')}</div>
            </div>
            <div className="space-y-2 px-4 py-4">
              {docsOrdered.length === 0 ? (
                <div className="app-text-body rounded-md border border-dashed border-app-border px-3 py-4 text-app-ink/40">
                  {t('pms.spaceOverview.noDocCollections')}
                </div>
              ) : docsOrdered.map((doc, index) => (
                <div key={doc.id} className="flex items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
                  <FileText size={14} className="shrink-0 text-gray-500" />
                  <div className="min-w-0 flex-1">
                    <div className="app-text-control-sm truncate text-app-ink">{doc.title || t('pms.orderEditor.untitled')}</div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => moveDocStep(doc.id, 'up')}
                      disabled={index === 0}
                      className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                      title={t('pms.orderEditor.moveUp')}
                    >
                      <ArrowUp size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => moveDocStep(doc.id, 'down')}
                      disabled={index === docsOrdered.length - 1}
                      className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
                      title={t('pms.orderEditor.moveDown')}
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
