import { Loader2, Sparkles, ThumbsUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { BriefVersion } from '../../../api/image-wizard-api';

interface BriefTurnProps {
  version: BriefVersion;
  index: number;
  isLatest: boolean;
  approving: boolean;
  approveDisabled: boolean;
  onApprove: () => void;
}

export function BriefTurn({
  version,
  index,
  isLatest,
  approving,
  approveDisabled,
  onApprove,
}: BriefTurnProps) {
  const { t } = useTranslation('apps');
  return (
    <article className="rounded-lg border border-app-border bg-app-surface p-4 shadow-sm">
      <header className="mb-2 flex items-center gap-2 app-text-caption text-app-ink/50">
        <Sparkles size={12} className="text-app-accent" />
        <span className="font-medium">v{index + 1}</span>
        {version.edit_instruction ? (
          <span className="line-clamp-1 italic">"{version.edit_instruction}"</span>
        ) : null}
      </header>
      <pre className="app-text-body whitespace-pre-wrap break-words font-sans text-app-ink">
        {version.text}
      </pre>
      <div className="mt-3 flex items-center justify-end">
        <button
          type="button"
          onClick={onApprove}
          disabled={approveDisabled || approving}
          className={`flex items-center gap-1.5 rounded-md px-4 py-2 app-text-control-sm font-medium transition-colors disabled:opacity-50 ${
            isLatest
              ? 'bg-app-accent text-white hover:opacity-90'
              : 'border border-app-border text-app-ink hover:border-app-accent hover:text-app-accent'
          }`}
        >
          {approving ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <ThumbsUp size={13} />
          )}
          {t('ai.imageWizard.step4.approveAction')}
        </button>
      </div>
    </article>
  );
}

export default BriefTurn;
