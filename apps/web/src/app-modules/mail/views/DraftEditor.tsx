import { Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { MailDraft } from '../api/mail-api';
import { actionButtonClassName, fieldClassName } from './mail-view-model';

export function DraftEditor({
  busy,
  draft,
  onChange,
  onSend,
}: {
  busy: boolean;
  draft: MailDraft | null;
  onChange: (draft: MailDraft | null) => void;
  onSend: (draft: MailDraft | null) => void;
}) {
  const { t } = useTranslation('apps');
  if (!draft) {
    return <section className="min-h-0 overflow-auto p-6 text-app-ink/50">{t('mail.draft.select')}</section>;
  }
  const set = (patch: Partial<MailDraft>) => onChange({ ...draft, ...patch });
  return (
    <section className="grid min-h-0 grid-rows-[auto_1fr_auto] gap-3 overflow-hidden p-5">
      <div className="grid gap-2">
        <input
          aria-label={t('mail.draft.to')}
          className={fieldClassName}
          onChange={(event) => set({ to_text: event.target.value })}
          placeholder={t('mail.draft.to')}
          value={draft.to_text}
        />
        <input
          aria-label={t('mail.draft.cc')}
          className={fieldClassName}
          onChange={(event) => set({ cc_text: event.target.value })}
          placeholder={t('mail.draft.cc')}
          value={draft.cc_text}
        />
        <input
          aria-label={t('mail.draft.bcc')}
          className={fieldClassName}
          onChange={(event) => set({ bcc_text: event.target.value })}
          placeholder={t('mail.draft.bcc')}
          value={draft.bcc_text}
        />
        <input
          aria-label={t('mail.draft.subject')}
          className={fieldClassName}
          onChange={(event) => set({ subject: event.target.value })}
          placeholder={t('mail.draft.subject')}
          value={draft.subject}
        />
      </div>
      <textarea
        aria-label={t('mail.body.htmlFrameTitle')}
        className={`${fieldClassName} min-h-0 resize-none leading-6`}
        onChange={(event) => set({ text_body: event.target.value })}
        value={draft.text_body}
      />
      <div className="flex items-center justify-between gap-3">
        <span className="app-text-caption text-app-ink/50">
          {t(`mail.draft.status.${draft.status}`, { defaultValue: draft.status })}
        </span>
        <button
          className={actionButtonClassName}
          disabled={busy || draft.status !== 'draft'}
          onClick={() => onSend(draft)}
          type="button"
        >
          <Send size={16} />
          <span>{t('mail.actions.send')}</span>
        </button>
      </div>
    </section>
  );
}
