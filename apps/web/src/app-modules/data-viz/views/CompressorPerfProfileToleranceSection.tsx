import { useMemo } from 'react';
import { Loader2, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { InlineNotice, Input } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import type { ProfileTolCell } from '../api/dataviz-api';
import {
  TEST_TOLERANCE_FIELDS,
  TOLERANCE_SIGN_OPTIONS,
  formatProfileToleranceCell,
  nonEmptyProfileToleranceGroups,
  numberOrNull,
  profileToleranceGroups,
  profileToleranceRowCount,
  type ProfileToleranceProfiles,
  type ProfileToleranceValues,
} from './compressor-perf-tolerance-model';
import { COMPRESSOR_PERF_TABLE_CLASSES } from './data-viz-colors';

export interface CompressorPerfProfileToleranceSectionProps {
  allProfiles: ProfileToleranceProfiles;
  fieldLabels: Record<string, string>;
  loading: string | null;
  profileName: string;
  profileRowCount: number;
  profileSaveStatus?: string;
  tolValues: ProfileToleranceValues;
  onProfileNameChange: (name: string) => void;
  onProfileRowCountChange: (count: number) => void;
  onRefreshProfile: () => void | Promise<void>;
  onSaveProfile: () => void | Promise<void>;
  onTolValuesChange: (values: ProfileToleranceValues) => void;
}

export function CompressorPerfProfileToleranceSection({
  allProfiles,
  fieldLabels,
  loading,
  profileName,
  profileRowCount,
  profileSaveStatus,
  tolValues,
  onProfileNameChange,
  onProfileRowCountChange,
  onRefreshProfile,
  onSaveProfile,
  onTolValuesChange,
}: CompressorPerfProfileToleranceSectionProps) {
  const { t } = useTranslation('apps');

  const loadProfile = (next: string, data: ProfileToleranceValues) => {
    onProfileNameChange(next);
    onTolValuesChange(data);
    onProfileRowCountChange(profileToleranceRowCount(data));
  };

  return (
    <aside className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
      <h2 className="app-text-body-sm mb-3 font-semibold text-app-ink">
        {t('ai.dataViz.perf.toleranceProfile')}
      </h2>
      <div className="mb-3 flex items-center gap-2">
        <label
          style={{ fontSize: '12px' }}
          className="shrink-0 text-app-ink/65"
          htmlFor="dataviz-tol-category"
        >
          {t('ai.dataViz.perf.category')}
        </label>
        <Input
          id="dataviz-tol-category"
          style={{ fontSize: '12px' }}
          className="!h-7 min-w-0 flex-1"
          value={profileName}
          placeholder={t('ai.dataViz.perf.categoryPlaceholder')}
          onChange={(event) => {
            const next = event.target.value;
            onProfileNameChange(next);
            const loaded = allProfiles[next];
            onTolValuesChange(loaded ?? {});
            onProfileRowCountChange(
              loaded ? profileToleranceRowCount(loaded) : 3,
            );
          }}
        />
        <button
          type="button"
          style={{ fontSize: '12px' }}
          className="inline-flex h-7 items-center rounded-md border border-app-border bg-app-surface px-2.5 text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
          onClick={() => void onRefreshProfile()}
        >
          {t('ai.dataViz.perf.load')}
        </button>
      </div>
      <ToleranceProfileGrid
        category={profileName}
        values={tolValues}
        onChange={onTolValuesChange}
        rowCount={profileRowCount}
        onRowCountChange={onProfileRowCountChange}
        fields={TEST_TOLERANCE_FIELDS}
        fieldLabels={fieldLabels}
      />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={loading === 'profileSave'}
          style={{ fontSize: '12px' }}
          className="inline-flex h-7 items-center gap-1.5 rounded-md bg-app-accent px-2.5 font-medium text-app-accent-fg shadow-sm transition-colors hover:bg-app-accent-hover active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-60"
          onClick={() => void onSaveProfile()}
        >
          {loading === 'profileSave' ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Save size={13} />
          )}
          {loading === 'profileSave'
            ? t('common:actions.saving')
            : t('ai.dataViz.perf.saveProfile')}
        </button>
        {profileSaveStatus ? (
          <InlineNotice tone="success">{profileSaveStatus}</InlineNotice>
        ) : null}
      </div>
      {Object.keys(allProfiles).length > 0 ? (
        <div className="mt-4">
          <h3
            style={{ fontSize: '12px' }}
            className="mb-2 font-semibold text-app-ink/75"
          >
            {t('ai.dataViz.perf.savedProfilesReviewTitle')}
          </h3>
          <ToleranceProfileAllReview
            profiles={allProfiles}
            fields={TEST_TOLERANCE_FIELDS}
            fieldLabels={fieldLabels}
            onProfileClick={loadProfile}
          />
        </div>
      ) : null}
    </aside>
  );
}

