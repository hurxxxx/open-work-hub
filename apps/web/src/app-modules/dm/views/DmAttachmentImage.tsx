import { InlineNotice } from '@open-work-hub/ui/feedback/inline-notice';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { authenticatedContentObjectUrl } from '@/src/platform/browser/browser-download';
import { getDmAttachmentPreviewUrl } from '../api/dm-api';

function ImageContent({
  token,
  attachmentId,
  alt,
  className,
}: {
  token: string | null;
  attachmentId: string;
  alt: string;
  className: string;
}) {
  const { t } = useTranslation('apps');
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    void getDmAttachmentPreviewUrl(token, attachmentId)
      .then(async (response) => {
        if (cancelled) return;
        const resolved = await authenticatedContentObjectUrl(
          token,
          response.url,
        );
        if (cancelled) {
          URL.revokeObjectURL(resolved);
          return;
        }
        objectUrl = resolved;
        setSrc(resolved);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [attachmentId, token]);
  if (failed)
    return (
      <InlineNotice tone="warning">
        {t('dm.errors.attachmentPreviewFailed')}
      </InlineNotice>
    );
  return src ? (
    <img alt={alt} className={className} src={src} />
  ) : (
    <span role="status">{t('common:feedback.loading')}</span>
  );
}
/** URLs are fetched for the current session and never appear in image sources. */
export function DmAttachmentImage(props: Parameters<typeof ImageContent>[0]) {
  return (
    <ImageContent
      key={[props.token, props.attachmentId].join(':')}
      {...props}
    />
  );
}
