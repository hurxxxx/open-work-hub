import { FileText, FolderOpen, List as ListIcon } from 'lucide-react';
import type * as React from 'react';
import { useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import {
  useDismissOnOutside,
  useFloatingAnchorPosition,
} from './space-tree-floating';

type SpaceAddPopoverProps = {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onCreateList: () => void;
  onCreateFolder: () => void;
  onOpenDocs: () => void;
};

export function SpaceAddPopover({
  open,
  anchorRef,
  onClose,
  onCreateList,
  onCreateFolder,
  onOpenDocs,
}: SpaceAddPopoverProps) {
  const { t } = useTranslation('apps');
  const ref = useRef<HTMLDivElement>(null);
  const pos = useFloatingAnchorPosition(open, anchorRef);
  useDismissOnOutside(open, ref, onClose);

  if (!open) return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[9999] w-52 bg-app-bg border border-app-border rounded-lg shadow-xl py-1"
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
        <ListIcon size={16} className="text-app-ink/45" />
        <div className="text-left">
          <div className="app-text-control-sm text-app-ink">
            {t('pms.spaceTree.list')}
          </div>
          <div className="app-text-micro text-app-ink/40">
            {t('pms.spaceTree.listDescription')}
          </div>
        </div>
      </button>
      <button
        type="button"
        onClick={() => {
          onCreateFolder();
          onClose();
        }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <FolderOpen size={16} className="text-app-ink/45" />
        <div className="text-left">
          <div className="app-text-control-sm text-app-ink">
            {t('pms.spaceTree.folder')}
          </div>
          <div className="app-text-micro text-app-ink/40">
            {t('pms.spaceTree.folderDescription')}
          </div>
        </div>
      </button>
      <button
        type="button"
        onClick={() => {
          onOpenDocs();
          onClose();
        }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-app-surface-hover transition-colors"
      >
        <FileText size={16} className="text-app-ink/45" />
        <div className="text-left">
          <div className="app-text-control-sm text-app-ink">
            {t('pms.spaceTree.doc')}
          </div>
          <div className="app-text-micro text-app-ink/40">
            {t('pms.spaceTree.docDescription')}
          </div>
        </div>
      </button>
    </div>,
    document.body,
  );
}
