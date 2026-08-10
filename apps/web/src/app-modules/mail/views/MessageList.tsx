import { Inbox, Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { MailMessage } from '../api/mail-api';
import { extractMailPreviewText } from './MailBodyRenderer';
import { formatMailDate } from './mail-view-model';

export function MessageList({
  locale,
  messages,
  selectedId,
  timeZone,
  onSelect,
  onStar,
}: {
  locale: string;
  messages: MailMessage[];
  selectedId: string | null;
  timeZone: string;
  onSelect: (id: string) => void;
  onStar: (message: MailMessage) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <section className="min-h-0 overflow-auto border-r border-app-border">
      {messages.length === 0 ? (
        <div className="p-5 text-center text-app-ink/55">
          <Inbox className="mx-auto mb-2 size-8" />
          <p className="app-text-body">{t('mail.empty')}</p>
        </div>
      ) : (
        messages.map((message) => {
          const preview = extractMailPreviewText(message.snippet);
          const rowTone = message.is_read ? 'text-app-ink/70' : 'text-app-ink';
          const rowBg = selectedId === message.id ? 'bg-app-surface-muted' : 'bg-app-bg';
          return (
            <div
              className={`flex border-b border-app-border transition-colors hover:bg-app-surface-muted ${rowBg} ${rowTone}`}
              key={message.id}
            >
              <button
                className="min-w-0 flex-1 p-3 text-left"
                onClick={() => onSelect(message.id)}
                type="button"
              >
                <div className="min-w-0">
                  <p className="truncate app-text-control">{message.from_text || t('mail.unknownSender')}</p>
                  <p className="mt-1 truncate app-text-body font-medium">{message.subject || t('mail.noSubject')}</p>
                </div>
                {preview ? (
                  <p className="mt-1 line-clamp-2 app-text-caption text-app-ink/55">{preview}</p>
                ) : null}
                <p className="mt-2 app-text-caption text-app-ink/40">
                  {formatMailDate(message.received_at, locale, timeZone)}
                </p>
              </button>
              <div className="shrink-0 px-2 py-3">
                <button
                  aria-label={t('mail-starred')}
                  className="rounded p-1 text-app-ink/45 hover:text-app-accent"
                  onClick={() => onStar(message)}
                  type="button"
                >
                  <Star size={15} fill={message.is_starred ? 'currentColor' : 'none'} />
                </button>
              </div>
            </div>
          );
        })
      )}
    </section>
  );
}
