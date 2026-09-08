import { Image as ImageIcon } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { MailMessageDetail } from '../api/mail-api';
import { buildMailHtmlDocument } from './mail-html-document';

export {
  buildMailHtmlDocument,
  extractMailPreviewText,
} from './mail-html-document';
export type { MailHtmlDocument } from './mail-html-document';

const remoteImageButtonClassName =
  'inline-flex h-8 items-center gap-2 rounded-md border border-app-border bg-app-bg px-3 app-text-control text-app-ink transition-colors hover:bg-app-surface-muted';

export function MailBodyRenderer({
  body,
}: {
  body: MailMessageDetail['body'];
}) {
  const { t } = useTranslation('apps');
  const [allowRemoteImages, setAllowRemoteImages] = useState(true);
  const htmlBody = body.html_body.trim();
  const textBody = body.text_body;
  const rendered = useMemo(
    () => buildMailHtmlDocument(htmlBody, { allowRemoteImages }),
    [allowRemoteImages, htmlBody],
  );

  if (!htmlBody) {
    return (
      <div className="mt-4 rounded-md border border-app-border bg-app-bg p-4">
        <pre className="whitespace-pre-wrap font-sans app-text-body leading-6">
          {textBody}
        </pre>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-md border border-app-border bg-white">
      {!allowRemoteImages && rendered.blockedRemoteImageCount > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-app-border bg-app-surface px-3 py-2">
          <span className="app-text-caption text-app-ink/60">
            {t('mail.body.remoteImagesBlocked', {
              count: rendered.blockedRemoteImageCount,
            })}
          </span>
          <button
            className={remoteImageButtonClassName}
            onClick={() => setAllowRemoteImages(true)}
            type="button"
          >
            <ImageIcon size={15} />
            <span>{t('mail.body.showRemoteImages')}</span>
          </button>
        </div>
      ) : null}
      <iframe
        className="h-[620px] w-full rounded-b-md border-0 bg-white"
        referrerPolicy="no-referrer"
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        srcDoc={rendered.srcDoc}
        title={t('mail.body.htmlFrameTitle')}
      />
    </div>
  );
}
