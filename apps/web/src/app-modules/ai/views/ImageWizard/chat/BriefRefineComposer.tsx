import { useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface BriefRefineComposerProps {
  disabled: boolean;
  busy: boolean;
  onSend: (instruction: string) => Promise<void>;
}

export function BriefRefineComposer({ disabled, busy, onSend }: BriefRefineComposerProps) {
  const { t } = useTranslation('apps');
  const [text, setText] = useState('');

  async function submit() {
    const trimmed = text.trim();
    if (!trimmed) return;
    await onSend(trimmed);
    setText('');
  }

  return (
    <div className="space-y-2">
      <p className="app-text-caption text-app-ink/50">
        {t('ai.imageWizard.step4.composerHelper')}
      </p>
      <div className="flex gap-2">
        <textarea
          value={text}
          rows={2}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder={t('ai.imageWizard.step4.composerPlaceholder')}
          className="app-text-body flex-1 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none disabled:opacity-60"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || busy || !text.trim()}
          className="flex items-center gap-1 rounded-md bg-app-accent px-3 py-2 app-text-control-sm font-medium text-white transition-colors hover:opacity-90 disabled:border disabled:border-app-border disabled:bg-app-surface-sidebar disabled:text-app-ink/65 disabled:opacity-100"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          {t('ai.imageWizard.step4.sendRefinement')}
        </button>
      </div>
    </div>
  );
}

export default BriefRefineComposer;
