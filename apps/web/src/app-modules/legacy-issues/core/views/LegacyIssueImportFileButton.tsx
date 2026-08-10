import { useRef, type ChangeEvent } from 'react';
import { Loader2, Upload } from 'lucide-react';

export function LegacyIssueImportFileButton({
  disabled = false,
  fileTypesLabel,
  label,
  loading = false,
  onFileSelected,
}: {
  disabled?: boolean;
  fileTypesLabel: string;
  label: string;
  loading?: boolean;
  onFileSelected: (file: File | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const inactive = disabled || loading;

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0] ?? null;
    onFileSelected(file);
    event.currentTarget.value = '';
  }

  return (
    <div className="inline-flex items-center gap-2">
      <input
        ref={inputRef}
        accept=".csv,.xlsx"
        className="hidden"
        type="file"
        onChange={handleChange}
      />
      <button
        className="app-control h-9 px-3"
        disabled={inactive}
        type="button"
        onClick={() => inputRef.current?.click()}
      >
        {loading ? (
          <Loader2 size={16} className="animate-spin" />
        ) : (
          <Upload size={16} />
        )}
        <span>{label}</span>
      </button>
      <span className="hidden app-text-caption text-app-ink/45 sm:inline">
        {fileTypesLabel}
      </span>
    </div>
  );
}
