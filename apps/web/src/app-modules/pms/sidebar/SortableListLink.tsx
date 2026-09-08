import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { List as ListIcon, MoreHorizontal } from 'lucide-react';
import type * as React from 'react';
import { useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { cn } from '@/src/lib/utils';
import type { PmsTaskList } from '../api/pms-api';
import { taskListRoleAllows } from '../api/pms-permissions';
import type { FlatDropZone } from '../api/pms-sidebar-reorder';
import { buildPmsTaskListToolPath } from '../views/pms-view-route';
import { ListContextMenu } from './ListContextMenu';
import { useSuppressClickAfterDrag } from './space-tree-drag';

export type SortableListMenuState = {
  buttonRefs: React.MutableRefObject<Map<string, HTMLButtonElement>>;
  isOpen: boolean;
  onClose: () => void;
  onToggle: () => void;
};

type SortableListLinkProps = {
  list: PmsTaskList;
  activeNavItemId: string;

  canDrag: boolean;
  dropZone: FlatDropZone | null;
  menu?: SortableListMenuState;
  onArchive?: () => void;
  onDelete?: () => void;
  onRename?: () => void;
  onRestore?: () => void;
  onSettings?: () => void;
};

export function SortableListLink({
  list,
  activeNavItemId,
  canDrag,
  dropZone,
  menu,
  onArchive,
  onDelete,
  onRename,
  onRestore,
  onSettings,
}: SortableListLinkProps) {
  const { t } = useTranslation('apps');
  const navigate = useNavigate();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: list.id,
    disabled: !canDrag,
    data: { kind: 'list', parentId: list.folder_id ?? null },
  });
  const suppressClick = useSuppressClickAfterDrag(isDragging);
  const canManageList = Boolean(
    menu &&
      taskListRoleAllows(list.role, 'admin') &&
      (list.archived
        ? onDelete || onRestore
        : onSettings || onArchive || onRename),
  );
  const handleOpenList = useCallback(
    (event: React.MouseEvent<HTMLButtonElement>) => {
      suppressClick(event);
      if (event.defaultPrevented) return;
      navigate(
        buildPmsTaskListToolPath({
          taskListId: list.id,
        }),
      );
    },
    [list.id, navigate, suppressClick],
  );
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn(
        'group/list relative flex items-center',
        isDragging && 'opacity-30',
        canDrag && 'touch-none',
      )}
    >
      {dropZone === 'before' ? (
        <div className="pointer-events-none absolute inset-x-1 top-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
      <button
        type="button"
        onClick={handleOpenList}
        className={cn(
          'sidebar-submenu-item flex-1 min-w-0 text-left',
          activeNavItemId === `pms-list-${list.id}` &&
            'sidebar-submenu-item-active',
        )}
      >
        <ListIcon size={13} className="text-app-ink/55 shrink-0" />
        <span className="sidebar-submenu-label">{list.name}</span>
        <span className="sidebar-submenu-meta">({list.task_count})</span>
      </button>
      {canManageList && menu ? (
        <>
          <div
            className={cn(
              'items-center gap-0.5 pr-1 shrink-0',
              menu.isOpen ? 'flex' : 'hidden group-hover/list:flex',
            )}
          >
            <button
              type="button"
              aria-label={t('pms.spaceTree.listManagement')}
              aria-expanded={menu.isOpen}
              aria-haspopup="menu"
              ref={(el) => {
                menuButtonRef.current = el;
                if (el) menu.buttonRefs.current.set(list.id, el);
                else menu.buttonRefs.current.delete(list.id);
              }}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                menu.onToggle();
              }}
              className="p-0.5 hover:bg-app-surface-hover rounded text-app-ink/70 dark:text-app-ink/80 hover:text-app-ink dark:hover:text-white transition-colors"
              title={t('pms.spaceTree.listManagement')}
            >
              <MoreHorizontal size={12} />
            </button>
          </div>
          <ListContextMenu
            open={menu.isOpen}
            anchorRef={menuButtonRef}
            onClose={menu.onClose}
            onArchive={list.archived ? undefined : onArchive}
            onSettings={list.archived ? undefined : onSettings}
            onRename={list.archived ? undefined : onRename}
            onRestore={list.archived ? onRestore : undefined}
            onDelete={list.archived ? onDelete : undefined}
          />
        </>
      ) : null}
      {dropZone === 'after' ? (
        <div className="pointer-events-none absolute inset-x-1 bottom-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
    </div>
  );
}
