import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronRight, Plus, RefreshCw, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button, useToast } from '@open-work-hub/ui';

import {
  AdminAiModelSettingsApiError,
  createAdminAiModel,
  getAdminAiModelSettings,
  updateAdminAiModel,
  type AdminAiModelSettings,
} from './admin-ai-model-settings-api';
import {
  Badge,
  EmptyPanel,
  FORM_FIELD_CLASS as fieldClassName,
  SurfaceCard,
} from './admin-shared';

const MODEL_CAPABILITIES = ['chat', 'tool_calling', 'vision'] as const;

interface ModelDraft {
  modelKey: string;
  displayName: string;
  capabilities: string[];
  enabled: boolean;
}

interface NewModelDraft extends ModelDraft {
  providerId: string;
}

const EMPTY_NEW_MODEL: NewModelDraft = {
  providerId: 'local',
  modelKey: '',
  displayName: '',
  capabilities: ['chat'],
  enabled: true,
};

function initialModelDrafts(
  data: AdminAiModelSettings,
): Record<string, ModelDraft> {
  return Object.fromEntries(
    data.models.map((model) => [
      model.id,
      {
        modelKey: model.model_key,
        displayName: model.display_name,
        capabilities: model.capabilities,
        enabled: model.enabled,
      },
    ]),
  );
}

function toggleCapability(
  capabilities: string[],
  capability: string,
): string[] {
  return capabilities.includes(capability)
    ? capabilities.filter((item) => item !== capability)
    : [...capabilities, capability];
}

