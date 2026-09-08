import { X } from 'lucide-react';
import { useEffect, type CSSProperties, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';

type FullscreenImageDialogProps = {
  alt: string;
  src: string;
  title: string;
  onClose: () => void;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  contentClassName?: string;
  closeLabel?: string;
  dialogTestId?: string;
  contentTestId?: string;
  imageClassName?: string;
  imageStyle?: CSSProperties;
  imageTestId?: string;
  titleClassName?: string;
  zIndexClassName?: string;
};

export function FullscreenImageDialog({
  actions,
  alt,
  children,
  className,
  closeLabel,
  contentClassName,
  contentTestId,
  dialogTestId,
  imageClassName,
  imageStyle,
  imageTestId,
  onClose,
  src,
  title,
  titleClassName,
  zIndexClassName = 'z-[10000]',
}: FullscreenImageDialogProps) {
  const { t } = useTranslation('common');
  const resolvedCloseLabel = closeLabel ?? t('actions.close');

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  useEffect(() => {
    if (typeof document === 'undefined') {
      return;
    }
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  if (typeof document === 'undefined') {
    return null;
  }

  return createPortal(
    <dialog
      open
      aria-label={title}
      className={cn(
        'fixed inset-0 m-0 flex h-screen max-h-none w-screen max-w-none flex-col border-0 bg-black/90 p-3 text-white sm:p-5',
        zIndexClassName,
        className,
      )}
      data-testid={dialogTestId}
    >
      <header className="mb-3 flex flex-wrap items-center gap-3">
        <h2
          className={cn(
            'min-w-0 flex-1 truncate text-white',
            titleClassName ?? 'app-text-title',
          )}
        >
          {title}
        </h2>
        {actions ? (
          <div className="flex shrink-0 items-center gap-2">{actions}</div>
        ) : null}
        <button
          type="button"
          onClick={onClose}
          aria-label={resolvedCloseLabel}
          title={resolvedCloseLabel}
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-md border border-white/25 bg-white/10 text-white transition-colors hover:bg-white/20"
        >
          <X size={20} />
        </button>
      </header>
      <div
        data-testid={contentTestId}
        className={
          contentClassName ?? 'flex min-h-0 flex-1 items-center justify-center'
        }
      >
        {children ?? (
          <img
            data-testid={imageTestId}
            src={src}
            alt={alt}
            className={cn(
              'max-h-full max-w-full object-contain',
              imageClassName,
            )}
            style={imageStyle}
          />
        )}
      </div>
    </dialog>,
    document.body,
  );
}
