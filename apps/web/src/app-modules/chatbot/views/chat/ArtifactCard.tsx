import {
  Code2,
  FileText,
  Globe,
  Image as ImageIcon,
  Loader2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { ArtifactBuffer } from '../../api/agent-events';
import type { ChatbotArtifactRenderer } from '../chatbot-experience';
import { cn } from '@/src/lib/utils';

export interface ArtifactCardProps {
  artifact: ArtifactBuffer;
  isActive: boolean;
  onOpen: (artifactId: string) => void;
  renderers?: readonly ChatbotArtifactRenderer[];
}

// Small inline summary card rendered below a chat bubble. Mirrors the
// ToolCallCard layout so the two types feel consistent when a turn has both.
// Clicking routes to the artifact panel — the full body never lives in the
// chat flow itself.
export function ArtifactCard({
  artifact,
  isActive,
  onOpen,
  renderers = [],
}: ArtifactCardProps) {
  const { t } = useTranslation('apps');
  const streaming = artifact.status === 'open';
  const label = artifact.title?.trim() || typeFallbackLabel(artifact.type, t);
  const customPreview = renderers
    .find((renderer) => renderer.type === artifact.type)
    ?.preview?.(artifact);
  const preview =
    customPreview === undefined
      ? buildTypedPreview(artifact, t)
      : customPreview;
  const Icon = streaming ? Loader2 : iconForType(artifact.type);

  return (
    <button
      type="button"
      onClick={() => onOpen(artifact.id)}
      className={cn(
        'mt-2 flex w-full items-start gap-3 rounded-lg border px-3 py-2 text-left transition-colors',
        isActive
          ? 'border-app-accent bg-app-bg'
          : 'border-app-border bg-app-surface hover:border-app-accent',
      )}
      aria-pressed={isActive}
      data-testid={`artifact-card-${artifact.id}`}
    >
      <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent">
        <Icon size={14} className={streaming ? 'animate-spin' : undefined} />
      </div>
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="app-text-control-sm truncate text-app-ink">{label}</div>
        <div className="app-text-micro truncate text-app-ink/55">
          {streaming
            ? t('ai.artifacts.streaming')
            : preview ||
              t('ai.artifacts.contentLength', {
                type: artifact.type,
                count: artifact.content.length,
              })}
        </div>
      </div>
      <div className="app-text-micro shrink-0 self-center text-app-ink/55">
        {isActive ? t('ai.artifacts.opened') : t('ai.artifacts.open')}
      </div>
    </button>
  );
}

function iconForType(type: string) {
  switch (type) {
    case 'html':
      return Globe;
    case 'code':
      return Code2;
    case 'svg':
      return ImageIcon;
    case 'document':
    default:
      return FileText;
  }
}

function typeFallbackLabel(type: string, t: (key: string) => string): string {
  switch (type) {
    case 'html':
      return t('ai.artifacts.untitledHtml');
    case 'code':
      return t('ai.artifacts.untitledCode');
    case 'svg':
      return t('ai.artifacts.untitledSvg');
    case 'document':
    default:
      return t('ai.artifacts.untitledDocument');
  }
}

function buildTypedPreview(
  artifact: ArtifactBuffer,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  switch (artifact.type) {
    case 'html':
      return htmlPreview(artifact.content, t);
    case 'code': {
      const lines = artifact.content.split('\n').length;
      const lang = artifact.language?.trim();
      return lang
        ? t('ai.artifacts.codeLanguageLines', { language: lang, count: lines })
        : t('ai.artifacts.codeLines', { count: lines });
    }
    case 'svg':
      return t('ai.artifacts.contentLength', {
        type: 'SVG',
        count: artifact.content.length,
      });
    case 'document':
    default:
      return buildPreview(artifact.content);
  }
}

function htmlPreview(content: string, t: (key: string) => string): string {
  // Try the <title> tag first — matches what the browser tab would show.
  const titleMatch = /<title>([\s\S]*?)<\/title>/i.exec(content);
  const title = titleMatch?.[1]?.trim();
  if (title) {
    return `HTML · ${title.slice(0, 60)}`;
  }
  return t('ai.artifacts.htmlPreview');
}

function buildPreview(content: string): string {
  // First non-empty non-boilerplate line, stripped of common markdown
  // tokens. The preview shows up in a ~80char subtitle; leaking `**`,
  // pipe tables, or link syntax makes the card look broken.
  const trimmed = content.trim();
  if (!trimmed) {
    return '';
  }
  const candidate =
    trimmed
      .split('\n')
      .map((line) => stripMarkdownTokens(line))
      .find((line) => line.length > 0) ?? '';
  return candidate.length > 80 ? `${candidate.slice(0, 80)}…` : candidate;
}

function stripMarkdownTokens(line: string): string {
  let out = line.trim();
  if (!out) return '';
  // Leading block markers: heading, quote, list bullet, ordered list, fence.
  out = out.replace(/^(#{1,6}\s+|>\s+|[-*+]\s+|\d+\.\s+|```[\w-]*\s*)/, '');
  // Drop leftover fence markers that appear in isolation.
  if (/^`{3,}\s*[\w-]*$/.test(out)) return '';
  // Pipe-only table separator rows like `|:---|:---|`.
  if (/^\|?[-:|\s]+\|?$/.test(out)) return '';
  // Image `![alt](url)` → `alt`.
  out = out.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1');
  // Link `[text](url)` → `text`.
  out = out.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  // Emphasis wrappers: bold `**x**` / `__x__`, italic `*x*` / `_x_`,
  // strikethrough `~~x~~`, inline code `` `x` ``.
  out = out.replace(/\*\*([^*]+)\*\*/g, '$1');
  out = out.replace(/__([^_]+)__/g, '$1');
  out = out.replace(/~~([^~]+)~~/g, '$1');
  out = out.replace(/`([^`]+)`/g, '$1');
  out = out.replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, '$1$2');
  out = out.replace(/(^|[^_])_([^_\s][^_]*?)_(?!_)/g, '$1$2');
  // Any remaining stray markers — drop them rather than show garbage.
  out = out.replace(/[*_`~]+/g, '');
  // Table row leading/trailing pipes.
  out = out.replace(/^\|\s*/, '').replace(/\s*\|$/, '');
  // Collapse interior pipes to middots so multi-column rows read cleanly.
  out = out.replace(/\s*\|\s*/g, ' · ');
  return out.trim();
}
