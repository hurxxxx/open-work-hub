import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@open-work-hub/ui';
import {
  updateAdminAiModelDefault,
  type AdminAiModelSettings,
  type AiModelRoute,
} from './admin-ai-model-settings-api';
import { SurfaceCard, FORM_FIELD_CLASS } from './admin-shared';

export function AdminLlmDefaults({
  token,
  data,
  disabled,
  onSave,
}: {
  token: string;
  data: AdminAiModelSettings;
  disabled: boolean;
  onSave: (
    key: string,
    mutation: () => Promise<AdminAiModelSettings>,
  ) => Promise<void>;
}) {
  const { t } = useTranslation('apps');
  const [appId, setAppId] = useState('');
  const apps = [
    ...new Set(data.workloads.map((workload) => workload.app_id)),
  ].sort();
  return (
    <SurfaceCard
      title={t('admin.console.aiSecurity.llmDefaults.title')}
      description={t('admin.console.aiSecurity.llmDefaults.description')}
    >
      <label className="block space-y-1">
        <span className="app-text-caption text-app-ink/60">
          {t('admin.console.aiSecurity.llmDefaults.scope')}
        </span>
        <select
          className="app-field-input"
          value={appId}
          disabled={disabled}
          onChange={(event) => setAppId(event.target.value)}
        >
          <option value="">
            {t('admin.console.aiSecurity.llmDefaults.global')}
          </option>
          {apps.map((id) => (
            <option key={id} value={id}>
              {t(`shell:apps.${id}`, { defaultValue: id })}
            </option>
          ))}
        </select>
      </label>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {(['local', 'external'] as const).map((route) => (
          <DefaultEditor
            key={`${appId}:${route}:${data.defaults.find((row) => row.app_id === appId && row.route_mode === route)?.version ?? 0}:${data.providers
              .filter((row) => row.route_mode === route)
              .map((row) => `${row.provider_id}:${row.version}`)
              .join(',')}:${data.registry_digest}`}
            {...{ token, data, disabled, onSave, appId, route }}
          />
        ))}
      </div>
    </SurfaceCard>
  );
}

function DefaultEditor({
  token,
  data,
  disabled,
  onSave,
  appId,
  route,
}: {
  token: string;
  data: AdminAiModelSettings;
  disabled: boolean;
  onSave: (
    key: string,
    mutation: () => Promise<AdminAiModelSettings>,
  ) => Promise<void>;
  appId: string;
  route: AiModelRoute;
}) {
  const { t } = useTranslation('apps');
  const saved = data.defaults.find(
    (row) => row.app_id === appId && row.route_mode === route,
  );
  const [connectionId, setConnectionId] = useState(saved?.provider_id ?? '');
  const connection = data.providers.find(
    (row) => row.provider_id === connectionId,
  );
  const [modelId, setModelId] = useState(
    saved?.model_id ?? (!appId ? connection?.default_model_id : '') ?? '',
  );
  const [cap, setCap] = useState(
    saved?.max_output_tokens ? String(saved.max_output_tokens / 1024) : '',
  );
  const models = data.models.filter(
    (row) =>
      row.provider_id === connectionId &&
      row.enabled &&
      row.discovery_status === 'active',
  );
  return (
    <form
      aria-label={t(`admin.console.aiSecurity.modelSettings.routes.${route}`)}
      className="space-y-2 rounded-md border border-app-border p-3"
      onSubmit={async (event) => {
        event.preventDefault();
        if (disabled) return;
        await onSave(`default:${appId}:${route}`, () =>
          updateAdminAiModelDefault(token, appId, route, {
            expected_registry_digest: data.registry_digest,
            expected_version: saved?.version ?? 0,
            expected_provider_version: connection?.version,
            provider_id: connectionId || null,
            model_id: modelId || null,
            max_output_tokens: cap ? Number(cap) * 1024 : null,
          }),
        );
      }}
    >
      <h3 className="app-text-control text-app-ink">
        {t(`admin.console.aiSecurity.modelSettings.routes.${route}`)}
      </h3>
      <label className="block space-y-1">
        <span className="app-text-caption text-app-ink/60">
          {t('admin.console.aiSecurity.llmDefaults.connection')}
        </span>
        <select
          className="app-field-input"
          value={connectionId}
          disabled={disabled}
          onChange={(event) => {
            setConnectionId(event.target.value);
            setModelId('');
          }}
        >
          <option value="">
            {t(
              appId
                ? 'admin.console.aiSecurity.llmDefaults.inherit'
                : 'admin.console.aiSecurity.llmDefaults.unconfigured',
            )}
          </option>
          {data.providers
            .filter((row) => row.route_mode === route && row.enabled)
            .map((row) => (
              <option key={row.provider_id} value={row.provider_id}>
                {row.display_name}
              </option>
            ))}
        </select>
      </label>
      <label className="block space-y-1">
        <span className="app-text-caption text-app-ink/60">
          {t('admin.console.aiSecurity.modelSettings.providers.defaultModel')}
        </span>
        <select
          className="app-field-input"
          disabled={disabled || !connectionId}
          value={modelId}
          onChange={(event) => setModelId(event.target.value)}
        >
          <option value="">
            {t('admin.console.aiSecurity.llmDefaults.inherit')} ·{' '}
            {data.models.find((row) => row.id === connection?.default_model_id)
              ?.model_key ?? '—'}
          </option>
          {models.map((row) => (
            <option key={row.id} value={row.id}>
              {row.display_name} · {row.model_key}
            </option>
          ))}
        </select>
      </label>
      <label className="block space-y-1">
        <span className="app-text-caption text-app-ink/60">
          {t('admin.console.aiSecurity.llmDefaults.cap')}
        </span>
        <input
          className={FORM_FIELD_CLASS}
          type="number"
          min={1}
          max={64}
          step={1}
          value={cap}
          disabled={disabled}
          placeholder={t('admin.console.aiSecurity.llmDefaults.inherit')}
          onChange={(event) => setCap(event.target.value)}
        />
      </label>
      <Button type="submit" disabled={disabled} variant="primary">
        {t('common:actions.save')}
      </Button>
    </form>
  );
}
