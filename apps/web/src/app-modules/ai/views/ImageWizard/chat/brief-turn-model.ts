export type BriefSectionKey =
  | 'title'
  | 'goal'
  | 'composition'
  | 'visibleText'
  | 'style'
  | 'review';

export interface ParsedBrief {
  sections: Record<BriefSectionKey, string[]>;
  fallback: string[];
}

export interface BriefTurnProjection {
  fallbackText: string;
  hasParsedSections: boolean;
  sections: ParsedBrief['sections'];
  title: string;
}

export const BRIEF_SECTION_ORDER: BriefSectionKey[] = [
  'goal',
  'composition',
  'visibleText',
  'style',
  'review',
];

const SECTION_LABEL_ALIASES: Record<BriefSectionKey, string[]> = {
  title: ['TITLE', '\uc81c\ubaa9'],
  goal: ['GOAL', 'OBJECTIVE', '\ubaa9\ud45c'],
  composition: [
    'COMPOSITION',
    'LAYOUT',
    'KEY ELEMENTS',
    'KEY ELEMENT',
    '\ud654\uba74 \uad6c\uc131',
    '\uad6c\uc131',
    '\ub808\uc774\uc544\uc6c3',
    '\ud575\uc2ec \uc694\uc18c',
    '\uc8fc\uc694 \uc694\uc18c',
  ],
  visibleText: [
    'VISIBLE TEXT',
    'COPY',
    '\ud654\uba74\uc5d0 \ub123\uc744 \ud14d\uc2a4\ud2b8',
    '\ud45c\uc2dc \ud14d\uc2a4\ud2b8',
  ],
  style: [
    'STYLE',
    'COLORS',
    'COLOR',
    'TYPOGRAPHY',
    '\uc2a4\ud0c0\uc77c',
    '\uc0c9\uc0c1',
    '\uceec\ub7ec',
    '\uae00\uc790 \uc2a4\ud0c0\uc77c',
    '\ud0c0\uc774\ud3c4\uadf8\ub798\ud53c',
  ],
  review: [
    'NEEDS REVIEW',
    'REVIEW',
    'NOTES',
    'NOTE',
    '\ud655\uc778 \ud544\uc694',
    '\uc8fc\uc758\uc0ac\ud56d',
    '\uba54\ubaa8',
  ],
};

const PLACEHOLDER_VALUES = new Set([
  'metric',
  'metrics',
  'status',
  'priority',
  'client',
  'label',
  'title',
  'description',
  'copy',
  'text',
  '\uc124\uba85 \ud14d\uc2a4\ud2b8',
]);

function cleanPlaceholderText(value: string): string {
  return value
    .replace(/<\s*([^<>]{1,80})\s*>/g, (_match, inner: string) => {
      const label = inner.trim().replace(/\s+/g, ' ');
      if (PLACEHOLDER_VALUES.has(label.toLowerCase())) return '';
      return label;
    })
    .replace(/\s+/g, ' ')
    .trim();
}

function emptySections(): Record<BriefSectionKey, string[]> {
  return {
    title: [],
    goal: [],
    composition: [],
    visibleText: [],
    style: [],
    review: [],
  };
}

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

export function parseBriefText(text: string): ParsedBrief {
  const sections = emptySections();
  const fallback: string[] = [];
  let current: BriefSectionKey | null = null;

  for (const rawLine of text.split(/\r?\n/)) {
    const line = cleanPlaceholderText(rawLine);
    if (!line) continue;
    const match = line.match(/^([^:：]{1,48})[:：]\s*(.*)$/);
    if (match) {
      const key = sectionKeyForLabel(match[1]);
      if (key) {
        current = key;
        const value = cleanPlaceholderText(match[2] || '');
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

export function stripBriefBullet(line: string): string {
  return line.replace(/^[-*]\s+/, '').trim();
}

export function buildBriefTurnProjection(
  text: string,
  versionIndex: number,
): BriefTurnProjection {
  const parsed = parseBriefText(text);
  return {
    fallbackText: text
      .split(/\r?\n/)
      .flatMap((line) => {
        const cleanedLine = cleanPlaceholderText(line);
        return cleanedLine ? [cleanedLine] : [];
      })
      .join('\n'),
    hasParsedSections: BRIEF_SECTION_ORDER.some(
      (section) => parsed.sections[section].length > 0,
    ),
    sections: parsed.sections,
    title: parsed.sections.title[0] || parsed.fallback[0] || `v${versionIndex + 1}`,
  };
}
