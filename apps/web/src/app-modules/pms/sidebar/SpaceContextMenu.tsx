import { Pencil, Trash2, Users } from 'lucide-react';
import type * as React from 'react';
import { useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import {
  useDismissOnOutside,
  useFloatingAnchorPosition,
} from './space-tree-floating';

type SpaceContextMenuProps = {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onRename?: () => void;
  onManageMembers: () => void;
  canManage: boolean;
  onDelete?: () => void;
};

export function SpaceContextMenu({
  open,
  anchorRef,
  onClose,
  onRename,
  onManageMembers,
  canManage,
  onDelete,
}: SpaceContextMenuProps) {
  const { t } = useTranslation('apps');
  const ref = useRef<HTMLDivElement>(null);
  const pos = useFloatingAnchorPosition(open, anchorRef);
  useDismissOnOutside(open, ref, onClose);

  if (!open) return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[9999] w-44 bg-app-bg border border-app-border rounded-lg shadow-xl py-1"
    >
      {onRename ? (
        <button
          type="button"
          onClick={() => {
            onRename();
            onClose();
          }}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
        >
          <Pencil size={14} className="text-app-ink/45" />
          <span className="app-text-control-sm text-app-ink">
            {t('common:actions.rename')}
          </span>
        </button>
      ) : null}
      <button
        type="button"
        onClick={() => {
          onManageMembers();
          onClose();
        }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <Users size={14} className="text-app-ink/45" />
        <span className="app-text-control-sm text-app-ink">
          {canManage
            ? t('pms.spaceMembers.titleSuffix')
            : t('pms.spaceMembers.viewMembers')}
        </span>
      </button>
      {onDelete ? (
        <button
          type="button"
          onClick={() => {
            onDelete();
            onClose();
          }}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
        >
          <Trash2 size={14} className="text-app-danger-text" />
          <span className="app-text-control-sm text-app-danger-text">
            {t('common:actions.delete')}
          </span>
        </button>
      ) : null}
    </div>,
    document.body,
  );
}
