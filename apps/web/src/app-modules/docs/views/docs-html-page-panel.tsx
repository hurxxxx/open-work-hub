import { ExternalLink, FileCode2, Pencil } from 'lucide-react';

import { DocsHtmlFrame } from './docs-html-frame';

export interface DocsHtmlPagePanelProps {
  title: string;
  content?: string | null;
  previewLabel: string;
  openLabel: string;
  emptyLabel: string;
  editLabel?: string;
  onOpen: () => void;
  onEdit?: () => void;
}

export function DocsHtmlPagePanel({
  title,
  content,
  previewLabel,
  openLabel,
  emptyLabel,
  editLabel,
  onOpen,
  onEdit,
}: DocsHtmlPagePanelProps) {
  const hasContent = Boolean(content?.trim());
  return (
    <div className="not-prose space-y-3">
      <div className="flex flex-col gap-3 rounded-md border border-app-border bg-app-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <span className="flex min-w-0 items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-app-accent/10 text-app-accent">
            <FileCode2 size={20} />
          </span>
          <span className="min-w-0">
            <span className="app-text-control block truncate text-app-ink">
              {title}
            </span>
            <span className="app-text-caption block truncate text-app-ink/55">
              {hasContent ? previewLabel : emptyLabel}
            </span>
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {onEdit && editLabel ? (
            <button
              type="button"
              onClick={onEdit}
              className="app-text-control-sm inline-flex items-center justify-center gap-1.5 rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover"
            >
              <Pencil size={14} />
              <span>{editLabel}</span>
            </button>
          ) : null}
          <button
            type="button"
            disabled={!hasContent}
            onClick={onOpen}
            className="app-text-control-sm inline-flex items-center justify-center gap-1.5 rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ExternalLink size={14} />
            <span>{openLabel}</span>
          </button>
        </span>
      </div>
      {hasContent ? (
        <div className="h-[min(70vh,720px)] min-h-[420px] overflow-hidden rounded-md border border-app-border bg-white">
          <DocsHtmlFrame title={title} content={content ?? ''} />
        </div>
      ) : null}
    </div>
  );
}
