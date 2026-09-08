import { Button } from '@open-work-hub/ui/primitives/button';
import { Dialog } from '@open-work-hub/ui/primitives/dialog';
import {
  ArrowDown,
  ArrowUp,
  FileText,
  FolderOpen,
  List as ListIcon,
} from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { DocsHubItem } from '@/src/app-modules/docs/public-api';
import type { PmsFolder, PmsTaskList } from '../api/pms-api';
import {
  createSpaceOrderDraft,
  createSpaceOrderSavePayload,
  getOrderedSpaceOrderDraftDocs,
  getRootSpaceOrderDraftLists,
  getSpaceOrderDraftListsForParent,
  moveSpaceOrderDraftDocStep,
  moveSpaceOrderDraftListParent,
  moveSpaceOrderDraftListStep,
  sortSpaceOrderFolders,
  summarizeSpaceOrderDraftChanges,
  type SpaceOrderDraftDoc,
  type SpaceOrderDraftList,
  type SpaceOrderSavePayload,
} from './space-order-editor-model';

interface SpaceOrderEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  spaceName: string;
  folders: PmsFolder[];
  lists: PmsTaskList[];
  docs: DocsHubItem[];
  onSave: (payload: SpaceOrderSavePayload) => Promise<void>;
}

const ROOT_VALUE = '__root__';
type SpaceOrderMoveDirection = 'up' | 'down';

function OrderEditorEmptyBlock({ children }: { children: ReactNode }) {
  return (
    <div className="app-text-body rounded-md border border-dashed border-app-border px-3 py-4 text-app-ink/40">
      {children}
    </div>
  );
}

function MoveStepButtons({
  disableDown,
  disableUp,
  labels,
  onMove,
}: {
  disableDown: boolean;
  disableUp: boolean;
  labels: { down: string; up: string };
  onMove: (direction: SpaceOrderMoveDirection) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => onMove('up')}
        disabled={disableUp}
        className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
        title={labels.up}
      >
        <ArrowUp size={14} />
      </button>
      <button
        type="button"
        onClick={() => onMove('down')}
        disabled={disableDown}
        className="rounded-md border border-app-border p-1 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-30"
        title={labels.down}
      >
        <ArrowDown size={14} />
      </button>
    </div>
  );
}

function SpaceOrderListRow({
  folders,
  index,
  itemCount,
  labels,
  list,
  onMoveParent,
  onMoveStep,
}: {
  folders: readonly PmsFolder[];
  index: number;
  itemCount: number;
  labels: {
    moveDown: string;
    moveUp: string;
    root: string;
    taskCount: (count: number) => string;
  };
  list: SpaceOrderDraftList;
  onMoveParent: (listId: string, parentId: string | null) => void;
  onMoveStep: (listId: string, direction: SpaceOrderMoveDirection) => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
      <ListIcon size={14} className="shrink-0 text-app-ink/55" />
      <div className="min-w-0 flex-1">
        <div className="app-text-control-sm truncate text-app-ink">
          {list.name}
        </div>
        <div className="app-text-caption text-app-ink/40">
          {labels.taskCount(list.task_count)}
        </div>
      </div>
      <select
        value={list.folder_id ?? ROOT_VALUE}
        onChange={(event) =>
          onMoveParent(
            list.id,
            event.target.value === ROOT_VALUE ? null : event.target.value,
          )
        }
        className="app-field-input-sm max-w-40 shrink-0"
      >
        <option value={ROOT_VALUE}>{labels.root}</option>
        {folders.map((folder) => (
          <option key={folder.id} value={folder.id}>
            {folder.name}
          </option>
        ))}
      </select>
      <MoveStepButtons
        disableDown={index === itemCount - 1}
        disableUp={index === 0}
        labels={{ down: labels.moveDown, up: labels.moveUp }}
        onMove={(direction) => onMoveStep(list.id, direction)}
      />
    </div>
  );
}

function SpaceOrderDocRow({
  doc,
  index,
  itemCount,
  labels,
  onMoveStep,
}: {
  doc: SpaceOrderDraftDoc;
  index: number;
  itemCount: number;
  labels: {
    moveDown: string;
    moveUp: string;
    untitled: string;
  };
  onMoveStep: (docId: string, direction: SpaceOrderMoveDirection) => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
      <FileText size={14} className="shrink-0 text-app-ink/55" />
      <div className="min-w-0 flex-1">
        <div className="app-text-control-sm truncate text-app-ink">
          {doc.title || labels.untitled}
        </div>
      </div>
      <MoveStepButtons
        disableDown={index === itemCount - 1}
        disableUp={index === 0}
        labels={{ down: labels.moveDown, up: labels.moveUp }}
        onMove={(direction) => onMoveStep(doc.id, direction)}
      />
    </div>
  );
}

export function SpaceOrderEditorModal({
  isOpen,
  ...props
}: SpaceOrderEditorModalProps) {
  return isOpen ? <SpaceOrderEditorModalSession {...props} /> : null;
}

type SpaceOrderEditorModalSessionProps = Omit<
  SpaceOrderEditorModalProps,
  'isOpen'
>;

function SpaceOrderEditorModalSession(
  props: SpaceOrderEditorModalSessionProps,
) {
  return useSpaceOrderEditorModalElement(props);
}

