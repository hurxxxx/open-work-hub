import { useState } from 'react';
import { Loader2, RefreshCw, Send, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { BriefVersion } from '../../../api/image-wizard-api';

interface ReviewBriefStepProps {
  briefVersions: BriefVersion[];
  briefStatus: 'drafting' | 'ready' | 'approved';
  generating: boolean;
  approving: boolean;
  hasInput: boolean;
  onGenerateBrief: (editInstruction?: string) => Promise<void>;
  onApprove: () => Promise<void>;
}

export function ReviewBriefStep({
  briefVersions,
  briefStatus,
  generating,
  approving,
  hasInput,
  onGenerateBrief,
  onApprove,
}: ReviewBriefStepProps) {
  const { t } = useTranslation('apps');
  const [editText, setEditText] = useState('');
  const latest = briefVersions[briefVersions.length - 1];

  async function handleEdit() {
    const trimmed = editText.trim();
    if (!trimmed) return;
    await onGenerateBrief(trimmed);
    setEditText('');
  }

  if (!latest) {
    return (
      <div className="space-y-3">
        <p className="app-text-caption text-app-ink/60">
          {t('ai.imageWizard.steps.review.empty')}
        </p>
        <button
          type="button"
          onClick={() => onGenerateBrief()}
          disabled={generating || !hasInput}
          className="flex items-center gap-2 rounded-md bg-app-accent px-4 py-2 app-text-control-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
        >
          {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          {t('ai.imageWizard.steps.review.generateInitial')}
        </button>
        {!hasInput ? (
          <p className="app-text-caption text-app-ink/40">
            {t('ai.imageWizard.steps.review.needsInput')}
          </p>
        ) : null}
      </div>
    );
  }

  const isApproved = briefStatus === 'approved';

  return (
    <div className="space-y-4">
      <div className="space-y-2 rounded-md border border-app-border bg-app-surface-sidebar p-4 text-app-ink">
        <pre className="app-text-body whitespace-pre-wrap break-words font-sans text-app-ink">
          {latest.text}
        </pre>
        <p className="app-text-caption text-app-ink/40">
          {t('ai.imageWizard.steps.review.versionMeta', {
            count: briefVersions.length,
          })}
        </p>
      </div>

      {!isApproved ? (
        <div className="space-y-2">
          <label className="app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.steps.review.editLabel')}
          </label>
          <div className="flex gap-2">
            <textarea
              value={editText}
              rows={2}
              onChange={(event) => setEditText(event.target.value)}
              placeholder={t('ai.imageWizard.steps.review.editPlaceholder')}
              className="app-text-body flex-1 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
            />
            <button
              type="button"
              onClick={handleEdit}
              disabled={generating || !editText.trim()}
              className="flex items-center gap-1 rounded-md bg-app-accent px-3 py-2 app-text-control-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {generating ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              {t('ai.imageWizard.steps.review.applyEdit')}
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={() => onGenerateBrief()}
              disabled={generating}
              className="flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control-sm text-app-ink transition-colors hover:border-app-accent hover:text-app-accent disabled:opacity-50"
            >
              {generating ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {t('ai.imageWizard.steps.review.regenerate')}
            </button>
            <button
              type="button"
              onClick={onApprove}
              disabled={approving || briefStatus !== 'ready'}
              className="ml-auto flex items-center gap-2 rounded-md bg-[var(--ui-color-success,green)] px-4 py-2 app-text-control-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {approving ? <Loader2 size={14} className="animate-spin" /> : null}
              {t('ai.imageWizard.steps.review.approve')}
            </button>
          </div>
        </div>
      ) : (
        <p className="app-text-control-sm rounded-md bg-app-surface-hover px-3 py-2 text-app-ink/60">
          {t('ai.imageWizard.steps.review.approvedNotice')}
        </p>
      )}

      {briefVersions.length > 1 ? (
        <details className="rounded-md border border-app-border bg-app-surface-sidebar p-3">
          <summary className="cursor-pointer app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.steps.review.history')}
          </summary>
          <ul className="mt-2 space-y-2">
            {briefVersions.slice(0, -1).map((version, index) => (
              <li key={index} className="space-y-1 rounded bg-app-surface-hover p-2">
                <p className="app-text-caption text-app-ink/40">
                  v{index + 1}
                  {version.edit_instruction
                    ? ` · ${version.edit_instruction}`
                    : ''}
                </p>
                <pre className="app-text-caption whitespace-pre-wrap text-app-ink/70">
                  {version.text}
                </pre>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

export default ReviewBriefStep;
