import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface PendingTurnProps {
  status: 'queued' | 'running';
}

export function PendingTurn({ status }: PendingTurnProps) {
  const { t } = useTranslation('apps');
  return (
    <article className="flex items-center gap-3 rounded-lg border border-app-border bg-app-surface-sidebar p-4 text-app-ink/70">
      <Loader2 size={16} className="animate-spin text-app-accent" />
      <span className="app-text-control-sm">
        {status === 'queued'
          ? t('ai.imageWizard.step4.pendingQueued')
          : t('ai.imageWizard.step4.pendingRunning')}
      </span>
    </article>
  );
}

export default PendingTurn;
