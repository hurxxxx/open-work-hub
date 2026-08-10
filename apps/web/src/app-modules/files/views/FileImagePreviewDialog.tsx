import { useState } from 'react';
import { RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { FullscreenImageDialog } from '@/src/components/media/FullscreenImageDialog';
import { cn } from '@/src/lib/utils';
import type { FileItem } from '../api/files-api';
import {
  IMAGE_PREVIEW_ZOOM_MAX,
  IMAGE_PREVIEW_ZOOM_MIN,
  IMAGE_PREVIEW_ZOOM_STEP,
  clampImagePreviewZoom,
} from './file-manager-view-model';

type FileImagePreviewDialogProps = {
  file: FileItem;
  onClose: () => void;
  url: string;
};

export function FileImagePreviewDialog({
  file,
  onClose,
  url,
}: FileImagePreviewDialogProps) {
  const { t } = useTranslation(['apps', 'common']);
  const [zoom, setZoom] = useState(1);
  const zoomPercent = `${Math.round(zoom * 100)}%`;

  function adjustZoom(delta: number) {
    setZoom((current) => clampImagePreviewZoom(current + delta));
  }

  return (
    <FullscreenImageDialog
      src={url}
      alt={file.filename}
      title={file.filename}
      onClose={onClose}
      actions={
        <fieldset
          className="flex h-10 shrink-0 items-center rounded-md border border-white/15 bg-white/10 p-1"
          aria-label={t('files.preview.zoomControls')}
        >
          <button
            type="button"
            onClick={() => adjustZoom(-IMAGE_PREVIEW_ZOOM_STEP)}
            disabled={zoom <= IMAGE_PREVIEW_ZOOM_MIN}
            aria-label={t('files.preview.zoomOut')}
            title={t('files.preview.zoomOut')}
            className="inline-flex size-8 items-center justify-center rounded text-white/75 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ZoomOut size={16} />
          </button>
          <span
            data-testid="files-image-preview-zoom-label"
            className="app-text-control-sm w-14 text-center tabular-nums text-white/85"
            aria-live="polite"
          >
            {zoomPercent}
          </span>
          <button
            type="button"
            onClick={() => adjustZoom(IMAGE_PREVIEW_ZOOM_STEP)}
            disabled={zoom >= IMAGE_PREVIEW_ZOOM_MAX}
            aria-label={t('files.preview.zoomIn')}
            title={t('files.preview.zoomIn')}
            className="inline-flex size-8 items-center justify-center rounded text-white/75 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ZoomIn size={16} />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            disabled={zoom === 1}
            aria-label={t('files.preview.resetZoom')}
            title={t('files.preview.resetZoom')}
            className="ml-1 inline-flex size-8 items-center justify-center rounded border-l border-white/15 text-white/75 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
          >
            <RotateCcw size={15} />
          </button>
        </fieldset>
      }
      closeLabel={t('common:actions.close')}
      className="h-auto"
      contentTestId="files-image-preview-scroll"
      contentClassName="min-h-0 flex-1 overflow-auto rounded-md bg-black/20"
    >
      <div className="min-h-full min-w-full">
        <div
          className={cn(
            'min-h-full min-w-full p-6',
            zoom <= 1
              ? 'flex items-center justify-center'
              : 'flex items-start justify-start',
          )}
        >
          <img
            data-testid="files-image-preview-image"
            src={url}
            alt={file.filename}
            className={cn(
              'h-auto object-contain',
              zoom === 1 ? 'max-h-full max-w-full' : 'max-w-none',
            )}
            style={zoom === 1 ? undefined : { width: `${zoom * 100}%` }}
          />
        </div>
      </div>
    </FullscreenImageDialog>
  );
}