function CapabilityPicker({
  value,
  onChange,
}: {
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <fieldset className="space-y-1.5">
      <legend className="app-text-caption text-app-ink/60">
        {t('admin.console.aiSecurity.modelSettings.models.capabilities')}
      </legend>
      <div className="flex flex-wrap gap-2">
        {MODEL_CAPABILITIES.map((capability) => (
          <label
            className="app-text-caption inline-flex items-center gap-1.5 rounded-md border border-app-border px-2 py-1.5 text-app-ink/75"
            key={capability}
          >
            <input
              checked={value.includes(capability)}
              onChange={() => onChange(toggleCapability(value, capability))}
              type="checkbox"
            />
            {t(
              `admin.console.aiSecurity.modelSettings.capabilities.${capability}`,
            )}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function AdminAiModelSettingsSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const toast = useToast();
  const [data, setData] = useState<AdminAiModelSettings | null>(null);
  const [modelDrafts, setModelDrafts] = useState<Record<string, ModelDraft>>(
    {},
  );
  const [newModel, setNewModel] = useState<NewModelDraft>(EMPTY_NEW_MODEL);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [modelQuery, setModelQuery] = useState('');
  const [showNewModel, setShowNewModel] = useState(false);

  const applySnapshot = useCallback((snapshot: AdminAiModelSettings) => {
    setData(snapshot);
    setModelDrafts(initialModelDrafts(snapshot));
    setNewModel((current) => ({
      ...EMPTY_NEW_MODEL,
      providerId: snapshot.providers.some(
        (provider) => provider.provider_id === current.providerId,
      )
        ? current.providerId
        : (snapshot.providers[0]?.provider_id ?? 'local'),
    }));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      applySnapshot(await getAdminAiModelSettings(token));
    } catch {
      toast.error(t('admin.console.aiSecurity.modelSettings.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [applySnapshot, t, toast, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const runMutation = useCallback(
    async (key: string, mutation: () => Promise<AdminAiModelSettings>) => {
      setSavingKey(key);
      try {
        applySnapshot(await mutation());
        toast.success(t('admin.console.aiSecurity.modelSettings.saved'));
      } catch (error) {
        if (
          error instanceof AdminAiModelSettingsApiError &&
          error.status === 409 &&
          (error.code === null ||
            error.code === 'admin.ai_model_registry_changed' ||
            error.code === 'admin.ai_model_version_conflict')
        ) {
          toast.info(t('admin.console.aiSecurity.modelSettings.conflict'));
          await load();
        } else {
          toast.error(
            error instanceof AdminAiModelSettingsApiError
              ? error.message
              : t('admin.console.aiSecurity.modelSettings.saveFailed'),
          );
        }
      } finally {
        setSavingKey(null);
      }
    },
    [applySnapshot, load, t, toast],
  );

  const filteredModels = useMemo(() => {
    const normalized = modelQuery.trim().toLocaleLowerCase();
    if (!data || !normalized) return data?.models ?? [];
    return data.models.filter((model) =>
      [
        model.display_name,
        model.model_key,
        model.provider_id,
        ...model.capabilities,
      ]
        .join(' ')
        .toLocaleLowerCase()
        .includes(normalized),
    );
  }, [data, modelQuery]);

  if (loading && !data) {
    return (
      <EmptyPanel
        description={t(
          'admin.console.aiSecurity.modelSettings.loadingDescription',
        )}
        title={t('admin.console.aiSecurity.modelSettings.loadingTitle')}
      />
    );
  }

  if (!data) {
    return (
      <EmptyPanel
        description={t(
          'admin.console.aiSecurity.modelSettings.emptyDescription',
        )}
        title={t('admin.console.aiSecurity.modelSettings.emptyTitle')}
      />
    );
  }

  return (
    <div className="space-y-3">
      <div
        className="flex min-h-9 items-center justify-between gap-3 rounded-md border border-app-border bg-app-surface px-3 py-1.5"
        title={t('admin.console.aiSecurity.modelSettings.registry.digest', {
          digest: data.registry_digest,
        })}
      >
        <div className="app-text-caption flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-app-ink/60">
          <span>
            {t('admin.console.aiSecurity.modelSettings.models.title')}{' '}
            <strong className="font-semibold text-app-ink">
              {data.models.filter((model) => model.enabled).length}/
              {data.models.length}
            </strong>
          </span>
          <span className="hidden h-3 w-px bg-app-border sm:block" />
          <span>
            {t('admin.console.aiSecurity.routingOverview.total')}{' '}
            <strong className="font-semibold text-app-ink">
              {data.workloads.length}
            </strong>
          </span>
        </div>
        <Button
          aria-label={t('admin.console.usage.refresh')}
          className="shrink-0"
          disabled={loading || savingKey !== null}
          onClick={() => void load()}
          size="icon"
          title={t('admin.console.usage.refresh')}
          variant="secondary"
        >
          <RefreshCw size={15} />
        </Button>
      </div>

      <SurfaceCard
        description={t(
          'admin.console.aiSecurity.modelSettings.models.description',
        )}
        title={t('admin.console.aiSecurity.modelSettings.models.title')}
        actions={
          <Button
            onClick={() => setShowNewModel((current) => !current)}
            variant={showNewModel ? 'secondary' : 'primary'}
          >
            <Plus size={15} />
            {t('admin.console.aiSecurity.modelSettings.models.addTitle')}
          </Button>
        }
      >
        <div className="space-y-4">
          <input
            aria-label={t(
              'admin.console.aiSecurity.modelSettings.models.search',
            )}
            className={fieldClassName}
            onChange={(event) => setModelQuery(event.target.value)}
            placeholder={t(
              'admin.console.aiSecurity.modelSettings.models.search',
            )}
            value={modelQuery}
          />
          {showNewModel ? (
            <form
              className="space-y-3 rounded-md border border-dashed border-app-border p-4"
              onSubmit={(event) => {
                event.preventDefault();
                if (
                  !newModel.modelKey.trim() ||
                  !newModel.displayName.trim() ||
                  newModel.capabilities.length === 0
                ) {
                  toast.error(
                    t('admin.console.aiSecurity.modelSettings.models.invalid'),
                  );
                  return;
                }
                void runMutation('model:new', () =>
                  createAdminAiModel(token, {
                    expected_registry_digest: data.registry_digest,
                    provider_id: newModel.providerId,
                    model_key: newModel.modelKey.trim(),
                    display_name: newModel.displayName.trim(),
                    capabilities: newModel.capabilities,
                    enabled: newModel.enabled,
                  }),
                );
              }}
            >
              <div className="flex items-center gap-2">
                <Plus size={16} />
                <h3 className="app-text-control text-app-ink">
                  {t('admin.console.aiSecurity.modelSettings.models.addTitle')}
                </h3>
              </div>
              <div className="grid gap-3 lg:grid-cols-3">
                <label className="block space-y-1">
                  <span className="app-text-caption text-app-ink/60">
                    {t(
                      'admin.console.aiSecurity.modelSettings.models.provider',
                    )}
                  </span>
                  <select
                    className="app-field-input"
                    onChange={(event) =>
                      setNewModel((current) => ({
                        ...current,
                        providerId: event.target.value,
                      }))
                    }
                    value={newModel.providerId}
                  >
                    {data.providers.map((provider) => (
                      <option
                        key={provider.provider_id}
                        value={provider.provider_id}
                      >
                        {provider.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block space-y-1">
                  <span className="app-text-caption text-app-ink/60">
                    {t(
                      'admin.console.aiSecurity.modelSettings.models.modelKey',
                    )}
                  </span>
                  <input
                    className={fieldClassName}
                    onChange={(event) =>
                      setNewModel((current) => ({
                        ...current,
                        modelKey: event.target.value,
                      }))
                    }
                    value={newModel.modelKey}
                  />
                </label>
                <label className="block space-y-1">
                  <span className="app-text-caption text-app-ink/60">
                    {t(
                      'admin.console.aiSecurity.modelSettings.models.displayName',
                    )}
                  </span>
                  <input
                    className={fieldClassName}
                    onChange={(event) =>
                      setNewModel((current) => ({
                        ...current,
                        displayName: event.target.value,
                      }))
                    }
                    value={newModel.displayName}
                  />
                </label>
              </div>
              <CapabilityPicker
                onChange={(capabilities) =>
                  setNewModel((current) => ({ ...current, capabilities }))
                }
                value={newModel.capabilities}
              />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="app-text-body-sm flex items-center gap-2 text-app-ink">
                  <input
                    checked={newModel.enabled}
                    onChange={(event) =>
                      setNewModel((current) => ({
                        ...current,
                        enabled: event.target.checked,
                      }))
                    }
                    type="checkbox"
                  />
                  {t('admin.console.aiSecurity.modelSettings.models.enabled')}
                </label>
                <Button
                  disabled={savingKey !== null}
                  type="submit"
                  variant="primary"
                >
                  <Plus size={16} />
                  {t('common:actions.add')}
                </Button>
              </div>
            </form>
          ) : null}

          <div className="divide-y divide-app-border overflow-hidden rounded-md border border-app-border">
            {filteredModels.map((model) => {
              const draft = modelDrafts[model.id];
              if (!draft) return null;
              return (
                <details className="group bg-app-surface" key={model.id}>
                  <summary className="flex cursor-pointer list-none flex-col gap-2 px-3 py-2.5 marker:hidden hover:bg-app-surface-hover sm:flex-row sm:items-center sm:justify-between [&::-webkit-details-marker]:hidden">
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      <ChevronRight
                        className="shrink-0 text-app-ink/40 transition-transform group-open:rotate-90"
                        size={14}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="app-text-body-sm truncate font-semibold text-app-ink">
                          {draft.displayName}
                        </div>
                        <div
                          className="app-text-caption truncate text-app-ink/50"
                          title={`${model.provider_id} · ${draft.modelKey} · ${model.id}`}
                        >
                          {model.provider_id} · {draft.modelKey}
                        </div>
                      </div>
                    </div>
                    <div className="flex min-w-0 flex-wrap items-center gap-1 sm:justify-end">
                      <Badge
                        tone={
                          model.source === 'discovered' ? 'purple' : 'default'
                        }
                      >
                        {t(
                          `admin.console.aiSecurity.modelSettings.models.sources.${model.source}`,
                        )}
                      </Badge>
                      {model.discovery_status === 'stale' ? (
                        <Badge tone="amber">
                          {t(
                            'admin.console.aiSecurity.modelSettings.models.stale',
                          )}
                        </Badge>
                      ) : null}
                      {draft.capabilities.map((capability) => (
                        <Badge key={capability} tone="default">
                          {t(
                            `admin.console.aiSecurity.modelSettings.capabilities.${capability}`,
                            { defaultValue: capability },
                          )}
                        </Badge>
                      ))}
                      <Badge tone={draft.enabled ? 'green' : 'default'}>
                        {t(
                          draft.enabled
                            ? 'admin.console.aiSecurity.modelSettings.status.enabled'
                            : 'admin.console.aiSecurity.modelSettings.status.disabled',
                        )}
                      </Badge>
                    </div>
                  </summary>
                  <form
                    className="space-y-3 border-t border-app-border bg-app-surface-sidebar/35 p-3"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void runMutation(`model:${model.id}`, () =>
                        updateAdminAiModel(token, model.id, {
                          expected_registry_digest: data.registry_digest,
                          expected_version: model.version,
                          model_key: draft.modelKey.trim(),
                          display_name: draft.displayName.trim(),
                          capabilities: draft.capabilities,
                          enabled: draft.enabled,
                        }),
                      );
                    }}
                  >
                    <div className="grid gap-3 lg:grid-cols-2">
                      <label className="block space-y-1">
                        <span className="app-text-caption text-app-ink/60">
                          {t(
                            'admin.console.aiSecurity.modelSettings.models.modelKey',
                          )}
                        </span>
                        <input
                          className={fieldClassName}
                          disabled={model.source === 'discovered'}
                          onChange={(event) =>
                            setModelDrafts((current) => ({
                              ...current,
                              [model.id]: {
                                ...draft,
                                modelKey: event.target.value,
                              },
                            }))
                          }
                          value={draft.modelKey}
                        />
                      </label>
                      <label className="block space-y-1">
                        <span className="app-text-caption text-app-ink/60">
                          {t(
                            'admin.console.aiSecurity.modelSettings.models.displayName',
                          )}
                        </span>
                        <input
                          className={fieldClassName}
                          onChange={(event) =>
                            setModelDrafts((current) => ({
                              ...current,
                              [model.id]: {
                                ...draft,
                                displayName: event.target.value,
                              },
                            }))
                          }
                          value={draft.displayName}
                        />
                      </label>
                    </div>
                    <CapabilityPicker
                      onChange={(capabilities) =>
                        setModelDrafts((current) => ({
                          ...current,
                          [model.id]: { ...draft, capabilities },
                        }))
                      }
                      value={draft.capabilities}
                    />
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <label className="app-text-body-sm flex items-center gap-2 text-app-ink">
                        <input
                          checked={draft.enabled}
                          onChange={(event) =>
                            setModelDrafts((current) => ({
                              ...current,
                              [model.id]: {
                                ...draft,
                                enabled: event.target.checked,
                              },
                            }))
                          }
                          type="checkbox"
                        />
                        {t(
                          'admin.console.aiSecurity.modelSettings.models.enabled',
                        )}
                      </label>
                      <Button
                        disabled={
                          savingKey !== null ||
                          !draft.modelKey.trim() ||
                          !draft.displayName.trim() ||
                          draft.capabilities.length === 0
                        }
                        type="submit"
                        variant="secondary"
                      >
                        <Save size={16} />
                        {t('common:actions.save')}
                      </Button>
                    </div>
                  </form>
                </details>
              );
            })}
          </div>
        </div>
      </SurfaceCard>
    </div>
  );
}
