import { useCallback, useEffect, useState } from 'react';
import { KeyRound, RefreshCw, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button, InlineNotice, useToast } from '@open-work-hub/ui';

import {
  AdminImageModelSettingsApiError,
  getAdminImageModelSettings,
  updateAdminImageModelProfile,
  updateAdminImageModelProvider,
  type AdminImageModelSettings,
  type ImageModelProfile,
  type ImageModelProfileUpdate,
  type ImageModelProviderConfig,
  type ImageModelProviderUpdate,
} from './admin-image-model-settings-api';
import {
  Badge,
  EmptyPanel,
  FORM_FIELD_CLASS as fieldClassName,
  SurfaceCard,
} from './admin-shared';

export interface ImageProviderDraft {
  enabled: boolean;
  endpointUrl: string;
  supervisorModelId: string;
  generationModelId: string;
  apiKey: string;
  clearApiKey: boolean;
}

export function buildImageProviderUpdate(
  draft: ImageProviderDraft,
  provider: ImageModelProviderConfig,
  registryDigest: string,
): ImageModelProviderUpdate {
  const apiKey = draft.apiKey.trim();
  return {
    expected_registry_digest: registryDigest,
    expected_version: provider.version,
    enabled: draft.enabled,
    endpoint_url: draft.endpointUrl.trim() || null,
    supervisor_model_id: draft.supervisorModelId.trim() || null,
    generation_model_id: draft.generationModelId.trim() || null,
    ...(apiKey ? { api_key: apiKey } : {}),
    ...(draft.clearApiKey ? { clear_api_key: true } : {}),
  };
}

export function buildImageProfileUpdate(
  profile: ImageModelProfile,
  registryDigest: string,
): ImageModelProfileUpdate {
  return {
    expected_registry_digest: registryDigest,
    expected_version: profile.version,
    active_provider_id: profile.active_provider_id,
    brief_web_search_enabled: profile.brief_web_search_enabled,
    generation_web_search_enabled: profile.generation_web_search_enabled,
    max_iterations: profile.max_iterations,
  };
}

function providerDraft(provider: ImageModelProviderConfig): ImageProviderDraft {
  return {
    enabled: provider.enabled,
    endpointUrl: provider.endpoint_url ?? '',
    supervisorModelId: provider.supervisor_model_id ?? '',
    generationModelId: provider.generation_model_id ?? '',
    apiKey: '',
    clearApiKey: false,
  };
}

function providerDrafts(
  data: AdminImageModelSettings,
): Record<string, ImageProviderDraft> {
  return Object.fromEntries(
    data.providers.map((provider) => [
      provider.provider_id,
      providerDraft(provider),
    ]),
  );
}

