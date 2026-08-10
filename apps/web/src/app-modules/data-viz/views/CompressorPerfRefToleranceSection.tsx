import { useMemo, useRef } from 'react';
import { Loader2, Save, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { InlineNotice } from '@ai-do/ui';

import { cn } from '@/src/lib/utils';
import type {
  ToleranceAllResponse,
  ToleranceResponse,
} from '../api/dataviz-api';
import {
  DEFAULT_REF_GROUPS,
  REF_TOLERANCE_FIELD_LABELS,
  REF_TOLERANCE_FIELDS,
  numberOrNull,
  sortToleranceCapModelKeys,
  toleranceEsOrder,
  type RefToleranceValues,
} from './compressor-perf-tolerance-model';
import { COMPRESSOR_PERF_TABLE_CLASSES } from './data-viz-colors';

export interface CompressorPerfRefToleranceSectionProps {
  capacity: string;
  carModel: string;
  loading: string | null;
  refSaveStatus?: string;
  refValues: RefToleranceValues;
  tolerance: ToleranceResponse | null;
  toleranceAll: ToleranceAllResponse | null;
  toleranceFile: File | null;
  onCapacityChange: (capacity: string) => void;
  onCarModelChange: (carModel: string) => void;
  onRefValuesChange: (values: RefToleranceValues) => void;
  onSaveTolerance: () => void | Promise<void>;
  onToleranceFileChange: (file: File | null) => void;
  onToleranceUpload: () => boolean | Promise<boolean>;
}

export function CompressorPerfRefToleranceSection({
  capacity,
  carModel,
  loading,
  refSaveStatus,
  refValues,
  tolerance,
  toleranceAll,
  toleranceFile,
  onCapacityChange,
  onCarModelChange,
  onRefValuesChange,
  onSaveTolerance,
  onToleranceFileChange,
  onToleranceUpload,
}: CompressorPerfRefToleranceSectionProps) {
  const { t } = useTranslation('apps');
  const toleranceInputRef = useRef<HTMLInputElement | null>(null);

  const handleToleranceUpload = async () => {
    const uploaded = await onToleranceUpload();
    if (uploaded && toleranceInputRef.current) {
      toleranceInputRef.current.value = '';
    }
  };

  return (
    <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
      <h2 className="app-text-body-sm mb-3 font-semibold text-app-ink">
        {t('ai.dataViz.perf.toleranceRefs')}
      </h2>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          ref={toleranceInputRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          style={{ fontSize: '12px' }}
          className="text-app-ink"
          onChange={(event) =>
            onToleranceFileChange(event.target.files?.[0] ?? null)
          }
        />
        <button
          type="button"
          disabled={!toleranceFile || loading === 'tolUpload'}
          onClick={() => void handleToleranceUpload()}
          style={{ fontSize: '12px' }}
          className="inline-flex h-7 items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-2.5 text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading === 'tolUpload' ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Upload size={13} />
          )}
          {t('ai.dataViz.perf.bulkUpload')}
        </button>
      </div>
      <ToleranceGrid
        values={refValues}
        onChange={onRefValuesChange}
        capacity={capacity}
        carModel={carModel}
        onCapacityChange={onCapacityChange}
        onCarModelChange={onCarModelChange}
        carModels={tolerance?.car_models ?? []}
        fields={REF_TOLERANCE_FIELDS}
        fieldLabels={REF_TOLERANCE_FIELD_LABELS}
      />
      {toleranceAll && Object.keys(toleranceAll.cap_models).length > 0 ? (
        <div className="mt-4">
          <h3
            style={{ fontSize: '12px' }}
            className="mb-2 font-semibold text-app-ink/75"
          >
            {t('ai.dataViz.perf.toleranceAllReviewTitle', {
              count: Object.keys(toleranceAll.cap_models).length,
            })}
          </h3>
          <ToleranceAllReviewGrid
            data={toleranceAll}
            fields={REF_TOLERANCE_FIELDS}
            fieldLabels={REF_TOLERANCE_FIELD_LABELS}
            onRowClick={(rowCapacity, rowModel, rowValues) => {
              onCapacityChange(rowCapacity);
              onCarModelChange(rowModel);
              onRefValuesChange(rowValues);
            }}
          />
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={loading === 'tolSave'}
          style={{ fontSize: '12px' }}
          className="inline-flex h-7 items-center gap-1.5 rounded-md bg-app-accent px-2.5 font-medium text-app-accent-fg shadow-sm transition-colors hover:bg-app-accent-hover active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-60"
          onClick={() => void onSaveTolerance()}
        >
          {loading === 'tolSave' ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Save size={13} />
          )}
          {loading === 'tolSave'
            ? t('common:actions.saving')
            : t('ai.dataViz.perf.saveRefs')}
        </button>
        {refSaveStatus ? (
          <InlineNotice tone="success">{refSaveStatus}</InlineNotice>
        ) : null}
      </div>
    </div>
  );
}

function RefGridColgroup({ metricCount }: { metricCount: number }) {
  const w = `${(66 / Math.max(metricCount, 1)).toFixed(3)}%`;
  return (
    <colgroup>
      <col style={{ width: '12%' }} />
      <col style={{ width: '14%' }} />
      <col style={{ width: '8%' }} />
      {Array.from({ length: metricCount }).map((_, i) => (
        <col key={i} style={{ width: w }} />
      ))}
    </colgroup>
  );
}

function refRowBorder(isLast: boolean): string {
  return isLast
    ? COMPRESSOR_PERF_TABLE_CLASSES.groupEndBorder
    : 'border-b border-b-app-border [border-bottom-style:dashed]';
}

function ToleranceGrid({
  values,
  onChange,
  capacity,
  carModel,
  onCapacityChange,
  onCarModelChange,
  carModels,
  fields = REF_TOLERANCE_FIELDS,
  fieldLabels,
}: {
  values: RefToleranceValues;
  onChange: (next: RefToleranceValues) => void;
  capacity: string;
  carModel: string;
  onCapacityChange: (capacity: string) => void;
  onCarModelChange: (carModel: string) => void;
  carModels?: string[];
  fields?: readonly string[];
  fieldLabels?: Record<string, string>;
}) {
  const { t } = useTranslation('apps');
  const groups =
    Object.keys(values).length > 0
      ? Object.keys(values).sort()
      : [...DEFAULT_REF_GROUPS];
  const labelFor = (field: string): string =>
    fieldLabels?.[field] ?? t(`ai.dataViz.perf.metric.${field}`);
  const cellInput =
    'w-full rounded-md border border-app-border bg-app-surface px-2 py-1 text-center text-app-ink tabular-nums outline-none transition-colors focus:border-app-accent';
  return (
    <div className="overflow-auto custom-scrollbar rounded-md border border-app-border">
      {carModels ? (
        <datalist id="dataviz-car-models">
          {carModels.map((item) => (
            <option key={item} value={item} />
          ))}
        </datalist>
      ) : null}
      <table className="w-full table-fixed border-collapse">
        <RefGridColgroup metricCount={fields.length} />
        <thead>
          <tr className="border-b border-app-border bg-app-surface-sidebar">
            <th
              style={{ fontSize: '12px' }}
              className="px-2 py-1 text-center font-medium text-app-ink/65"
            >
              {t('ai.dataViz.perf.capacity')}
            </th>
            <th
              style={{ fontSize: '12px' }}
              className="px-2 py-1 text-center font-medium text-app-ink/65"
            >
              {t('ai.dataViz.perf.carModel')}
            </th>
            <th
              style={{ fontSize: '12px' }}
              className="px-2 py-1 text-center font-medium text-app-ink/65"
            >
              {fieldLabels?.['__es__'] ?? 'ES'}
            </th>
            {fields.map((field) => (
              <th
                key={field}
                style={{ fontSize: '12px' }}
                className="px-2 py-1 text-center font-medium text-app-ink/65"
              >
                {labelFor(field)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((group, idx) => {
            const border = refRowBorder(idx === groups.length - 1);
            return (
              <tr key={group}>
                <td className={cn('px-1.5 py-1', border)}>
                  <div className="relative flex items-center">
                    <input
                      type="number"
                      inputMode="numeric"
                      placeholder={t('ai.dataViz.perf.numericPlaceholder')}
                      style={{ fontSize: '12px' }}
                      className={cn(cellInput, 'pr-6 text-right')}
                      value={capacity.replace(/[^0-9.]/g, '')}
                      onChange={(event) => {
                        const digits = event.target.value.replace(
                          /[^0-9.]/g,
                          '',
                        );
                        onCapacityChange(digits ? `${digits}cc` : '');
                      }}
                    />
                    <span
                      style={{ fontSize: '12px' }}
                      className="pointer-events-none absolute right-2 text-app-ink/55"
                    >
                      cc
                    </span>
                  </div>
                </td>
                <td className={cn('px-1.5 py-1', border)}>
                  <input
                    type="text"
                    placeholder={t('ai.dataViz.perf.carModel')}
                    style={{ fontSize: '12px' }}
                    className={cellInput}
                    value={carModel}
                    onChange={(event) => onCarModelChange(event.target.value)}
                    list="dataviz-car-models"
                  />
                </td>
                <td
                  style={{ fontSize: '12px' }}
                  className={cn('px-2 py-1 text-center text-app-ink', border)}
                >
                  {group}
                </td>
                {fields.map((field) => (
                  <td key={field} className={cn('px-1.5 py-1', border)}>
                    <input
                      type="number"
                      step="any"
                      style={{ fontSize: '12px' }}
                      className={cellInput}
                      value={values[group]?.[field] ?? ''}
                      onChange={(event) => {
                        const next = {
                          ...values,
                          [group]: { ...(values[group] ?? {}) },
                        };
                        next[group][field] = numberOrNull(event.target.value);
                        onChange(next);
                      }}
                    />
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ToleranceAllReviewGrid({
  data,
  fields,
  fieldLabels,
  onRowClick,
}: {
  data: ToleranceAllResponse;
  fields: readonly string[];
  fieldLabels?: Record<string, string>;
  onRowClick?: (
    capacity: string,
    carModel: string,
    refValues: RefToleranceValues,
  ) => void;
}) {
  const { t } = useTranslation('apps');
  const labelFor = (field: string): string => fieldLabels?.[field] ?? field;
  const capModelKeys = useMemo(() => sortToleranceCapModelKeys(data), [data]);

  if (capModelKeys.length === 0) return null;

  return (
    <div className="overflow-auto custom-scrollbar rounded-md border border-app-border">
      <table className="w-full table-fixed border-collapse">
        <RefGridColgroup metricCount={fields.length} />
        <thead>
          <tr className="border-b border-app-border bg-app-surface-sidebar">
            <th
              style={{ fontSize: '12px' }}
              className="px-2 py-1 text-center font-medium text-app-ink/65"
            >
              {t('ai.dataViz.perf.capacity')}
            </th>
            <th
              style={{ fontSize: '12px' }}
              className="px-2 py-1 text-center font-medium text-app-ink/65"
            >
              {t('ai.dataViz.perf.carModel')}
            </th>
            <th
              style={{ fontSize: '12px' }}
              className="px-2 py-1 text-center font-medium text-app-ink/65"
            >
              ES
            </th>
            {fields.map((field) => (
              <th
                key={field}
                style={{ fontSize: '12px' }}
                className="px-2 py-1 text-center font-medium text-app-ink/65"
              >
                {labelFor(field)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {capModelKeys.flatMap((key, groupIdx) => {
            const meta = data.cap_models[key];
            const groupData = data.models[key] ?? {};
            const esKeys = Object.keys(groupData).sort(
              (a, b) => toleranceEsOrder(a) - toleranceEsOrder(b),
            );
            const bgClass =
              groupIdx % 2 === 1
                ? COMPRESSOR_PERF_TABLE_CLASSES.groupAltBg
                : '';
            return esKeys.map((esKey, esIdx) => {
              const isGroupEnd = esIdx === esKeys.length - 1;
              const cellBorder = isGroupEnd
                ? COMPRESSOR_PERF_TABLE_CLASSES.groupEndBorder
                : 'border-b border-b-app-border [border-bottom-style:dashed]';
              return (
                <tr
                  key={`${key}-${esKey}`}
                  className={cn(
                    bgClass,
                    onRowClick ? 'cursor-pointer hover:bg-app-accent/10' : '',
                  )}
                  onClick={
                    onRowClick
                      ? () => onRowClick(meta.capacity, meta.model, groupData)
                      : undefined
                  }
                >
                  <td
                    style={{ fontSize: '12px' }}
                    className={cn(
                      'px-2 py-1 text-center text-app-ink',
                      cellBorder,
                    )}
                  >
                    {meta.capacity}
                  </td>
                  <td
                    style={{ fontSize: '12px' }}
                    className={cn(
                      'px-2 py-1 text-center text-app-ink',
                      cellBorder,
                    )}
                  >
                    {meta.model}
                  </td>
                  <td
                    style={{ fontSize: '12px' }}
                    className={cn(
                      'px-2 py-1 text-center text-app-ink',
                      cellBorder,
                    )}
                  >
                    {esKey}
                  </td>
                  {fields.map((field) => (
                    <td
                      key={field}
                      style={{ fontSize: '12px' }}
                      className={cn(
                        'px-2 py-1 text-center tabular-nums text-app-ink',
                        cellBorder,
                      )}
                    >
                      {groupData[esKey]?.[field] != null
                        ? String(groupData[esKey][field])
                        : '-'}
                    </td>
                  ))}
                </tr>
              );
            });
          })}
        </tbody>
      </table>
    </div>
  );
}
