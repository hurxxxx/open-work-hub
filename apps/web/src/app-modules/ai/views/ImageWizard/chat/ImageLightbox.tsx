import { Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { FullscreenImageDialog } from '@/src/components/media/FullscreenImageDialog';

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

  return (
    <FullscreenImageDialog
      src={imageUrl}
      alt={alt}
      title={title}
      onClose={onClose}
      zIndexClassName="z-[100]"
      titleClassName="app-text-heading-3"
      closeLabel={t('ai.imageWizard.step4.closePreview')}
      actions={
        <a
          href={imageUrl}
          download={downloadName}
          className="inline-flex size-10 items-center justify-center rounded-md border border-white/25 bg-white/10 text-white hover:bg-white/20"
          aria-label={t('ai.imageWizard.step4.downloadAction')}
        >
          <Download size={18} />
        </a>
      }
    />
  );
}
