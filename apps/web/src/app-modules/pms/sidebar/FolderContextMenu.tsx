import { useRef } from 'react';
import type * as React from 'react';
import { createPortal } from 'react-dom';
import { ArrowDown, ArrowUp, Pencil, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  useDismissOnOutside,
  useFloatingAnchorPosition,
} from './space-tree-floating';

type FolderContextMenuProps = {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  canMoveUp?: boolean;
  canMoveDown?: boolean;
  onRename: () => void;
  onDelete: () => void;
};

export function FolderContextMenu({
  open,
  anchorRef,
  onClose,
  onMoveUp,
  onMoveDown,
  canMoveUp = false,
  canMoveDown = false,
  onRename,
  onDelete,
}: FolderContextMenuProps) {
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
      {onMoveUp ? (
        <button
          type="button"
          onClick={() => {
            onMoveUp();
            onClose();
          }}
          disabled={!canMoveUp}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowUp size={14} className="text-app-ink/45" />
          <span className="app-text-control-sm text-app-ink">
            {t('pms.orderEditor.moveUp')}
          </span>
        </button>
      ) : null}
      {onMoveDown ? (
        <button
          type="button"
          onClick={() => {
            onMoveDown();
            onClose();
          }}
          disabled={!canMoveDown}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowDown size={14} className="text-app-ink/45" />
          <span className="app-text-control-sm text-app-ink">
            {t('pms.orderEditor.moveDown')}
          </span>
        </button>
      ) : null}
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
    </div>,
    document.body,
  );
}
