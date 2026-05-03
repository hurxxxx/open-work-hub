import { Loader2, Sparkles, ThumbsUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { BriefVersion } from '../../../api/image-wizard-api';

type BriefSectionKey = 'title' | 'layout' | 'elements' | 'colors' | 'typography' | 'notes';

interface ParsedBrief {
  sections: Record<BriefSectionKey, string[]>;
  fallback: string[];
}

const SECTION_ORDER: BriefSectionKey[] = [
  'layout',
  'elements',
  'colors',
  'typography',
  'notes',
];

const SECTION_LABEL_ALIASES: Record<BriefSectionKey, string[]> = {
  title: ['TITLE', '\uc81c\ubaa9'],
  layout: ['LAYOUT', '\ud654\uba74 \uad6c\uc131', '\uad6c\uc131', '\ub808\uc774\uc544\uc6c3'],
  elements: [
    'KEY ELEMENTS',
    'KEY ELEMENT',
    '\ud575\uc2ec \uc694\uc18c',
    '\uc8fc\uc694 \uc694\uc18c',
  ],
  colors: ['COLORS', 'COLOR', '\uc0c9\uc0c1', '\uceec\ub7ec'],
  typography: ['TYPOGRAPHY', '\uae00\uc790 \uc2a4\ud0c0\uc77c', '\ud0c0\uc774\ud3ec\uadf8\ub798\ud53c'],
  notes: ['NOTES', 'NOTE', '\uc8fc\uc758\uc0ac\ud56d', '\uba54\ubaa8'],
};

function normalizeLabel(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toUpperCase();
}

function sectionKeyForLabel(label: string): BriefSectionKey | null {
  const normalized = normalizeLabel(label);
  for (const [key, aliases] of Object.entries(SECTION_LABEL_ALIASES)) {
    if (aliases.some((alias) => normalizeLabel(alias) === normalized)) {
      return key as BriefSectionKey;
    }
  }
  return null;
}

function parseBrief(text: string): ParsedBrief {
  const sections: Record<BriefSectionKey, string[]> = {
    title: [],
    layout: [],
    elements: [],
    colors: [],
    typography: [],
    notes: [],
  };
  const fallback: string[] = [];
  let current: BriefSectionKey | null = null;

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    const match = line.match(/^([^:：]{1,48})[:：]\s*(.*)$/);
    if (match) {
      const key = sectionKeyForLabel(match[1]);
      if (key) {
        current = key;
        const value = match[2]?.trim();
        if (value) sections[key].push(value);
        continue;
      }
    }
    if (current) {
      sections[current].push(line);
    } else {
      fallback.push(line);
    }
  }

  return { sections, fallback };
}

function stripBullet(line: string): string {
  return line.replace(/^[-*]\s+/, '').trim();
}

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
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-app-accent" />
              <span>{stripBullet(line)}</span>
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
  const parsed = parseBrief(version.text);
  const title = parsed.sections.title[0] || parsed.fallback[0] || `v${index + 1}`;
  const hasParsedSections = SECTION_ORDER.some((section) => parsed.sections[section].length > 0);

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
          {SECTION_ORDER.map((section) => (
            <BriefSection
              key={section}
              label={t(`ai.imageWizard.step4.briefSections.${section}`)}
              lines={parsed.sections[section]}
            />
          ))}
        </div>
      ) : (
        <pre className="app-text-body whitespace-pre-wrap break-words font-sans text-app-ink">
          {version.text}
        </pre>
      )}
      <div className="mt-3 flex items-center justify-end">
        <button
          type="button"
          onClick={onApprove}
          disabled={approveDisabled || approving}
          className={`flex items-center gap-1.5 rounded-md px-4 py-2 app-text-control-sm font-medium transition-colors disabled:opacity-50 ${
            isLatest
              ? 'bg-app-accent text-white hover:opacity-90 disabled:border disabled:border-app-border disabled:bg-app-surface-sidebar disabled:text-app-ink/70 disabled:opacity-100'
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

export default BriefTurn;
