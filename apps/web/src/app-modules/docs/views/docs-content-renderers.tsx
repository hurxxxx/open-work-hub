import type { ChangeEvent } from 'react';
import { Download, Upload } from 'lucide-react';

export interface DocsBlockMarkdownActionsProps {
  canImport: boolean;
  exportLabel: string;
  importLabel: string;
  onExport: () => void;
  onImportFile: (file: File | null) => void;
}

export function DocsBlockMarkdownActions({
  canImport,
  exportLabel,
  importLabel,
  onExport,
  onImportFile,
}: DocsBlockMarkdownActionsProps) {
  function handleImport(event: ChangeEvent<HTMLInputElement>) {
    onImportFile(event.target.files?.[0] ?? null);
    event.currentTarget.value = '';
  }

  return (
    <div className="not-prose mb-4 flex flex-wrap items-center justify-end gap-2">
      <button
        type="button"
        onClick={onExport}
        className="app-text-control inline-flex items-center gap-2 rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink hover:bg-app-surface-hover"
      >
        <Download size={15} />
        <span>{exportLabel}</span>
      </button>
      {canImport ? (
        <label className="app-text-control inline-flex cursor-pointer items-center gap-2 rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink hover:bg-app-surface-hover">
          <Upload size={15} />
          <span>{importLabel}</span>
          <input
            type="file"
            accept=".md,.markdown,text/markdown,text/plain"
            className="sr-only"
            onChange={handleImport}
          />
        </label>
      ) : null}
    </div>
  );
}
