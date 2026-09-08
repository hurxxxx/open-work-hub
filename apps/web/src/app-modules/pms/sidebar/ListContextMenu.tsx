import {
  Archive,
  ArchiveRestore,
  Pencil,
  Settings,
  Trash2,
} from 'lucide-react';
import type * as React from 'react';
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';

import {
  useDismissOnOutside,
  useFloatingAnchorPosition,
} from './space-tree-floating';

type ListContextMenuProps = {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onArchive?: () => void;
  onDelete?: () => void;
  onRename?: () => void;
  onRestore?: () => void;
  onSettings?: () => void;
};

export function ListContextMenu({
  open,
  anchorRef,
  onClose,
  onArchive,
  onDelete,
  onRename,
  onRestore,
  onSettings,
}: ListContextMenuProps) {
  const { t } = useTranslation('apps');
  const ref = useRef<HTMLDivElement>(null);
  const pos = useFloatingAnchorPosition(open, anchorRef);
  useDismissOnOutside(open, ref, onClose);

  useEffect(() => {
    if (!open) return;
    ref.current
      ?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')
      ?.focus();
  }, [open]);

  if (
    !open ||
    (!onSettings && !onRename && !onArchive && !onRestore && !onDelete)
  )
    return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[9999] w-44 bg-app-bg border border-app-border rounded-lg shadow-xl py-1"
      role="menu"
      onKeyDown={(event) => {
        const items = Array.from(
          ref.current?.querySelectorAll<HTMLButtonElement>(
            '[role="menuitem"]:not(:disabled)',
          ) ?? [],
        );
        const currentIndex = items.indexOf(
          document.activeElement as HTMLButtonElement,
        );
        if (event.key === 'Escape') {
          event.preventDefault();
          onClose();
          anchorRef.current?.focus();
          return;
        }
        if (event.key === 'Tab') {
          onClose();
          return;
        }
        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          return;
        }
        event.preventDefault();
        const nextIndex =
          event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? items.length - 1
              : event.key === 'ArrowDown'
                ? (currentIndex + 1 + items.length) % items.length
                : (currentIndex - 1 + items.length) % items.length;
        items[nextIndex]?.focus();
      }}
    >
      {onSettings ? (
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onSettings();
            onClose();
          }}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
        >
          <Settings size={14} className="text-app-ink/45" />
          <span className="app-text-control-sm text-app-ink">
            {t('pms.actions.settings')}
          </span>
        </button>
      ) : null}
      {onRename ? (
        <button
          type="button"
          role="menuitem"
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
      {onRestore ? (
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onRestore();
            onClose();
          }}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
        >
          <ArchiveRestore size={14} className="text-app-ink/45" />
          <span className="app-text-control-sm text-app-ink">
            {t('pms.archive.restore')}
          </span>
        </button>
      ) : null}
      {onArchive ? (
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onArchive();
            onClose();
          }}
          className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
        >
          <Archive size={14} className="text-app-ink/45" />
          <span className="app-text-control-sm text-app-ink">
            {t('pms.archive.action')}
          </span>
        </button>
      ) : null}
      {onDelete ? (
        <button
          type="button"
          role="menuitem"
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
