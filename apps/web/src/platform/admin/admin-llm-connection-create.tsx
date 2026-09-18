import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, useFeedback } from '@open-work-hub/ui';
import {
  createAdminAiModelConnection,
  type AdminAiModelSettings,
  type AiModelRoute,
} from './admin-ai-model-settings-api';
import { FORM_FIELD_CLASS, SurfaceCard } from './admin-shared';

export function AdminLlmConnectionCreate({
  token,
  data,
  onSaved,
}: {
  token: string;
  data: AdminAiModelSettings;
  onSaved: (data: AdminAiModelSettings) => void;
}) {
  const { t } = useTranslation('apps');
  const toast = useFeedback();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState('openrouter');
  const [name, setName] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [key, setKey] = useState('');
  const [route, setRoute] = useState<AiModelRoute>('external');
  const [auth, setAuth] = useState<'api_key' | 'none'>('api_key');
  const [preset, setPreset] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <SurfaceCard title={t('admin.console.aiSecurity.llmConnections.title')}>
      <Button
        variant="secondary"
        onClick={() => {
          setOpen(!open);
          setKey('');
        }}
      >
        {t('admin.console.aiSecurity.llmConnections.add')}
      </Button>
      {open ? (
        <form
          className="mt-3 grid gap-3 md:grid-cols-2"
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            try {
              const result = await createAdminAiModelConnection(token, {
                expected_registry_digest: data.registry_digest,
                expected_version: 0,
                enabled: false,
                provider_kind: kind,
                display_name: name,
                endpoint_url: endpoint || null,
                default_model_id: null,
                route_mode: kind === 'openai_compatible' ? route : 'external',
                credential_kind:
                  kind === 'openai_compatible' ? auth : 'api_key',
                preset: kind === 'openai_compatible' ? preset : '',
                ...(key ? { api_key: key } : {}),
              });
              setKey('');
              setOpen(false);
              setName('');
              onSaved(result);
              toast.success(t('admin.console.aiSecurity.modelSettings.saved'));
            } catch (error) {
              toast.error(
                error instanceof Error
                  ? error.message
                  : t('admin.console.aiSecurity.modelSettings.saveFailed'),
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="block space-y-1">
            <span>{t('admin.console.aiSecurity.llmConnections.name')}</span>
            <input
              className={FORM_FIELD_CLASS}
              required
              maxLength={160}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block space-y-1">
            <span>{t('admin.console.aiSecurity.llmConnections.kind')}</span>
            <select
              className="app-field-input"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setEndpoint('');
                setPreset('');
              }}
            >
              {data.provider_kinds
                .filter((id) => id !== 'local')
                .map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
            </select>
          </label>
          {kind === 'openai_compatible' ? (
            <>
              <label className="block space-y-1">
                <span>
                  {t('admin.console.aiSecurity.llmConnections.preset')}
                </span>
                <select
                  className="app-field-input"
                  value={preset}
                  onChange={(e) => {
                    setPreset(e.target.value);
                    setRoute('local');
                    setAuth('none');
                    setEndpoint(
                      e.target.value === 'ollama'
                        ? 'http://127.0.0.1:11434/v1'
                        : e.target.value === 'vllm'
                          ? 'http://127.0.0.1:8000/v1'
                          : '',
                    );
                  }}
                >
                  <option value="">
                    {t('admin.console.aiSecurity.llmConnections.custom')}
                  </option>
                  <option value="vllm">vLLM</option>
                  <option value="ollama">
                    {t('admin.console.aiSecurity.llmConnections.ollama')}
                  </option>
                </select>
              </label>
              <label className="block space-y-1">
                <span>
                  {t('admin.console.aiSecurity.llmConnections.route')}
                </span>
                <select
                  className="app-field-input"
                  value={route}
                  onChange={(e) => setRoute(e.target.value as AiModelRoute)}
                >
                  {(['local', 'external'] as const).map((id) => (
                    <option key={id} value={id}>
                      {t(`admin.console.aiSecurity.modelSettings.routes.${id}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1">
                <span>{t('admin.console.aiSecurity.llmConnections.auth')}</span>
                <select
                  className="app-field-input"
                  value={auth}
                  onChange={(e) =>
                    setAuth(e.target.value as 'api_key' | 'none')
                  }
                >
                  <option value="api_key">
                    {t(
                      'admin.console.aiSecurity.modelSettings.providers.apiKey',
                    )}
                  </option>
                  <option value="none">
                    {t('admin.console.aiSecurity.llmConnections.noAuth')}
                  </option>
                </select>
              </label>
            </>
          ) : null}
          <label className="block space-y-1">
            <span>
              {t('admin.console.aiSecurity.modelSettings.providers.endpoint')}
            </span>
            <input
              type="url"
              className={FORM_FIELD_CLASS}
              required={kind === 'openai_compatible'}
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
            />
          </label>
          {kind !== 'openai_compatible' || auth === 'api_key' ? (
            <label className="block space-y-1">
              <span>
                {t('admin.console.aiSecurity.modelSettings.providers.apiKey')}
              </span>
              <input
                className={FORM_FIELD_CLASS}
                type="password"
                autoComplete="new-password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
              />
            </label>
          ) : null}
          <p className="app-text-caption text-app-ink/60 md:col-span-2">
            {t('admin.console.aiSecurity.llmConnections.setup')}
          </p>
          <Button type="submit" disabled={busy} variant="primary">
            {t('common:actions.save')}
          </Button>
        </form>
      ) : null}
    </SurfaceCard>
  );
}
