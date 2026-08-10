import { useTranslation } from 'react-i18next';

import type { MailDraft } from '../api/mail-api';

export function DraftList({
  drafts,
  selectedId,
  onSelect,
}: {
  drafts: MailDraft[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <section className="min-h-0 overflow-auto border-r border-app-border">
      {drafts.length === 0 ? (
        <div className="p-5 text-center text-app-ink/55">{t('mail.draft.empty')}</div>
      ) : (
        drafts.map((draft) => (
          <button
            className={`block w-full border-b border-app-border px-3 py-3 text-left ${
              selectedId === draft.id ? 'bg-app-surface-muted' : 'bg-app-bg'
            }`}
            key={draft.id}
            onClick={() => onSelect(draft.id)}
            type="button"
          >
            <p className="truncate app-text-control">{draft.to_text || t('mail.draft.noRecipient')}</p>
            <p className="mt-1 truncate app-text-body">{draft.subject || t('mail.noSubject')}</p>
            <p className="mt-1 app-text-caption text-app-ink/50">
              {t(`mail.draft.status.${draft.status}`, { defaultValue: draft.status })}
            </p>
          </button>
        ))
      )}
    </section>
  );
}
