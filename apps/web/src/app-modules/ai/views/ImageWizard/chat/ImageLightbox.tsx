import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Download, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ImageLightboxProps {
  imageUrl: string;
  alt: string;
  title: string;
  downloadName: string;
  onClose: () => void;
}

export function ImageLightbox({
  imageUrl,
  alt,
  title,
  downloadName,
  onClose,
}: ImageLightboxProps) {
  const { t } = useTranslation('apps');

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-[100] flex flex-col bg-black/90 p-3 text-white sm:p-5"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="app-text-heading-3 min-w-0 truncate">{title}</h3>
        <div className="flex shrink-0 items-center gap-2">
          <a
            href={imageUrl}
            download={downloadName}
            className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-white/25 bg-white/10 text-white hover:bg-white/20"
            aria-label={t('ai.imageWizard.step4.downloadAction')}
          >
            <Download size={18} />
          </a>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-white/25 bg-white/10 text-white hover:bg-white/20"
            aria-label={t('ai.imageWizard.step4.closePreview')}
          >
            <X size={20} />
          </button>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <img src={imageUrl} alt={alt} className="max-h-full max-w-full object-contain" />
      </div>
    </div>,
    document.body,
  );
}

export default ImageLightbox;