function ToleranceProfileGrid({
  category,
  values,
  onChange,
  rowCount,
  onRowCountChange,
  fields,
  fieldLabels,
}: {
  category: string;
  values: ProfileToleranceValues;
  onChange: (next: ProfileToleranceValues) => void;
  rowCount: number;
  onRowCountChange: (count: number) => void;
  fields: readonly string[];
  fieldLabels?: Record<string, string>;
}) {
  const { t } = useTranslation('apps');
  const groups = useMemo(
    () => profileToleranceGroups(category, values, rowCount),
    [category, values, rowCount],
  );

  const labelFor = (field: string): string => fieldLabels?.[field] ?? field;

  const setCell = (
    group: string,
    field: string,
    patch: Partial<ProfileTolCell>,
  ) => {
    const current: ProfileTolCell = values[group]?.[field] ?? {
      ref: null,
      sign: '±',
      tol: null,
      lower: null,
    };
    onChange({
      ...values,
      [group]: {
        ...(values[group] ?? {}),
        [field]: { ...current, ...patch },
      },
    });
  };

  const numClass =
    'w-16 rounded-md border border-app-border bg-app-surface px-2 py-1 text-center text-app-ink tabular-nums outline-none transition-colors focus:border-app-accent';

  const rowBtn =
    'inline-flex h-6 w-6 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-50';

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span style={{ fontSize: '12px' }} className="text-app-ink/65">
          {t('ai.dataViz.perf.profileRows')}
        </span>
        <button
          type="button"
          className={rowBtn}
          disabled={rowCount <= 1}
          onClick={() => onRowCountChange(Math.max(1, rowCount - 1))}
          aria-label={t('ai.dataViz.perf.deleteRow')}
        >
          −
        </button>
        <span
          style={{ fontSize: '12px' }}
          className="min-w-5 text-center tabular-nums text-app-ink"
        >
          {groups.length}
        </span>
        <button
          type="button"
          className={rowBtn}
          onClick={() => onRowCountChange(groups.length + 1)}
          aria-label={t('ai.dataViz.perf.addRow')}
        >
          +
        </button>
      </div>
      <div className="overflow-auto custom-scrollbar rounded-md border border-app-border">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-app-border bg-app-surface-sidebar">
              <th
                style={{ fontSize: '12px' }}
                className="px-2 py-1 text-center font-medium text-app-ink/65"
              >
                {t('ai.dataViz.perf.group')}
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
            {groups.map((group) => (
              <tr key={group} className="border-b border-app-border">
                <td
                  style={{ fontSize: '12px' }}
                  className="whitespace-nowrap px-2 py-1 text-center font-medium text-app-ink"
                >
                  {group}
                </td>
                {fields.map((field) => {
                  const cell = values[group]?.[field];
                  return (
                    <td key={field} className="px-1.5 py-1">
                      <div className="flex items-center justify-center gap-1">
                        <input
                          type="number"
                          step="any"
                          style={{ fontSize: '12px' }}
                          className={numClass}
                          value={cell?.ref ?? ''}
                          onChange={(event) =>
                            setCell(group, field, {
                              ref: numberOrNull(event.target.value),
                            })
                          }
                        />
                        <select
                          className="app-field-input-sm w-auto shrink-0 text-center"
                          value={cell?.sign ?? '±'}
                          onChange={(event) =>
                            setCell(group, field, {
                              sign: event.target
                                .value as ProfileTolCell['sign'],
                            })
                          }
                        >
                          {TOLERANCE_SIGN_OPTIONS.map((sign) => (
                            <option key={sign} value={sign}>
                              {sign}
                            </option>
                          ))}
                        </select>
                        {cell?.sign === '편측' ? (
                          <div className="flex items-center gap-0.5">
                            <span
                              style={{ fontSize: '12px' }}
                              className="text-app-ink/55"
                            >
                              +
                            </span>
                            <input
                              type="number"
                              step="any"
                              title={t('ai.dataViz.perf.upperDeviation')}
                              style={{ fontSize: '12px' }}
                              className={numClass}
                              value={cell?.tol ?? ''}
                              onChange={(event) =>
                                setCell(group, field, {
                                  tol: numberOrNull(event.target.value),
                                })
                              }
                            />
                            <span
                              style={{ fontSize: '12px' }}
                              className="text-app-ink/55"
                            >
                              −
                            </span>
                            <input
                              type="number"
                              step="any"
                              title={t('ai.dataViz.perf.lowerDeviation')}
                              style={{ fontSize: '12px' }}
                              className={numClass}
                              value={cell?.lower ?? ''}
                              onChange={(event) =>
                                setCell(group, field, {
                                  lower: numberOrNull(event.target.value),
                                })
                              }
                            />
                          </div>
                        ) : (
                          <input
                            type="number"
                            step="any"
                            style={{ fontSize: '12px' }}
                            className={numClass}
                            value={cell?.tol ?? ''}
                            onChange={(event) =>
                              setCell(group, field, {
                                tol: numberOrNull(event.target.value),
                              })
                            }
                          />
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ToleranceProfileAllReview({
  profiles,
  fields,
  fieldLabels,
  onProfileClick,
}: {
  profiles: ProfileToleranceProfiles;
  fields: readonly string[];
  fieldLabels?: Record<string, string>;
  onProfileClick?: (profile: string, data: ProfileToleranceValues) => void;
}) {
  const { t } = useTranslation('apps');
  const labelFor = (field: string): string => fieldLabels?.[field] ?? field;
  const profileNames = Object.keys(profiles).sort();
  if (profileNames.length === 0) return null;
  return (
    <div className="overflow-auto custom-scrollbar rounded-md border border-app-border">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-app-border bg-app-surface-sidebar">
            <th
              style={{ fontSize: '12px' }}
              className="px-2 py-1 text-center font-medium text-app-ink/65"
            >
              {t('ai.dataViz.perf.profile')}
            </th>
            <th
              style={{ fontSize: '12px' }}
              className="px-2 py-1 text-center font-medium text-app-ink/65"
            >
              {t('ai.dataViz.perf.group')}
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
          {profileNames.flatMap((profile, pIdx) => {
            const groupsData = profiles[profile];
            const groups = nonEmptyProfileToleranceGroups(groupsData);
            const bgClass =
              pIdx % 2 === 1 ? COMPRESSOR_PERF_TABLE_CLASSES.groupAltBg : '';
            return groups.map((group, gIdx) => {
              const isEnd = gIdx === groups.length - 1;
              const border = isEnd
                ? COMPRESSOR_PERF_TABLE_CLASSES.groupEndBorder
                : 'border-b border-b-app-border [border-bottom-style:dashed]';
              return (
                <tr
                  key={`${profile}-${group}`}
                  className={cn(
                    bgClass,
                    onProfileClick
                      ? 'cursor-pointer hover:bg-app-accent/10'
                      : '',
                  )}
                  onClick={
                    onProfileClick
                      ? () => onProfileClick(profile, groupsData)
                      : undefined
                  }
                >
                  <td
                    style={{ fontSize: '12px' }}
                    className={cn(
                      'whitespace-nowrap px-2 py-1 text-center font-semibold text-app-ink',
                      border,
                    )}
                  >
                    {gIdx === 0 ? profile : ''}
                  </td>
                  <td
                    style={{ fontSize: '12px' }}
                    className={cn(
                      'whitespace-nowrap px-2 py-1 text-center font-medium text-app-ink',
                      border,
                    )}
                  >
                    {group}
                  </td>
                  {fields.map((field) => (
                    <td
                      key={field}
                      style={{ fontSize: '12px' }}
                      className={cn(
                        'px-2 py-1 text-center tabular-nums text-app-ink',
                        border,
                      )}
                    >
                      {formatProfileToleranceCell(groupsData[group]?.[field])}
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
