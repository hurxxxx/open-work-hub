import { Bot, MailPlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { MailMessageDetail } from '../api/mail-api';
import { MailBodyRenderer } from './MailBodyRenderer';
import {
  actionButtonClassName,
  fieldClassName,
  formatMailDate,
} from './mail-view-model';

export function MessageDetail({
  busy,
  detail,
  locale,
  replyInstruction,
  summary,
  timeZone,
  onCreateDraft,
  onInstructionChange,
  onSummarize,
}: {
  busy: boolean;
  detail: MailMessageDetail | null;
  locale: string;
  replyInstruction: string;
  summary: string;
  timeZone: string;
  onCreateDraft: () => void;
  onInstructionChange: (value: string) => void;
  onSummarize: () => void;
}) {
  const { t } = useTranslation('apps');
  if (!detail) {
    return (
      <section className="min-h-0 overflow-auto p-6 text-app-ink/50">
        {t('mail.selectMessage')}
      </section>
    );
  }
  return (
    <section className="min-h-0 overflow-auto p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="app-text-title-md">
            {detail.subject || t('mail.noSubject')}
          </h2>
          <p className="mt-1 app-text-body text-app-ink/60">
            {detail.from_text}
          </p>
          <p className="app-text-caption text-app-ink/45">
            {formatMailDate(detail.received_at, locale, timeZone)}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            className={actionButtonClassName}
            disabled={busy}
            onClick={onSummarize}
            type="button"
          >
            <Bot size={16} />
            <span>{t('mail.actions.summarize')}</span>
          </button>
        </div>
      </div>
      {summary ? (
        <div className="mt-4 rounded-md border border-app-border bg-app-surface p-3">
          <p className="app-text-caption mb-1 text-app-ink/50">
            {t('mail.summary')}
          </p>
          <p className="whitespace-pre-wrap app-text-body">{summary}</p>
        </div>
      ) : null}
      <MailBodyRenderer body={detail.body} />
      <div className="mt-4 grid gap-2">
        <textarea
          aria-label={t('mail.draft.instructionPlaceholder')}
          className={`${fieldClassName} min-h-20`}
          onChange={(event) => onInstructionChange(event.target.value)}
          placeholder={t('mail.draft.instructionPlaceholder')}
          value={replyInstruction}
        />
        <button
          className={actionButtonClassName}
          disabled={busy}
          onClick={onCreateDraft}
          type="button"
        >
          <MailPlus size={16} />
          <span>{t('mail.actions.createDraft')}</span>
        </button>
      </div>
    </section>
  );
}
