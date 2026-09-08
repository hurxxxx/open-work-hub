import { KeyRound, RefreshCw, Save } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, useFeedback } from '@open-work-hub/ui';

import {
  AdminAiModelSettingsApiError,
  discoverAdminAiModelProviderModels,
  getAdminAiModelSettings,
  isAiModelProviderReady,
  updateAdminAiModelProvider,
  type AdminAiModelSettings,
  type AiModelProviderConfig,
  type AiModelProviderUpdate,
} from './admin-ai-model-settings-api';
import {
  Badge,
  EmptyPanel,
  FORM_FIELD_CLASS as fieldClassName,
  SurfaceCard,
} from './admin-shared';

export interface LlmProviderDraft {
  enabled: boolean;
  endpointUrl: string;
  defaultModelId: string;
  apiKey: string;
  clearApiKey: boolean;
}

export function buildLlmProviderUpdate(
  draft: LlmProviderDraft,
  provider: AiModelProviderConfig,
  registryDigest: string,
): AiModelProviderUpdate {
  const apiKey = draft.apiKey.trim();
  return {
    expected_registry_digest: registryDigest,
    expected_version: provider.version,
    enabled: draft.enabled,
    endpoint_url: draft.endpointUrl.trim() || null,
    default_model_id: draft.defaultModelId || null,
    ...(apiKey ? { api_key: apiKey } : {}),
    ...(draft.clearApiKey ? { clear_api_key: true } : {}),
  };
}

function initialDrafts(
  data: AdminAiModelSettings,
): Record<string, LlmProviderDraft> {
  return Object.fromEntries(
    data.providers.map((provider) => [
      provider.provider_id,
      {
        enabled: provider.enabled,
        endpointUrl: provider.endpoint_url ?? '',
        defaultModelId: provider.default_model_id ?? '',
        apiKey: '',
        clearApiKey: false,
      },
    ]),
  );
}

function defaultModelLabel(
  data: AdminAiModelSettings,
  provider: AiModelProviderConfig,
): string {
  const model = data.models.find(
    (item) => item.id === provider.default_model_id,
  );
  return model ? `${model.display_name} · ${model.model_key}` : '—';
}

export function AdminLlmProviderSettingsSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const toast = useFeedback();
  const [data, setData] = useState<AdminAiModelSettings | null>(null);
  const [drafts, setDrafts] = useState<Record<string, LlmProviderDraft>>({});
  const [selectedProviderId, setSelectedProviderId] = useState('local');
  const [loading, setLoading] = useState(true);
  const [savingProviderId, setSavingProviderId] = useState<string | null>(null);
  const [syncingProviderId, setSyncingProviderId] = useState<string | null>(
    null,
  );

  const applySnapshot = useCallback((snapshot: AdminAiModelSettings) => {
    setData(snapshot);
    setDrafts(initialDrafts(snapshot));
    setSelectedProviderId((current) =>
      snapshot.providers.some((provider) => provider.provider_id === current)
        ? current
        : (snapshot.providers[0]?.provider_id ?? 'local'),
    );
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

  const selectedProvider = data?.providers.find(
    (provider) => provider.provider_id === selectedProviderId,
  );
  const selectedDraft = selectedProvider
    ? drafts[selectedProvider.provider_id]
    : undefined;
  const selectedModels = useMemo(
    () =>
      data?.models.filter(
        (model) => model.provider_id === selectedProviderId,
      ) ?? [],
    [data?.models, selectedProviderId],
  );

  if (loading && !data) {
    return (
      <EmptyPanel
        description={t(
          'admin.console.aiSecurity.llmProviders.loadingDescription',
        )}
        title={t('admin.console.aiSecurity.llmProviders.loadingTitle')}
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

  const updateDraft = (
    providerId: string,
    update: Partial<LlmProviderDraft>,
  ) => {
    setDrafts((current) => ({
      ...current,
      [providerId]: { ...current[providerId], ...update },
    }));
  };

  const saveProvider = async (
    provider: AiModelProviderConfig,
    draft: LlmProviderDraft,
  ) => {
    setSavingProviderId(provider.provider_id);
    try {
      applySnapshot(
        await updateAdminAiModelProvider(
          token,
          provider.provider_id,
          buildLlmProviderUpdate(draft, provider, data.registry_digest),
        ),
      );
      toast.success(t('admin.console.aiSecurity.modelSettings.saved'));
    } catch (error) {
      if (
        error instanceof AdminAiModelSettingsApiError &&
        error.status === 409
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
      setSavingProviderId(null);
    }
  };

  const discoverModels = async (provider: AiModelProviderConfig) => {
    setSyncingProviderId(provider.provider_id);
    try {
      const snapshot = await discoverAdminAiModelProviderModels(
        token,
        provider.provider_id,
        data.registry_digest,
      );
      applySnapshot(snapshot);
      toast.success(
        t('admin.console.aiSecurity.llmProviders.discoverySucceeded', {
          count: snapshot.models.filter(
            (model) => model.provider_id === provider.provider_id,
          ).length,
        }),
      );
    } catch (error) {
      toast.error(
        error instanceof AdminAiModelSettingsApiError
          ? error.message
          : t('admin.console.aiSecurity.llmProviders.discoveryFailed'),
      );
    } finally {
      setSyncingProviderId(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="app-text-title-sm text-app-ink">
            {t('admin.console.aiSecurity.llmProviders.title')}
          </h2>
          <p className="app-text-body-sm text-app-ink/60">
            {t('admin.console.aiSecurity.llmProviders.description')}
          </p>
        </div>
        <Button
          disabled={loading || savingProviderId !== null}
          onClick={() => void load()}
          size="icon"
          title={t('admin.console.usage.refresh')}
          variant="secondary"
        >
          <RefreshCw size={15} />
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        {data.providers.map((provider) => {
          const ready = isAiModelProviderReady(data, provider);
          const providerModels = data.models.filter(
            (model) => model.provider_id === provider.provider_id,
          );
          return (
            <button
              className={`min-w-0 rounded-md border px-3 py-2 text-left transition-colors ${
                selectedProviderId === provider.provider_id
                  ? 'border-app-accent bg-app-accent/5'
                  : 'border-app-border bg-app-surface hover:bg-app-surface-hover'
              }`}
              key={provider.provider_id}
              onClick={() => setSelectedProviderId(provider.provider_id)}
              type="button"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="app-text-control truncate text-app-ink">
                  {provider.display_name}
                </span>
                <Badge tone={provider.enabled ? 'green' : 'default'}>
                  {t(
                    provider.enabled
                      ? 'admin.console.aiSecurity.modelSettings.status.enabled'
                      : 'admin.console.aiSecurity.modelSettings.status.disabled',
                  )}
                </Badge>
              </div>
              <div
                className="app-text-caption mt-1 truncate text-app-ink/55"
                title={defaultModelLabel(data, provider)}
              >
                {defaultModelLabel(data, provider)}
              </div>
              <div className="app-text-caption mt-1 flex items-center gap-2 text-app-ink/45">
                <span>
                  {t('admin.console.aiSecurity.llmProviders.modelCount', {
                    count: providerModels.length,
                  })}
                </span>
                {!ready && provider.enabled ? (
                  <span className="text-app-warning-text">
                    {t(
                      'admin.console.aiSecurity.modelSettings.status.needsSetup',
                    )}
                  </span>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>

      {selectedProvider && selectedDraft ? (
        <SurfaceCard
          description={t(
            'admin.console.aiSecurity.llmProviders.connectionDescription',
            { name: selectedProvider.display_name },
          )}
          title={selectedProvider.display_name}
        >
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void saveProvider(selectedProvider, selectedDraft);
            }}
          >
            <div className="grid gap-3 md:grid-cols-2">
              <label className="block space-y-1">
                <span className="app-text-caption text-app-ink/60">
                  {t(
                    'admin.console.aiSecurity.modelSettings.providers.endpoint',
                  )}
                </span>
                <input
                  className={fieldClassName}
                  onChange={(event) =>
                    updateDraft(selectedProvider.provider_id, {
                      endpointUrl: event.target.value,
                    })
                  }
                  placeholder={t(
                    'admin.console.aiSecurity.modelSettings.providers.endpointPlaceholder',
                  )}
                  type="url"
                  value={selectedDraft.endpointUrl}
                />
                <p className="app-text-caption text-app-ink/45">
                  {t(
                    selectedProvider.endpoint_source === 'default'
                      ? 'admin.console.aiSecurity.llmProviders.endpointDefault'
                      : 'admin.console.aiSecurity.llmProviders.endpointCustom',
                  )}
                </p>
              </label>
              <label className="block space-y-1">
                <span className="app-text-caption text-app-ink/60">
                  {t(
                    'admin.console.aiSecurity.modelSettings.providers.defaultModel',
                  )}
                </span>
                <select
                  className="app-field-input"
                  onChange={(event) =>
                    updateDraft(selectedProvider.provider_id, {
                      defaultModelId: event.target.value,
                    })
                  }
                  value={selectedDraft.defaultModelId}
                >
                  <option value="">
                    {t(
                      'admin.console.aiSecurity.modelSettings.models.selectModel',
                    )}
                  </option>
                  {selectedModels
                    .filter((model) => model.enabled)
                    .map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.display_name} · {model.model_key}
                      </option>
                    ))}
                </select>
              </label>
            </div>

            {selectedProvider.credential_kind === 'api_key' ? (
              <div className="space-y-1">
                <label
                  className="app-text-caption block text-app-ink/60"
                  htmlFor={`provider-api-key-${selectedProvider.provider_id}`}
                >
                  {t('admin.console.aiSecurity.modelSettings.providers.apiKey')}
                </label>
                <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                  <input
                    autoComplete="new-password"
                    className={fieldClassName}
                    disabled={selectedDraft.clearApiKey}
                    id={`provider-api-key-${selectedProvider.provider_id}`}
                    onChange={(event) =>
                      updateDraft(selectedProvider.provider_id, {
                        apiKey: event.target.value,
                      })
                    }
                    placeholder={t(
                      selectedProvider.has_api_key
                        ? 'admin.console.aiSecurity.modelSettings.providers.apiKeyStored'
                        : 'admin.console.aiSecurity.modelSettings.providers.apiKeyMissing',
                    )}
                    type="password"
                    value={selectedDraft.apiKey}
                  />
                  <div className="flex h-9 items-center gap-2">
                    <KeyRound size={14} className="text-app-ink/45" />
                    <Badge
                      tone={selectedProvider.has_api_key ? 'green' : 'amber'}
                    >
                      {t(
                        selectedProvider.has_api_key
                          ? 'admin.console.aiSecurity.llmProviders.secretStored'
                          : 'admin.console.aiSecurity.llmProviders.secretMissing',
                      )}
                    </Badge>
                  </div>
                </div>
                <p className="app-text-caption text-app-ink/45">
                  {t('admin.console.aiSecurity.llmProviders.secretNotice')}
                </p>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-app-border pt-3">
              <div className="flex flex-wrap items-center gap-4">
                <label className="app-text-body-sm flex items-center gap-2 text-app-ink">
                  <input
                    checked={selectedDraft.enabled}
                    onChange={(event) =>
                      updateDraft(selectedProvider.provider_id, {
                        enabled: event.target.checked,
                      })
                    }
                    type="checkbox"
                  />
                  {t(
                    'admin.console.aiSecurity.modelSettings.providers.enabled',
                  )}
                </label>
                {selectedProvider.credential_kind === 'api_key' &&
                selectedProvider.has_api_key ? (
                  <label className="app-text-caption flex items-center gap-2 text-app-danger-text">
                    <input
                      checked={selectedDraft.clearApiKey}
                      onChange={(event) =>
                        updateDraft(selectedProvider.provider_id, {
                          apiKey: '',
                          clearApiKey: event.target.checked,
                        })
                      }
                      type="checkbox"
                    />
                    {t(
                      'admin.console.aiSecurity.modelSettings.providers.clearApiKey',
                    )}
                  </label>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  disabled={
                    savingProviderId !== null ||
                    syncingProviderId !== null ||
                    (selectedProvider.credential_kind === 'api_key' &&
                      !selectedProvider.has_api_key)
                  }
                  onClick={() => void discoverModels(selectedProvider)}
                  type="button"
                  variant="secondary"
                >
                  <RefreshCw size={15} />
                  {t('admin.console.aiSecurity.llmProviders.discoverModels')}
                </Button>
                <Button
                  disabled={
                    savingProviderId !== null || syncingProviderId !== null
                  }
                  type="submit"
                  variant="primary"
                >
                  <Save size={15} />
                  {t('common:actions.save')}
                </Button>
              </div>
            </div>
          </form>
        </SurfaceCard>
      ) : null}
    </div>
  );
}
