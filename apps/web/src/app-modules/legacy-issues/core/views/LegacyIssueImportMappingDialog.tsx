import type { ReactNode } from 'react';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Upload, X } from 'lucide-react';

import { cn } from '@/src/lib/utils';

export type LegacyIssueImportDialogField = {
  key: string;
  label: string;
  locked: boolean;
};

export type LegacyIssueImportDialogDefinition = {
  fields: Array<{
    key: string;
    label_en: string;
    label_ko: string;
    readonly?: boolean;
  }>;
};

export type LegacyIssueImportDialogPreview = {
  columns: Array<{
    header: string;
    index: number;
    sample_values: string[];
  }>;
  preview_rows: string[][];
  record_id_field: string;
};

export function LegacyIssueImportMappingDialog({
  definition,
  mapping,
  onClose,
  onImport,
  onMappingChange,
  preview,
  saving,
}: {
  definition: LegacyIssueImportDialogDefinition;
  mapping: Record<string, number>;
  onClose: () => void;
  onImport: () => void;
  onMappingChange: (mapping: Record<string, number>) => void;
  preview: LegacyIssueImportDialogPreview;
  saving: boolean;
}) {
  const { t, i18n } = useTranslation(['apps']);
  const [step, setStep] = useState<'mapping' | 'preview'>('mapping');
  const [selectedSourceIndex, setSelectedSourceIndex] = useState<number | null>(
    preview.columns[0]?.index ?? null,
  );
  const korean = i18n.language.startsWith('ko');
  const fields: LegacyIssueImportDialogField[] = [
    {
      key: preview.record_id_field,
      label: t('coreBusiness.module.import.recordId'),
      locked: true,
    },
    ...definition.fields
      .filter((field) => !field.readonly)
      .map((field) => ({
        key: field.key,
        label: korean ? field.label_ko : field.label_en,
        locked: false,
      })),
  ];
  const mappedFields = fields.filter(
    (field) => typeof mapping[field.key] === 'number',
  );
  const selectedSourceColumn = preview.columns.find(
    (column) => column.index === selectedSourceIndex,
  );
  const selectedSourceValues =
    selectedSourceIndex === null
      ? []
      : preview.preview_rows.map((row) =>
          selectedSourceIndex < row.length ? row[selectedSourceIndex] : '',
        );

  function updateMapping(fieldKey: string, value: string) {
    const next = { ...mapping };
    if (value === '') {
      delete next[fieldKey];
    } else {
      next[fieldKey] = Number(value);
      setSelectedSourceIndex(Number(value));
    }
    onMappingChange(next);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4">
      <section className="flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface shadow-xl">
        <header className="flex items-center justify-between border-b border-app-border px-4 py-3">
          <div className="min-w-0">
            <h2 className="app-text-subtitle font-semibold">
              {t('coreBusiness.module.import.title')}
            </h2>
            <p className="app-text-caption text-app-ink/55">
              {t('coreBusiness.module.import.subtitle')}
            </p>
          </div>
          <DialogIconButton
            icon={<X size={15} />}
            label={t('coreBusiness.module.actions.close')}
            onClick={onClose}
          />
        </header>

        <div className="border-b border-app-border bg-app-bg px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <StepButton
              active={step === 'mapping'}
              label={t('coreBusiness.module.import.stepMapping')}
              onClick={() => setStep('mapping')}
            />
            <StepButton
              active={step === 'preview'}
              disabled={mappedFields.length === 0}
              label={t('coreBusiness.module.import.stepPreview')}
              onClick={() => setStep('preview')}
            />
            <span className="ml-auto app-text-caption text-app-ink/50">
              {t('coreBusiness.module.import.mappedFields', {
                mapped: mappedFields.length,
                total: fields.length,
              })}
            </span>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-4">
          {step === 'mapping' ? (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)]">
              <section className="min-h-0 rounded-md border border-app-border bg-app-bg">
                <header className="border-b border-app-border px-3 py-2">
                  <p className="app-text-caption font-semibold text-app-ink/70">
                    {t('coreBusiness.module.import.sourceFields')}
                  </p>
                  <p className="app-text-caption text-app-ink/45">
                    {t('coreBusiness.module.import.sourceColumns', {
                      count: preview.columns.length,
                    })}
                  </p>
                </header>
                <div className="grid min-h-0 gap-3 p-2 md:grid-cols-[minmax(0,0.95fr)_minmax(0,1fr)]">
                  <div className="max-h-[52vh] overflow-auto rounded-md border border-app-border bg-app-surface p-1">
                    {preview.columns.map((column) => (
                      <button
                        key={column.index}
                        className={cn(
                          'mb-1 flex min-h-8 w-full items-center gap-2 rounded px-2 py-1.5 text-left app-text-control-sm hover:bg-app-surface-hover',
                          selectedSourceIndex === column.index &&
                            'bg-app-accent/10 text-app-accent',
                        )}
                        type="button"
                        onClick={() => setSelectedSourceIndex(column.index)}
                      >
                        <span className="shrink-0 rounded bg-app-bg px-1.5 py-0.5 app-text-caption text-app-ink/50">
                          {column.index + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate">
                          {column.header}
                        </span>
                      </button>
                    ))}
                  </div>
                  <div className="max-h-[52vh] overflow-auto rounded-md border border-app-border bg-app-surface">
                    <div className="border-b border-app-border px-3 py-2">
                      <p className="app-text-caption font-semibold text-app-ink/70">
                        {t('coreBusiness.module.import.dataSample')}
                      </p>
                      <p className="truncate app-text-caption text-app-ink/45">
                        {selectedSourceColumn?.header ??
                          t('coreBusiness.module.import.noColumnSelected')}
                      </p>
                    </div>
                    <div className="p-2">
                      {selectedSourceValues.length > 0 ? (
                        selectedSourceValues.map((value, index) => (
                          <div
                            key={index}
                            className="min-h-8 border-b border-app-border px-2 py-1.5 app-text-body-sm text-app-ink/70 last:border-b-0"
                          >
                            <span className="mr-2 text-app-ink/35">
                              {index + 1}
                            </span>
                            {value ||
                              t('coreBusiness.module.import.emptyValue')}
                          </div>
                        ))
                      ) : (
                        <div className="px-2 py-4 app-text-body-sm text-app-ink/45">
                          {t('coreBusiness.module.import.noSample')}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </section>

              <section className="min-h-0 rounded-md border border-app-border bg-app-bg">
                <header className="border-b border-app-border px-3 py-2">
                  <p className="app-text-caption font-semibold text-app-ink/70">
                    {t('coreBusiness.module.import.targetFields')}
                  </p>
                  <p className="app-text-caption text-app-ink/45">
                    {t('coreBusiness.module.import.lockedPk')}
                  </p>
                </header>
                <div className="max-h-[52vh] overflow-auto p-2">
                  {fields.map((field) => {
                    const selectedIndex = mapping[field.key];
                    const selectedColumn = preview.columns.find(
                      (column) => column.index === selectedIndex,
                    );
                    return (
                      <div
                        key={field.key}
                        className="mb-2 grid gap-2 rounded-md border border-app-border bg-app-surface px-3 py-2 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)]"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="truncate app-text-body-sm font-medium">
                              {field.label}
                            </p>
                            {field.locked ? (
                              <span className="rounded border border-app-border px-1.5 py-0.5 app-text-caption text-app-ink/50">
                                PK
                              </span>
                            ) : null}
                          </div>
                          <p className="truncate app-text-caption text-app-ink/45">
                            {field.key}
                          </p>
                        </div>
                        <div className="min-w-0">
                          <select
                            className="app-field-input-sm"
                            value={
                              typeof selectedIndex === 'number'
                                ? String(selectedIndex)
                                : ''
                            }
                            onChange={(event) =>
                              updateMapping(field.key, event.target.value)
                            }
                          >
                            <option value="">
                              {t('coreBusiness.module.import.unmapped')}
                            </option>
                            {preview.columns.map((column) => (
                              <option key={column.index} value={column.index}>
                                {column.header}
                              </option>
                            ))}
                          </select>
                          <p className="mt-1 truncate app-text-caption text-app-ink/45">
                            {selectedColumn?.sample_values.join(' / ') ||
                              t('coreBusiness.module.import.noSample')}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            </div>
          ) : (
            <ImportPreviewTable
              fields={mappedFields}
              mapping={mapping}
              preview={preview}
            />
          )}
        </div>
        <footer className="flex justify-end gap-2 border-t border-app-border px-4 py-3">
          <button
            className="app-control h-9 px-3"
            type="button"
            onClick={onClose}
          >
            {t('coreBusiness.module.actions.close')}
          </button>
          {step === 'preview' ? (
            <button
              className="app-control h-9 px-3"
              type="button"
              onClick={() => setStep('mapping')}
            >
              {t('coreBusiness.module.import.backMapping')}
            </button>
          ) : null}
          {step === 'mapping' ? (
            <button
              className="app-control-primary h-9 px-3"
              disabled={mappedFields.length === 0}
              type="button"
              onClick={() => setStep('preview')}
            >
              {t('coreBusiness.module.import.nextPreview')}
            </button>
          ) : (
            <button
              className="app-control-primary h-9 px-3"
              disabled={saving || mappedFields.length === 0}
              type="button"
              onClick={onImport}
            >
              {saving ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Upload size={15} />
              )}
              {t('coreBusiness.module.actions.import')}
            </button>
          )}
        </footer>
      </section>
    </div>
  );
}

function StepButton({
  active,
  disabled = false,
  label,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        'app-control h-8 px-3',
        active
          ? 'app-control-primary'
          : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
      )}
      disabled={disabled}
      type="button"
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function DialogIconButton({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      className="inline-flex size-8 items-center justify-center rounded-md border border-app-border text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink"
      title={label}
      type="button"
      onClick={onClick}
    >
      {icon}
    </button>
  );
}

function ImportPreviewTable({
  fields,
  mapping,
  preview,
}: {
  fields: LegacyIssueImportDialogField[];
  mapping: Record<string, number>;
  preview: LegacyIssueImportDialogPreview;
}) {
  const { t } = useTranslation(['apps']);
  return (
    <div className="overflow-auto rounded-md border border-app-border bg-app-surface">
      <table className="min-w-full table-fixed border-collapse text-left">
        <thead className="sticky top-0 z-10 bg-app-bg">
          <tr>
            {fields.map((field) => (
              <th
                key={field.key}
                className="min-w-40 border-b border-r border-app-border px-2 py-1.5 app-text-caption font-semibold text-app-ink/80 last:border-r-0"
              >
                <span className="block truncate">{field.label}</span>
              </th>
            ))}
          </tr>
          <tr>
            {fields.map((field) => {
              const sourceIndex = mapping[field.key];
              const sourceColumn = preview.columns.find(
                (column) => column.index === sourceIndex,
              );
              return (
                <th
                  key={field.key}
                  className="min-w-40 border-b border-r border-app-border px-2 py-1.5 app-text-caption font-medium text-app-ink/45 last:border-r-0"
                >
                  <span className="block truncate">
                    {sourceColumn?.header ??
                      t('coreBusiness.module.import.unmapped')}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {preview.preview_rows.length > 0 ? (
            preview.preview_rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="hover:bg-app-surface-hover">
                {fields.map((field) => {
                  const sourceIndex = mapping[field.key];
                  const value =
                    typeof sourceIndex === 'number' && sourceIndex < row.length
                      ? row[sourceIndex]
                      : '';
                  return (
                    <td
                      key={field.key}
                      className="min-w-40 border-b border-r border-app-border px-2 py-1.5 align-top app-text-body-sm text-app-ink/70 last:border-r-0"
                    >
                      <span className="line-clamp-3 whitespace-pre-wrap">
                        {value || t('coreBusiness.module.import.emptyValue')}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))
          ) : (
            <tr>
              <td
                className="px-3 py-6 text-center app-text-body-sm text-app-ink/45"
                colSpan={Math.max(fields.length, 1)}
              >
                {t('coreBusiness.module.import.noSample')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
