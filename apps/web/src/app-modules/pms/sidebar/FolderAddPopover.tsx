import { useRef } from 'react';
import type * as React from 'react';
import { createPortal } from 'react-dom';
import { FileText, List as ListIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  useDismissOnOutside,
  useFloatingAnchorPosition,
} from './space-tree-floating';

type FolderAddPopoverProps = {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onCreateList: () => void;
  onCreateDoc: () => void;
};

export function FolderAddPopover({
  open,
  anchorRef,
  onClose,
  onCreateList,
  onCreateDoc,
}: FolderAddPopoverProps) {
  const { t } = useTranslation('apps');
  const ref = useRef<HTMLDivElement>(null);
  const pos = useFloatingAnchorPosition(open, anchorRef);
  useDismissOnOutside(open, ref, onClose);

  if (!open) return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[9999] w-48 bg-app-bg border border-app-border rounded-lg shadow-xl py-1"
    >
      <div className="app-text-overline px-3 py-1.5 text-app-ink/55">
        {t('common:actions.create')}
      </div>
      <button
        type="button"
        onClick={() => {
          onCreateList();
          onClose();
        }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <ListIcon size={14} className="text-app-ink/45" />
        <div className="app-text-control-sm text-app-ink">
          {t('pms.spaceTree.list')}
        </div>
      </button>
      <button
        type="button"
        onClick={() => {
          onCreateDoc();
          onClose();
        }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <FileText size={14} className="text-app-ink/45" />
        <div className="app-text-control-sm text-app-ink">
          {t('pms.spaceTree.doc')}
        </div>
      </button>
    </div>,
    document.body,
  );
}
