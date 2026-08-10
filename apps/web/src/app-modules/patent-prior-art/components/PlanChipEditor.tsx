import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, X } from 'lucide-react';

import { Button } from '@ai-do/ui';

import type { PatentPriorArtSearchValues } from '../api/patent-prior-art-api';
import type { EditablePlanField } from '../model/patent-prior-art-view-model';

export function PlanChipEditor({
  field,
  label,
  maxValueChars,
  maxValuesPerField,
  onAdd,
  onRemove,
  searchValues,
}: {
  field: EditablePlanField;
  label: string;
  maxValueChars: number;
  maxValuesPerField: number;
  onAdd: (field: EditablePlanField, value: string) => void;
  onRemove: (field: EditablePlanField, value: string) => void;
  searchValues: PatentPriorArtSearchValues;
}) {
  const { t } = useTranslation('apps');
  const inputId = useId();
  const [draft, setDraft] = useState('');
  const values = searchValues.values ?? [];
  const value = draft.trim();
  const isAtValueLimit = values.length >= maxValuesPerField;
  const isDraftOverlong = value.length > maxValueChars;
  const canAdd = Boolean(value) && !isAtValueLimit && !isDraftOverlong;

  const addDraft = () => {
    if (!canAdd) return;
    onAdd(field, draft);
    setDraft('');
  };

  return (
    <div className="rounded-lg border border-app-border bg-app-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <label className="app-text-control-sm font-semibold" htmlFor={inputId}>
          {label}
        </label>
        <span className="app-text-caption text-app-ink/55">
          {t(`ai.patentPriorArt.plan.sources.${searchValues.source}`)}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {values.map((value) => (
          <span
            className="inline-flex min-h-7 items-center gap-1 rounded-full border border-app-accent/25 bg-app-accent/10 px-2.5 app-text-caption text-app-ink"
            key={value}
          >
            {value}
            <button
              aria-label={t('ai.patentPriorArt.plan.removeChip', { value })}
              className="rounded-full p-0.5 text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-app-accent"
              onClick={() => onRemove(field, value)}
              type="button"
            >
              <X aria-hidden="true" size={13} />
            </button>
          </span>
        ))}
        {values.length === 0 ? (
          <span className="app-text-caption text-app-ink/45">
            {t('ai.patentPriorArt.plan.empty')}
          </span>
        ) : null}
      </div>
      <div className="mt-2 flex gap-2">
        <input
          className="min-w-0 flex-1 rounded-md border border-app-border bg-app-surface px-2.5 py-1.5 app-text-body-sm text-app-ink outline-none focus:border-app-accent focus:ring-2 focus:ring-app-accent/15"
          id={inputId}
          maxLength={maxValueChars}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              addDraft();
            }
          }}
          placeholder={t('ai.patentPriorArt.plan.addPlaceholder', { label })}
          value={draft}
        />
        <Button
          aria-label={t('ai.patentPriorArt.plan.addValue', { label })}
          disabled={!canAdd}
          onClick={addDraft}
          size="icon"
          variant="secondary"
        >
          <Plus aria-hidden="true" size={15} />
        </Button>
      </div>
      <p className="mt-1 app-text-caption text-app-ink/50">
        {t('ai.patentPriorArt.plan.valueLimit', {
          chars: maxValueChars,
          count: values.length,
          max: maxValuesPerField,
        })}
      </p>
    </div>
  );
}