function useSpaceOrderEditorModalElement({
  onClose,
  spaceName,
  folders,
  lists,
  docs,
  onSave,
}: SpaceOrderEditorModalSessionProps) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const orderedFolders = useMemo(
    () => sortSpaceOrderFolders(folders, locale),
    [folders, locale],
  );
  const [draft, setDraft] = useState(() =>
    createSpaceOrderDraft({ lists, docs }),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirtySummary = useMemo(
    () =>
      summarizeSpaceOrderDraftChanges({
        draft,
        originalLists: lists,
        originalDocs: docs,
      }),
    [docs, draft, lists],
  );
  const { changedCount, isDirty } = dirtySummary;

  function requestClose() {
    if (saving) return;
    if (isDirty && !window.confirm(t('pms.orderEditor.closeDirtyConfirm'))) {
      return;
    }
    onClose();
  }

  function moveListStep(listId: string, direction: 'up' | 'down') {
    setDraft((current) =>
      moveSpaceOrderDraftListStep(current, listId, direction),
    );
  }

  function moveListParent(listId: string, nextParentId: string | null) {
    setDraft((current) =>
      moveSpaceOrderDraftListParent(current, listId, nextParentId),
    );
  }

  function moveDocStep(docId: string, direction: 'up' | 'down') {
    setDraft((current) =>
      moveSpaceOrderDraftDocStep(current, docId, direction),
    );
  }

  async function handleSave() {
    if (saving || !isDirty) {
      onClose();
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(createSpaceOrderSavePayload(draft));
      onClose();
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : t('pms.orderEditor.saveFailed'),
      );
    } finally {
      setSaving(false);
    }
  }

  const rootLists = useMemo(
    () => getRootSpaceOrderDraftLists(draft, locale),
    [draft, locale],
  );
  const docsOrdered = useMemo(
    () => getOrderedSpaceOrderDraftDocs(draft, locale),
    [draft, locale],
  );

  return (
    <Dialog
      closeLabel={t('common:actions.close')}
      open
      onOpenChange={(open) => {
        if (!open) requestClose();
      }}
      title={t('pms.orderEditor.title', { spaceName })}
      maxWidth="max-w-5xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full items-center justify-between gap-3">
          <div className="app-text-caption text-app-ink/50">
            {isDirty
              ? t('pms.orderEditor.changedCount', { count: changedCount })
              : t('pms.orderEditor.noChanges')}
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={requestClose}
              disabled={saving}
            >
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
          <div className="app-text-control-sm text-app-ink">
            {t('pms.orderEditor.dedicatedEditor')}
          </div>
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
              <div className="app-text-control-sm text-app-ink">
                {t('pms.spaceOverview.lists')}
              </div>
              <div className="app-text-caption text-app-ink/50">
                {t('pms.orderEditor.listsDescription')}
              </div>
            </div>
            <div className="space-y-5 p-4">
              <div className="space-y-2">
                <div className="app-text-overline text-app-ink/40">
                  {t('pms.orderEditor.rootLists')}
                </div>
                {rootLists.length === 0 ? (
                  <OrderEditorEmptyBlock>
                    {t('pms.orderEditor.noRootLists')}
                  </OrderEditorEmptyBlock>
                ) : (
                  rootLists.map((list, index) => (
                    <SpaceOrderListRow
                      key={list.id}
                      folders={orderedFolders}
                      index={index}
                      itemCount={rootLists.length}
                      labels={{
                        moveDown: t('pms.orderEditor.moveDown'),
                        moveUp: t('pms.orderEditor.moveUp'),
                        root: t('pms.orderEditor.root'),
                        taskCount: (count) =>
                          t('pms.spaceOverview.taskCount', { count }),
                      }}
                      list={list}
                      onMoveParent={moveListParent}
                      onMoveStep={moveListStep}
                    />
                  ))
                )}
              </div>

              {orderedFolders.map((folder) => {
                const folderLists = getSpaceOrderDraftListsForParent(
                  draft,
                  folder.id,
                  locale,
                );
                return (
                  <div key={folder.id} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <FolderOpen size={14} className="text-app-ink/55" />
                      <div className="app-text-overline text-app-ink/50">
                        {folder.name}
                      </div>
                    </div>
                    {folderLists.length === 0 ? (
                      <OrderEditorEmptyBlock>
                        {t('pms.orderEditor.noFolderLists')}
                      </OrderEditorEmptyBlock>
                    ) : (
                      folderLists.map((list, index) => (
                        <SpaceOrderListRow
                          key={list.id}
                          folders={orderedFolders}
                          index={index}
                          itemCount={folderLists.length}
                          labels={{
                            moveDown: t('pms.orderEditor.moveDown'),
                            moveUp: t('pms.orderEditor.moveUp'),
                            root: t('pms.orderEditor.root'),
                            taskCount: (count) =>
                              t('pms.spaceOverview.taskCount', { count }),
                          }}
                          list={list}
                          onMoveParent={moveListParent}
                          onMoveStep={moveListStep}
                        />
                      ))
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-lg border border-app-border bg-app-bg">
            <div className="border-b border-app-border px-4 py-3">
              <div className="app-text-control-sm text-app-ink">
                {t('pms.spaceOverview.docs')}
              </div>
              <div className="app-text-caption text-app-ink/50">
                {t('pms.orderEditor.docsDescription')}
              </div>
            </div>
            <div className="space-y-2 p-4">
              {docsOrdered.length === 0 ? (
                <OrderEditorEmptyBlock>
                  {t('pms.spaceOverview.noDocCollections')}
                </OrderEditorEmptyBlock>
              ) : (
                docsOrdered.map((doc, index) => (
                  <SpaceOrderDocRow
                    key={doc.id}
                    doc={doc}
                    index={index}
                    itemCount={docsOrdered.length}
                    labels={{
                      moveDown: t('pms.orderEditor.moveDown'),
                      moveUp: t('pms.orderEditor.moveUp'),
                      untitled: t('pms.orderEditor.untitled'),
                    }}
                    onMoveStep={moveDocStep}
                  />
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </Dialog>
  );
}
