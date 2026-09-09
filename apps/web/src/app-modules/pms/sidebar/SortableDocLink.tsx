import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { FileText, MoreHorizontal } from 'lucide-react';
import type * as React from 'react';
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import type { DocsHubItem } from '@/src/app-modules/docs/public-api';
import { cn } from '@/src/lib/utils';
import type { FlatDropZone } from '../api/pms-sidebar-reorder';
import { buildPmsSpaceDocsToolPath } from '../views/pms-view-route';
import { FolderContextMenu } from './FolderContextMenu';
import { useSuppressClickAfterDrag } from './space-tree-drag';
import { getSpaceDocSpaceId } from './space-tree-model';

export type SortableDocPermissions = {
  canDrag: boolean;
  canManageCollections: boolean;
};

export type SortableDocRenameState = {
  inputRef: React.RefObject<HTMLInputElement | null>;
  isRenaming: boolean;
  onBegin: () => void;
  onCancel: () => void;
  onCommit: () => void;
  onValueChange: (value: string) => void;
  value: string;
};

export type SortableDocMenuState = {
  buttonRefs: React.MutableRefObject<Map<string, HTMLButtonElement>>;
  isOpen: boolean;
  onClose: () => void;
  onToggle: () => void;
};

type SortableDocLinkProps = {
  doc: DocsHubItem;
  spaceId: string;
  activeNavItemId: string;

  dropZone: FlatDropZone | null;
  menu: SortableDocMenuState;
  onDelete: () => void;
  permissions: SortableDocPermissions;
  rename: SortableDocRenameState;
};

export function SortableDocLink({
  doc,
  spaceId,
  activeNavItemId,
  dropZone,
  menu,
  onDelete,
  permissions,
  rename,
}: SortableDocLinkProps) {
  const { t } = useTranslation('apps');
  const navigate = useNavigate();
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: doc.id,
    disabled: !permissions.canDrag || rename.isRenaming,
    data: { kind: 'doc', parentId: getSpaceDocSpaceId(doc) },
  });
  const suppressClick = useSuppressClickAfterDrag(isDragging);
  const style = { transform: CSS.Transform.toString(transform), transition };
  const docNavId = `pms-space-${spaceId}-docs-${doc.id}`;
  const handleOpenDoc = useCallback(
    (event: React.MouseEvent<HTMLButtonElement>) => {
      suppressClick(event);
      if (event.defaultPrevented) return;
      navigate(
        buildPmsSpaceDocsToolPath({
          docId: doc.id,
          spaceId,
        }),
      );
    },
    [doc.id, navigate, spaceId, suppressClick],
  );
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn(
        'group/doc relative flex items-center',
        isDragging && 'opacity-30',
        permissions.canDrag && !rename.isRenaming && 'touch-none',
      )}
    >
      {dropZone === 'before' ? (
        <div className="pointer-events-none absolute inset-x-1 top-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
      {rename.isRenaming ? (
        <div className="sidebar-submenu-item flex-1 min-w-0">
          <FileText size={13} className="text-app-ink/55 shrink-0" />
          <input
            aria-label={t('common:actions.rename')}
            ref={rename.inputRef}
            value={rename.value}
            onChange={(e) => rename.onValueChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') rename.onCommit();
              else if (e.key === 'Escape') rename.onCancel();
            }}
            onBlur={rename.onCommit}
            className="app-text-body-sm flex-1 min-w-0 rounded border border-blue-500 bg-transparent px-1 py-0.5 text-app-ink outline-none"
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={handleOpenDoc}
          className={cn(
            'sidebar-submenu-item flex-1 min-w-0 text-left',
            activeNavItemId === docNavId && 'sidebar-submenu-item-active',
          )}
        >
          <FileText size={13} className="text-app-ink/55 shrink-0" />
          <span className="sidebar-submenu-label">
            {doc.title || t('pms.orderEditor.untitled')}
          </span>
        </button>
      )}
      {permissions.canManageCollections && !rename.isRenaming ? (
        <>
          <div
            className={cn(
              'items-center gap-0.5 pr-1 shrink-0',
              menu.isOpen ? 'flex' : 'hidden group-hover/doc:flex',
            )}
          >
            <button
              type="button"
              aria-label={t('pms.spaceTree.docOptions')}
              ref={(el) => {
                if (el) menu.buttonRefs.current.set(doc.id, el);
              }}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                menu.onToggle();
              }}
              className="p-0.5 hover:bg-app-surface-hover rounded text-app-ink/70 dark:text-app-ink/80 hover:text-app-ink dark:hover:text-white transition-colors"
              title={t('pms.spaceTree.docOptions')}
            >
              <MoreHorizontal size={12} />
            </button>
          </div>
          <FolderContextMenu
            open={menu.isOpen}
            anchorRef={{ current: menu.buttonRefs.current.get(doc.id) ?? null }}
            onClose={menu.onClose}
            onRename={rename.onBegin}
            onDelete={onDelete}
          />
        </>
      ) : null}
      {dropZone === 'after' ? (
        <div className="pointer-events-none absolute inset-x-1 bottom-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
    </div>
  );
}
