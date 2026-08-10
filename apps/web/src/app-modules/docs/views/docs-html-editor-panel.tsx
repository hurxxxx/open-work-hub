import { ExternalLink, FileCode2, Upload } from 'lucide-react';

export interface DocsHtmlEditorPanelProps {
  title: string;
  content?: string | null;
  uploadLabel: string;
  uploadPlaceholder: string;
  sourceLabel: string;
  sourcePlaceholder: string;
  previewLabel: string;
  openLabel: string;
  emptyLabel: string;
  onChange: (content: string) => void;
  onOpen: () => void;
  onPreview?: () => void;
  onUploadFile: (file: File | null) => void;
}

export function DocsHtmlEditorPanel({
  title,
  content,
  uploadLabel,
  uploadPlaceholder,
  sourceLabel,
  sourcePlaceholder,
  previewLabel,
  openLabel,
  emptyLabel,
  onChange,
  onOpen,
  onPreview,
  onUploadFile,
}: DocsHtmlEditorPanelProps) {
  const hasContent = Boolean(content?.trim());
  return (
    <div className="not-prose space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <label className="min-w-0 flex-1">
          <span className="app-text-caption mb-1 block text-app-ink/55">
            {uploadLabel}
          </span>
          <span className="flex cursor-pointer items-center justify-between gap-3 rounded-md border border-dashed border-app-border bg-app-bg p-3 text-app-ink hover:bg-app-surface-hover">
            <span className="flex min-w-0 items-center gap-2">
              <Upload size={16} className="shrink-0 text-app-accent" />
              <span className="app-text-body-sm truncate">
                {uploadPlaceholder}
              </span>
            </span>
            <input
              type="file"
              accept=".html,.htm,text/html"
              className="sr-only"
              onChange={(event) => {
                onUploadFile(event.target.files?.[0] ?? null);
                event.currentTarget.value = '';
              }}
            />
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          {onPreview ? (
            <button
              type="button"
              onClick={onPreview}
              className="app-text-control inline-flex items-center justify-center gap-2 rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover"
            >
              <FileCode2 size={16} />
              <span>{previewLabel}</span>
            </button>
          ) : null}
          <button
            type="button"
            disabled={!hasContent}
            onClick={onOpen}
            className="app-text-control inline-flex items-center justify-center gap-2 rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ExternalLink size={16} />
            <span>{hasContent ? openLabel : emptyLabel}</span>
          </button>
        </div>
      </div>
      <label className="block">
        <span className="app-text-caption mb-1 block text-app-ink/55">
          {sourceLabel}
        </span>
        <textarea
          value={content ?? ''}
          onChange={(event) => onChange(event.target.value)}
          placeholder={sourcePlaceholder}
          aria-label={title}
          className="app-text-body-sm min-h-[420px] w-full resize-y rounded-md border border-app-border bg-app-bg px-3 py-2 font-mono text-app-ink focus:border-app-accent focus:outline-none"
        />
      </label>
    </div>
  );
}
