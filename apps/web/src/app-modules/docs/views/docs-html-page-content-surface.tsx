import { DocsHtmlEditorPanel } from './docs-html-editor-panel';
import { DocsHtmlPagePanel } from './docs-html-page-panel';

export interface DocsHtmlPageContentSurfaceLabels {
  editSource: string;
  empty: string;
  openRendered: string;
  pastePlaceholder: string;
  preview: string;
  sourceLabel: string;
  uploadLabel: string;
  uploadPlaceholder: string;
}

export interface DocsHtmlPageContentSurfaceProps {
  canEdit: boolean;
  content?: string | null;
  editing: boolean;
  labels: DocsHtmlPageContentSurfaceLabels;
  onChange: (content: string) => void;
  onEdit: () => void;
  onOpen: () => void;
  onPreview: () => void;
  onUploadFile: (file: File | null) => void;
  title: string;
}

export function DocsHtmlPageContentSurface({
  canEdit,
  content,
  editing,
  labels,
  onChange,
  onEdit,
  onOpen,
  onPreview,
  onUploadFile,
  title,
}: DocsHtmlPageContentSurfaceProps) {
  if (canEdit && editing) {
    return (
      <DocsHtmlEditorPanel
        title={title}
        content={content}
        uploadLabel={labels.uploadLabel}
        uploadPlaceholder={labels.uploadPlaceholder}
        sourceLabel={labels.sourceLabel}
        sourcePlaceholder={labels.pastePlaceholder}
        previewLabel={labels.preview}
        openLabel={labels.openRendered}
        emptyLabel={labels.empty}
        onChange={onChange}
        onOpen={onOpen}
        onPreview={onPreview}
        onUploadFile={onUploadFile}
      />
    );
  }

  return (
    <DocsHtmlPagePanel
      title={title}
      content={content}
      previewLabel={labels.preview}
      openLabel={labels.openRendered}
      emptyLabel={labels.empty}
      onOpen={onOpen}
      editLabel={canEdit ? labels.editSource : undefined}
      onEdit={canEdit ? onEdit : undefined}
    />
  );
}
