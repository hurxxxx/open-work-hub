import { Loader2, Sparkles, ThumbsUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { BriefVersion } from '../../../api/image-wizard-api';
import {
  BRIEF_SECTION_ORDER,
  buildBriefTurnProjection,
  stripBriefBullet,
} from './brief-turn-model';

function BriefSection({
  label,
  lines,
}: {
  label: string;
  lines: string[];
}) {
  if (lines.length === 0) return null;
  const hasBullets = lines.some((line) => /^[-*]\s+/.test(line));
  return (
    <section className="border-t border-app-border/80 pt-3">
      <h4 className="mb-1 app-text-caption font-semibold uppercase tracking-normal text-app-ink/50">
        {label}
      </h4>
      {hasBullets ? (
        <ul className="space-y-1 app-text-body text-app-ink">
          {lines.map((line, index) => (
            <li key={`${line}-${index}`} className="flex gap-2">
              <span className="mt-2 size-1.5 shrink-0 rounded-full bg-app-accent" />
              <span>{stripBriefBullet(line)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="app-text-body whitespace-pre-wrap text-app-ink">
          {lines.join('\n')}
        </p>
      )}
    </section>
  );
}

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
  const { fallbackText, hasParsedSections, sections, title } =
    buildBriefTurnProjection(version.text, index);

  return (
    <article className="rounded-lg border border-app-border bg-app-surface p-4 shadow-sm">
      <header className="mb-2 flex items-center gap-2 app-text-caption text-app-ink/50">
        <Sparkles size={12} className="text-app-accent" />
        <span className="font-medium">v{index + 1}</span>
        {version.edit_instruction ? (
          <span className="line-clamp-1 italic">"{version.edit_instruction}"</span>
        ) : null}
      </header>
      {hasParsedSections ? (
        <div className="space-y-3">
          <div>
            <h3 className="app-text-heading-3 text-app-ink">{title}</h3>
          </div>
          {BRIEF_SECTION_ORDER.map((section) => (
            <BriefSection
              key={section}
              label={t(`ai.imageWizard.step4.briefSections.${section}`)}
              lines={sections[section]}
            />
          ))}
        </div>
      ) : (
        <pre className="app-text-body whitespace-pre-wrap break-words font-sans text-app-ink">
          {fallbackText}
        </pre>
      )}
      <div className="mt-3 flex items-center justify-end">
        <button
          type="button"
          onClick={onApprove}
          disabled={approveDisabled || approving}
          className={`flex items-center gap-1.5 rounded-md px-4 py-2 app-text-control-sm font-medium transition-colors ${
            isLatest
              ? 'bg-app-ink text-app-surface hover:bg-app-ink/90 disabled:border disabled:border-app-border disabled:bg-app-surface-sidebar disabled:text-app-ink/70 disabled:opacity-100'
              : 'border border-app-border text-app-ink hover:border-app-accent hover:text-app-accent disabled:text-app-ink/55 disabled:opacity-100'
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
