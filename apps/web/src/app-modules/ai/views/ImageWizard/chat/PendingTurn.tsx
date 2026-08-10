import { Loader2, Square } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface PendingTurnProps {
  status: 'queued' | 'running';
  cancelling?: boolean;
  onCancel?: () => void;
}

export function PendingTurn({ status, cancelling = false, onCancel }: PendingTurnProps) {
  const { t } = useTranslation('apps');
  return (
    <article className="flex flex-wrap items-center gap-3 rounded-lg border border-app-border bg-app-surface-sidebar p-4 text-app-ink/70">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <Loader2 size={16} className="shrink-0 animate-spin text-app-accent" />
        <span className="app-text-control-sm">
          {status === 'queued'
            ? t('ai.imageWizard.step4.pendingQueued')
            : t('ai.imageWizard.step4.pendingRunning')}
        </span>
      </div>
      {onCancel ? (
        <button
          type="button"
          onClick={onCancel}
          disabled={cancelling}
          className="inline-flex items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-3 py-2 app-text-control-sm text-app-ink hover:border-[var(--ui-color-danger)] hover:text-[var(--ui-color-danger)] disabled:opacity-60"
        >
          {cancelling ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Square size={13} />
          )}
          {t('ai.imageWizard.step4.cancelAction')}
        </button>
      ) : null}
    </article>
  );
}
