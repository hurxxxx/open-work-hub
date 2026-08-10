import {
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';

import { FullscreenImageDialog } from '@/src/components/media/FullscreenImageDialog';

export interface LearningImagePreview {
  src: string;
  alt?: string;
}

export function LearningImagePreviewDialog({
  image,
  onClose,
}: {
  image: LearningImagePreview;
  onClose: () => void;
}) {
  const { t } = useTranslation('apps');
  const title = image.alt?.trim() || t('learning.imagePreview');

  return (
    <FullscreenImageDialog
      src={image.src}
      alt={image.alt ?? ''}
      title={title}
      onClose={onClose}
      dialogTestId="learning-image-preview-dialog"
    />
  );
}

export function LearningImagePreviewSurface({
  children,
  className,
  testId,
}: {
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  const [previewImage, setPreviewImage] = useState<LearningImagePreview | null>(
    null,
  );

  const openPreview = (image: HTMLImageElement) => {
    const src = image.currentSrc || image.src || image.getAttribute('src');
    if (!src) return;
    setPreviewImage({
      src,
      alt: image.alt || '',
    });
  };

  const handleClickCapture = (event: ReactMouseEvent<HTMLDivElement>) => {
    const image = getImageFromEventTarget(event.target);
    if (!image) return;
    event.preventDefault();
    event.stopPropagation();
    openPreview(image);
  };

  const handleKeyDownCapture = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const image = getImageFromEventTarget(event.target);
    if (!image) return;
    event.preventDefault();
    event.stopPropagation();
    openPreview(image);
  };

  return (
    <>
      <div
        className={
          className
            ? `learning-image-preview-surface ${className}`
            : 'learning-image-preview-surface'
        }
        data-testid={testId}
        onClickCapture={handleClickCapture}
        onKeyDownCapture={handleKeyDownCapture}
      >
        {children}
      </div>
      {previewImage ? (
        <LearningImagePreviewDialog
          image={previewImage}
          onClose={() => setPreviewImage(null)}
        />
      ) : null}
    </>
  );
}

function getImageFromEventTarget(
  target: EventTarget | null,
): HTMLImageElement | null {
  if (target instanceof HTMLImageElement) return target;
  if (target instanceof HTMLElement) {
    const image = target.closest('img');
    return image instanceof HTMLImageElement ? image : null;
  }
  return null;
}