export function AdminImageModelSettingsSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const toast = useToast();
  const [data, setData] = useState<AdminImageModelSettings | null>(null);
  const [drafts, setDrafts] = useState<Record<string, ImageProviderDraft>>({});
  const [profileDraft, setProfileDraft] = useState<ImageModelProfile | null>(
    null,
  );
  const [selectedProviderId, setSelectedProviderId] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const applySnapshot = useCallback((snapshot: AdminImageModelSettings) => {
    setData(snapshot);
    setDrafts(providerDrafts(snapshot));
    setProfileDraft(snapshot.profile);
    setSelectedProviderId((current) =>
      snapshot.providers.some((provider) => provider.provider_id === current)
        ? current
        : (snapshot.profile.active_provider_id ??
          snapshot.providers[0]?.provider_id ??
          ''),
    );
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      applySnapshot(await getAdminImageModelSettings(token));
    } catch (error) {
      toast.error(
        error instanceof AdminImageModelSettingsApiError
          ? error.message
          : t('admin.console.imageModels.loadFailed'),
      );
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

  const handleError = async (error: unknown) => {
    if (
      error instanceof AdminImageModelSettingsApiError &&
      error.status === 409
    ) {
      toast.info(t('admin.console.imageModels.conflict'));
      await load();
      return;
    }
    toast.error(
      error instanceof AdminImageModelSettingsApiError
        ? error.message
        : t('admin.console.imageModels.saveFailed'),
    );
  };

  const saveProvider = async () => {
    if (!data || !selectedProvider || !selectedDraft) return;
    setSaving(true);
    try {
      applySnapshot(
        await updateAdminImageModelProvider(
          token,
          selectedProvider.provider_id,
          buildImageProviderUpdate(
            selectedDraft,
            selectedProvider,
            data.registry_digest,
          ),
        ),
      );
      toast.success(t('admin.console.imageModels.saved'));
    } catch (error) {
      await handleError(error);
    } finally {
      setSaving(false);
    }
  };

  const saveProfile = async () => {
    if (!data || !profileDraft) return;
    setSaving(true);
    try {
      applySnapshot(
        await updateAdminImageModelProfile(
          token,
          buildImageProfileUpdate(profileDraft, data.registry_digest),
        ),
      );
      toast.success(t('admin.console.imageModels.saved'));
    } catch (error) {
      await handleError(error);
    } finally {
      setSaving(false);
    }
  };

  if (loading && !data) {
    return (
      <EmptyPanel
        description={t('admin.console.imageModels.loadingDescription')}
        title={t('admin.console.imageModels.loadingTitle')}
      />
    );
  }
  if (!data || !profileDraft) {
    return (
      <EmptyPanel
        description={t('admin.console.imageModels.emptyDescription')}
        title={t('admin.console.imageModels.emptyTitle')}
      />
    );
  }

  const updateProviderDraft = (update: Partial<ImageProviderDraft>) => {
    if (!selectedProvider) return;
    setDrafts((current) => ({
      ...current,
      [selectedProvider.provider_id]: {
        ...current[selectedProvider.provider_id],
        ...update,
      },
    }));
  };

  return (
    <div className="space-y-4">
      {!data.deployment_enabled ? (
        <InlineNotice tone="warning">
          {t('admin.console.imageModels.deploymentDisabled')}
        </InlineNotice>
      ) : null}

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge tone={data.ready ? 'green' : 'amber'}>
            {t(
              data.ready
                ? 'admin.console.imageModels.status.ready'
                : 'admin.console.imageModels.status.needsSetup',
            )}
          </Badge>
          {!data.ready && data.readiness_code ? (
            <span className="app-text-caption text-app-ink/55">
              {t(`admin.console.imageModels.readiness.${data.readiness_code}`, {
                defaultValue: data.readiness_code,
              })}
            </span>
          ) : null}
        </div>
        <Button
          disabled={loading || saving}
          onClick={() => void load()}
          size="icon"
          title={t('admin.console.usage.refresh')}
          variant="secondary"
        >
          <RefreshCw size={15} />
        </Button>
      </div>

      <SurfaceCard
        description={t('admin.console.imageModels.profile.description')}
        title={t('admin.console.imageModels.profile.title')}
      >
        <form
          className="grid gap-3 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            void saveProfile();
          }}
        >
          <label className="block space-y-1">
            <span className="app-text-caption text-app-ink/60">
              {t('admin.console.imageModels.profile.activeProvider')}
            </span>
            <select
              className="app-field-input"
              onChange={(event) =>
                setProfileDraft({
                  ...profileDraft,
                  active_provider_id: event.target.value || null,
                })
              }
              value={profileDraft.active_provider_id ?? ''}
            >
              <option value="">
                {t('admin.console.imageModels.profile.selectProvider')}
              </option>
              {data.providers.map((provider) => (
                <option key={provider.provider_id} value={provider.provider_id}>
                  {provider.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1">
            <span className="app-text-caption text-app-ink/60">
              {t('admin.console.imageModels.profile.maxIterations')}
            </span>
            <input
              className={fieldClassName}
              max={20}
              min={1}
              onChange={(event) =>
                setProfileDraft({
                  ...profileDraft,
                  max_iterations: Number(event.target.value),
                })
              }
              type="number"
              value={profileDraft.max_iterations}
            />
          </label>
          <div className="flex flex-wrap gap-4 md:col-span-2">
            <label className="app-text-body-sm flex items-center gap-2 text-app-ink">
              <input
                checked={profileDraft.brief_web_search_enabled}
                onChange={(event) =>
                  setProfileDraft({
                    ...profileDraft,
                    brief_web_search_enabled: event.target.checked,
                  })
                }
                type="checkbox"
              />
              {t('admin.console.imageModels.profile.briefWebSearch')}
            </label>
            <label className="app-text-body-sm flex items-center gap-2 text-app-ink">
              <input
                checked={profileDraft.generation_web_search_enabled}
                onChange={(event) =>
                  setProfileDraft({
                    ...profileDraft,
                    generation_web_search_enabled: event.target.checked,
                  })
                }
                type="checkbox"
              />
              {t('admin.console.imageModels.profile.generationWebSearch')}
            </label>
          </div>
          <div className="md:col-span-2 flex justify-end">
            <Button disabled={saving} type="submit" variant="primary">
              <Save size={15} />
              {t('common:actions.save')}
            </Button>
          </div>
        </form>
      </SurfaceCard>

      <SurfaceCard
        description={t('admin.console.imageModels.provider.description')}
        title={t('admin.console.imageModels.provider.title')}
      >
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {data.providers.map((provider) => (
              <button
                className={`rounded-md border px-3 py-2 text-left ${
                  selectedProviderId === provider.provider_id
                    ? 'border-app-accent bg-app-accent/5'
                    : 'border-app-border bg-app-surface'
                }`}
                key={provider.provider_id}
                onClick={() => setSelectedProviderId(provider.provider_id)}
                type="button"
              >
                <span className="app-text-control text-app-ink">
                  {provider.display_name}
                </span>
                <span className="app-text-caption ml-2 text-app-ink/50">
                  {provider.provider_id}
                </span>
              </button>
            ))}
          </div>

          {selectedProvider && selectedDraft ? (
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                void saveProvider();
              }}
            >
              <div className="grid gap-3 md:grid-cols-2">
                <label className="block space-y-1">
                  <span className="app-text-caption text-app-ink/60">
                    {t('admin.console.imageModels.provider.endpoint')}
                  </span>
                  <input
                    className={fieldClassName}
                    onChange={(event) =>
                      updateProviderDraft({ endpointUrl: event.target.value })
                    }
                    type="url"
                    value={selectedDraft.endpointUrl}
                  />
                </label>
                <label className="block space-y-1">
                  <span className="app-text-caption text-app-ink/60">
                    {t('admin.console.imageModels.provider.supervisorModel')}
                  </span>
                  <input
                    className={fieldClassName}
                    onChange={(event) =>
                      updateProviderDraft({
                        supervisorModelId: event.target.value,
                      })
                    }
                    value={selectedDraft.supervisorModelId}
                  />
                </label>
                <label className="block space-y-1">
                  <span className="app-text-caption text-app-ink/60">
                    {t('admin.console.imageModels.provider.generationModel')}
                  </span>
                  <input
                    className={fieldClassName}
                    onChange={(event) =>
                      updateProviderDraft({
                        generationModelId: event.target.value,
                      })
                    }
                    value={selectedDraft.generationModelId}
                  />
                </label>
                {selectedProvider.credential_kind === 'api_key' ? (
                  <label className="block space-y-1">
                    <span className="app-text-caption text-app-ink/60">
                      {t('admin.console.imageModels.provider.apiKey')}
                    </span>
                    <div className="flex items-center gap-2">
                      <input
                        autoComplete="new-password"
                        className={fieldClassName}
                        disabled={selectedDraft.clearApiKey}
                        onChange={(event) =>
                          updateProviderDraft({ apiKey: event.target.value })
                        }
                        placeholder={t(
                          selectedProvider.has_api_key
                            ? 'admin.console.imageModels.provider.apiKeyStored'
                            : 'admin.console.imageModels.provider.apiKeyMissing',
                        )}
                        type="password"
                        value={selectedDraft.apiKey}
                      />
                      <KeyRound
                        className="shrink-0 text-app-ink/45"
                        size={15}
                      />
                    </div>
                  </label>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-app-border pt-3">
                <div className="flex flex-wrap gap-4">
                  <label className="app-text-body-sm flex items-center gap-2 text-app-ink">
                    <input
                      checked={selectedDraft.enabled}
                      onChange={(event) =>
                        updateProviderDraft({ enabled: event.target.checked })
                      }
                      type="checkbox"
                    />
                    {t('admin.console.imageModels.provider.enabled')}
                  </label>
                  {selectedProvider.has_api_key ? (
                    <label className="app-text-caption flex items-center gap-2 text-app-danger-text">
                      <input
                        checked={selectedDraft.clearApiKey}
                        onChange={(event) =>
                          updateProviderDraft({
                            apiKey: '',
                            clearApiKey: event.target.checked,
                          })
                        }
                        type="checkbox"
                      />
                      {t('admin.console.imageModels.provider.clearApiKey')}
                    </label>
                  ) : null}
                </div>
                <Button disabled={saving} type="submit" variant="primary">
                  <Save size={15} />
                  {t('common:actions.save')}
                </Button>
              </div>
            </form>
          ) : null}
        </div>
      </SurfaceCard>
    </div>
  );
}
