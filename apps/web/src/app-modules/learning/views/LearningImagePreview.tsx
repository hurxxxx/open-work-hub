import {
  useEffect,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

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

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-[10000] flex flex-col bg-black/90 p-3 text-white sm:p-5"
      data-testid="learning-image-preview-dialog"
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <h3 className="app-text-title min-w-0 truncate text-white">{title}</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('common:actions.close')}
          title={t('common:actions.close')}
          className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-white/25 bg-white/10 text-white transition-colors hover:bg-white/20"
        >
          <X size={20} />
        </button>
      </header>
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <img
          src={image.src}
          alt={image.alt ?? ''}
          className="max-h-full max-w-full object-contain"
        />
      </div>
    </div>,
    document.body,
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
