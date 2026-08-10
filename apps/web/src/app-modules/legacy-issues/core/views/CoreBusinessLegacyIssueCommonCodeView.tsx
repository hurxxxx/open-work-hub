import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';
import { Loader2, Plus, Save, Settings, X } from 'lucide-react';
import { useToast } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  fetchLegacyIssueModuleFields,
  fetchLegacyIssueSystemFields,
  updateLegacyIssueModuleField,
  updateLegacyIssueSystemField,
  type LegacyIssueModuleField,
  type LegacyIssueSystemField,
} from '../api/legacy-issue-api';
import {
  LEGACY_ISSUE_DEFAULT_DATASET_KEY,
  LEGACY_ISSUE_FIELD_SETTINGS_PATH_SUFFIX,
  LEGACY_ISSUE_VIEWS,
} from '../legacy-issue-datasets';
import { LegacyIssuePageHeader } from './LegacyIssuePageParts';

type LegacyIssueCodeFieldSource = 'system' | 'module';

interface LegacyIssueCodeField {
  active: boolean;
  fieldId: string | null;
  id: string;
  key: string;
  labelEn: string;
  labelKo: string;
  moduleKey: string | null;
  options: string[];
  readonly: boolean;
  source: LegacyIssueCodeFieldSource;
}

export function CoreBusinessLegacyIssueCommonCodeView() {
  const { workspaceSlug = '' } = useParams<{ workspaceSlug: string }>();
  const { token } = useAuth();
  const { t } = useTranslation(['apps', 'common', 'shell']);
  const toast = useToast();
  const fieldSettingsHref = workspaceSlug
    ? buildWorkspaceAppPath(
        workspaceSlug,
        'legacy-issues',
        LEGACY_ISSUE_FIELD_SETTINGS_PATH_SUFFIX,
      )
    : '#';
  const [systemFields, setSystemFields] = useState<LegacyIssueSystemField[]>(
    [],
  );
  const [moduleFields, setModuleFields] = useState<LegacyIssueModuleField[]>(
    [],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [optionDraft, setOptionDraft] = useState<string[]>([]);
  const [optionValue, setOptionValue] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadFields = useCallback(async () => {
    if (!workspaceSlug || !token) return;
    setLoading(true);
    try {
      const [systemResponse, moduleResponse] = await Promise.all([
        fetchLegacyIssueSystemFields({
          datasetKey: LEGACY_ISSUE_DEFAULT_DATASET_KEY,
          token,
          workspaceSlug,
        }),
        fetchLegacyIssueModuleFields({
          includeInactive: true,
          token,
          workspaceSlug,
        }),
      ]);
      setSystemFields(systemResponse.items);
      setModuleFields(moduleResponse.items);
    } catch (loadError) {
      toast.error(
        errorMessage(loadError, t('coreBusiness.commonCode.errors.loadFailed')),
      );
    } finally {
      setLoading(false);
    }
  }, [t, toast, token, workspaceSlug]);

  useEffect(() => {
    void loadFields();
  }, [loadFields]);

  const codeFields = useMemo<LegacyIssueCodeField[]>(() => {
    const systemCodeFields = systemFields
      .filter((field) => field.field_type === 'select' && !field.readonly)
      .map((field) => ({
        active: field.active,
        fieldId: null,
        id: `system:${field.key}`,
        key: field.key,
        labelEn: field.label_en,
        labelKo: field.label_ko,
        moduleKey: null,
        options: field.options,
        readonly: field.readonly,
        source: 'system' as const,
      }));
    const moduleCodeFields = moduleFields
      .filter((field) => field.field_type === 'select')
      .map((field) => ({
        active: field.active,
        fieldId: field.id,
        id: `module:${field.id}`,
        key: field.field_key,
        labelEn: field.label_en,
        labelKo: field.label_ko,
        moduleKey: field.module_key,
        options: field.options,
        readonly: false,
        source: 'module' as const,
      }));
    return [...systemCodeFields, ...moduleCodeFields].sort((left, right) => {
      if (left.source !== right.source) {
        return left.source === 'system' ? -1 : 1;
      }
      return left.labelKo.localeCompare(right.labelKo);
    });
  }, [moduleFields, systemFields]);

  const selectedField = codeFields.find((field) => field.id === selectedId);

  useEffect(() => {
    if (codeFields.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !codeFields.some((field) => field.id === selectedId)) {
      setSelectedId(codeFields[0].id);
    }
  }, [codeFields, selectedId]);

  useEffect(() => {
    setOptionDraft(selectedField?.options ?? []);
    setOptionValue('');
  }, [selectedField?.id, selectedField?.options]);

  const optionCanAdd = splitOptionText(optionValue).some(
    (option) => !optionDraft.includes(option),
  );

  function addOption(rawValue = optionValue) {
    const nextOptions = mergeOptions(optionDraft, splitOptionText(rawValue));
    if (nextOptions.length !== optionDraft.length) {
      setOptionDraft(nextOptions);
    }
    setOptionValue('');
  }

  function removeOption(option: string) {
    setOptionDraft((current) => current.filter((item) => item !== option));
  }

  async function saveOptions() {
    if (!workspaceSlug || !token || !selectedField || saving) return;
    const normalizedOptions = normalizeOptions(optionDraft);
    if (!normalizedOptions) {
      toast.error(t('coreBusiness.commonCode.errors.optionsRequired'));
      return;
    }
    setSaving(true);
    try {
      if (selectedField.source === 'system') {
        await updateLegacyIssueSystemField({
          fieldKey: selectedField.key,
          payload: {
            dataset_key: LEGACY_ISSUE_DEFAULT_DATASET_KEY,
            options: normalizedOptions,
          },
          token,
          workspaceSlug,
        });
      } else if (selectedField.fieldId) {
        await updateLegacyIssueModuleField({
          fieldId: selectedField.fieldId,
          payload: { options: normalizedOptions },
          token,
          workspaceSlug,
        });
      }
      toast.success(t('coreBusiness.commonCode.status.saved'));
      await loadFields();
    } catch (saveError) {
      toast.error(
        errorMessage(saveError, t('coreBusiness.commonCode.errors.saveFailed')),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="flex h-full min-h-0 bg-app-bg text-app-ink">
      <section className="flex min-w-0 flex-1 flex-col">
        <LegacyIssuePageHeader
          actions={null}
          eyebrow={t('coreBusiness.commonCode.eyebrow')}
          title={t('coreBusiness.commonCode.title')}
        />
        <CommonCodeGuidance fieldSettingsHref={fieldSettingsHref} />
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_24rem] overflow-hidden">
          <section className="min-h-0 overflow-auto px-4 py-4">
            <LegacyIssueCodeFieldList
              fieldSettingsHref={fieldSettingsHref}
              fields={codeFields}
              loading={loading}
              selectedId={selectedId}
              scopeLabel={(field) => codeFieldScopeLabel(field, t)}
              onSelect={setSelectedId}
            />
          </section>
          <aside className="min-h-0 overflow-auto border-l border-app-border bg-app-surface px-4 py-4">
            {selectedField ? (
              <div className="space-y-4">
                <div>
                  <h2 className="app-text-body-sm font-semibold">
                    {selectedField.labelKo}
                  </h2>
                  <div className="app-text-micro text-app-ink/45">
                    {codeFieldScopeLabel(selectedField, t)}
                  </div>
                </div>
                <FieldLabel label={t('coreBusiness.commonCode.options')}>
                  <div className="flex gap-2">
                    <input
                      className="app-field-input-sm h-8 min-w-0 flex-1"
                      placeholder={t(
                        'coreBusiness.commonCode.optionPlaceholder',
                      )}
                      value={optionValue}
                      onChange={(event) => setOptionValue(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          addOption();
                        }
                      }}
                      onPaste={(event) => {
                        const pastedText = event.clipboardData.getData('text');
                        if (/[\n,]/.test(pastedText)) {
                          event.preventDefault();
                          addOption(pastedText);
                        }
                      }}
                    />
                    <button
                      className="inline-flex h-8 shrink-0 items-center justify-center gap-1 rounded-md border border-app-border bg-app-bg px-3 app-text-caption font-medium text-app-ink/70 hover:bg-app-surface-hover disabled:opacity-40"
                      disabled={!optionCanAdd}
                      type="button"
                      onClick={() => addOption()}
                    >
                      <Plus size={14} />
                      {t('common:actions.add')}
                    </button>
                  </div>
                </FieldLabel>
                {optionDraft.length > 0 ? (
                  <ol className="max-h-72 overflow-auto rounded-md border border-app-border bg-app-bg">
                    {optionDraft.map((option, index) => (
                      <li
                        key={option}
                        className="flex min-h-9 items-center gap-2 border-b border-app-border px-3 py-1.5 last:border-b-0"
                      >
                        <span className="w-6 shrink-0 text-right app-text-micro tabular-nums text-app-ink/35">
                          {index + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate app-text-caption text-app-ink/75">
                          {option}
                        </span>
                        <button
                          aria-label={t(
                            'coreBusiness.commonCode.removeOption',
                            { option },
                          )}
                          className="inline-flex size-7 shrink-0 items-center justify-center rounded text-app-ink/45 hover:bg-app-surface-hover hover:text-app-ink"
                          type="button"
                          onClick={() => removeOption(option)}
                        >
                          <X size={14} />
                        </button>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <div className="rounded-md border border-dashed border-app-border bg-app-bg px-3 py-3 app-text-caption text-app-ink/45">
                    {t('coreBusiness.commonCode.optionsEmpty')}
                  </div>
                )}
                <button
                  className="inline-flex h-8 w-full items-center justify-center gap-2 rounded-md bg-app-accent px-3 app-text-caption font-medium text-app-accent-fg hover:bg-app-accent/90 disabled:opacity-50"
                  disabled={saving || normalizeOptions(optionDraft) === null}
                  type="button"
                  onClick={() => void saveOptions()}
                >
                  {saving ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <Save size={15} />
                  )}
                  {t('common:actions.save')}
                </button>
              </div>
            ) : (
              <LegacyIssueCodeEmpty
                icon={
                  loading ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <Plus size={18} />
                  )
                }
                label={
                  loading
                    ? t('common:feedback.loading')
                    : t('coreBusiness.commonCode.empty')
                }
                description={
                  loading
                    ? undefined
                    : t('coreBusiness.commonCode.emptyDescription')
                }
                action={
                  loading ? undefined : (
                    <FieldSettingsLink href={fieldSettingsHref} />
                  )
                }
              />
            )}
          </aside>
        </div>
      </section>
    </main>
  );
}

function LegacyIssueCodeFieldList({
  fieldSettingsHref,
  fields,
  loading,
  onSelect,
  scopeLabel,
  selectedId,
}: {
  fieldSettingsHref: string;
  fields: LegacyIssueCodeField[];
  loading: boolean;
  onSelect: (id: string) => void;
  scopeLabel: (field: LegacyIssueCodeField) => string;
  selectedId: string | null;
}) {
  const { t } = useTranslation(['apps', 'common']);
  if (loading) {
    return (
      <LegacyIssueCodeEmpty
        icon={<Loader2 size={18} className="animate-spin" />}
        label={t('common:feedback.loading')}
      />
    );
  }
  if (fields.length === 0) {
    return (
      <LegacyIssueCodeEmpty
        icon={<Plus size={18} />}
        label={t('coreBusiness.commonCode.empty')}
        description={t('coreBusiness.commonCode.emptyDescription')}
        action={<FieldSettingsLink href={fieldSettingsHref} />}
      />
    );
  }
  return (
    <div className="overflow-hidden rounded-md border border-app-border bg-app-surface">
      <table className="w-full table-fixed border-collapse app-text-caption">
        <thead className="bg-app-bg text-left text-app-ink/55">
          <tr>
            <th className="px-3 py-2 font-medium">
              {t('coreBusiness.commonCode.columns.field')}
            </th>
            <th className="w-44 px-3 py-2 font-medium">
              {t('coreBusiness.commonCode.columns.scope')}
            </th>
            <th className="w-24 px-3 py-2 font-medium">
              {t('coreBusiness.commonCode.columns.options')}
            </th>
            <th className="w-24 px-3 py-2 font-medium">
              {t('coreBusiness.commonCode.columns.status')}
            </th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <tr
              key={field.id}
              className={cn(
                'cursor-pointer border-t border-app-border hover:bg-app-surface-hover',
                selectedId === field.id && 'bg-app-accent/5',
                !field.active && 'text-app-ink/45',
              )}
              onClick={() => onSelect(field.id)}
            >
              <td className="truncate px-3 py-2">
                <div className="truncate font-medium">{field.labelKo}</div>
                <div className="truncate app-text-micro text-app-ink/45">
                  {field.key}
                </div>
              </td>
              <td className="truncate px-3 py-2 text-app-ink/65">
                {scopeLabel(field)}
              </td>
              <td className="px-3 py-2 text-app-ink/65">
                {field.options.length}
              </td>
              <td className="px-3 py-2 text-app-ink/65">
                {field.active
                  ? t('coreBusiness.fieldSettings.status.active')
                  : t('coreBusiness.fieldSettings.status.inactive')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FieldLabel({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <label className="block space-y-1">
      <span className="block app-text-micro font-medium text-app-ink/55">
        {label}
      </span>
      {children}
    </label>
  );
}

function LegacyIssueCodeEmpty({
  action,
  description,
  icon,
  label,
}: {
  action?: ReactNode;
  description?: string;
  icon: ReactNode;
  label: string;
}) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-app-border bg-app-surface px-4 text-center app-text-caption text-app-ink/50">
      {icon}
      <div className="space-y-1">
        <div>{label}</div>
        {description ? (
          <div className="max-w-sm app-text-micro leading-relaxed text-app-ink/45">
            {description}
          </div>
        ) : null}
      </div>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}

function CommonCodeGuidance({
  fieldSettingsHref,
}: {
  fieldSettingsHref: string;
}) {
  const { t } = useTranslation(['apps']);
  return (
    <div className="border-b border-app-border bg-app-surface-sidebar px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-4xl app-text-caption leading-relaxed text-app-ink/60">
          {t('coreBusiness.commonCode.guidance')}
        </p>
        <FieldSettingsLink href={fieldSettingsHref} />
      </div>
    </div>
  );
}

function FieldSettingsLink({ href }: { href: string }) {
  const { t } = useTranslation(['apps']);
  return (
    <Link
      className="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-md border border-app-border bg-app-bg px-3 app-text-caption font-medium text-app-ink/70 hover:bg-app-surface-hover"
      to={href}
    >
      <Settings size={14} />
      {t('coreBusiness.commonCode.openFieldSettings')}
    </Link>
  );
}

function codeFieldScopeLabel(
  field: LegacyIssueCodeField,
  t: (key: string, options?: Record<string, unknown>) => string,
) {
  if (field.source === 'system') {
    return t('coreBusiness.commonCode.scope.common');
  }
  const view = field.moduleKey
    ? LEGACY_ISSUE_VIEWS[field.moduleKey as keyof typeof LEGACY_ISSUE_VIEWS]
    : null;
  return view
    ? t(`nav.${view.navItemId}`, { ns: 'shell' })
    : t('coreBusiness.commonCode.scope.module');
}

function splitOptionText(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function mergeOptions(currentOptions: string[], incomingOptions: string[]) {
  return Array.from(new Set([...currentOptions, ...incomingOptions]));
}

function normalizeOptions(value: string[]): string[] | null {
  const options = Array.from(
    new Set(value.map((item) => item.trim()).filter(Boolean)),
  );
  return options.length > 0 ? options : null;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
