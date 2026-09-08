import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { useAppBootstrapContext } from '@/src/platform/apps/app-bootstrap-context';
import { DirectoryPicker } from '@/src/platform/directory/DirectoryPicker';
import { Button, useFeedback } from '@open-work-hub/ui';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  listCompanyAppControls,
  type CompanyAppControlItem,
} from './admin-api';
import { FORM_FIELD_CLASS } from './admin-shared';

type Policy = ApiSchema<'AppAccessPolicyResponse'>;

function AppControlsContent({ token }: { token: string }) {
  const { t } = useTranslation('shell');
  const feedback = useFeedback();
  const { reload } = useAppBootstrapContext();
  const [apps, setApps] = useState<CompanyAppControlItem[]>([]);
  const [appId, setAppId] = useState('');
  const [loadedPolicy, setPolicy] = useState<Policy | null>(null);
  const policy = loadedPolicy?.app_id === appId ? loadedPolicy : null;
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    listCompanyAppControls(token)
      .then((response) => {
        if (cancelled) return;
        setApps(response.items);
        if (response.items.length === 0) setLoading(false);
        setAppId((current) => current || response.items[0]?.app_id || '');
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setLoading(false);
          setError(
            caught instanceof Error
              ? caught.message
              : t('companyAccess.loadFailed'),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token, retry, t]);
  useEffect(() => {
    const controller = new AbortController();
    setPolicy(null);
    setError(null);
    setLoading(true);
    if (!appId) return () => controller.abort();
    apiFetchJson<Policy>(
      `/api/v1/admin/apps/${encodeURIComponent(appId)}/access-policy`,
      token,
      { signal: controller.signal },
    )
      .then((next) => {
        if (!controller.signal.aborted) setPolicy(next);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error
              ? caught.message
              : t('companyAccess.loadFailed'),
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [appId, token, retry, t]);
  const save = async () => {
    if (!policy) return;
    setSaving(true);
    try {
      const payload: ApiSchema<'AppAccessPolicyRequest'> = {
        enabled: policy.enabled,
        audience: policy.audience,
        user_ids: policy.audience === 'selected' ? policy.user_ids : [],
        group_ids: policy.audience === 'selected' ? policy.group_ids : [],
      };
      await apiFetchJson<Policy>(
        `/api/v1/admin/apps/${encodeURIComponent(appId)}/access-policy`,
        token,
        { method: 'PUT', body: JSON.stringify(payload) },
      );
      reload();
      feedback.success(t('companyAccess.saved'));
    } catch (caught) {
      feedback.error(
        caught instanceof Error
          ? caught.message
          : t('companyAccess.saveFailed'),
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="max-w-3xl space-y-5">
      <label className="block space-y-1">
        <span>{t('companyAccess.app')}</span>
        <select
          aria-label={t('companyAccess.app')}
          className={FORM_FIELD_CLASS}
          disabled={saving}
          value={appId}
          onChange={(event) => setAppId(event.target.value)}
        >
          {apps.map((app) => (
            <option key={app.app_id} value={app.app_id}>
              {t(`apps.${app.app_id}`, { defaultValue: app.title })}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <div role="alert">
          {error}
          <Button onClick={() => setRetry((value) => value + 1)}>
            {t('directory.retry')}
          </Button>
        </div>
      ) : null}
      {loading ? <p role="status">{t('directory.loading')}</p> : null}
      {policy && !loading ? (
        <fieldset disabled={saving} className="space-y-5">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={policy.enabled}
              onChange={(event) =>
                setPolicy({ ...policy, enabled: event.target.checked })
              }
            />
            {t('companyAccess.enabled')}
          </label>
          <label className="block space-y-1">
            <span>{t('companyAccess.audience')}</span>
            <select
              aria-label={t('companyAccess.audience')}
              className={FORM_FIELD_CLASS}
              value={policy.audience}
              onChange={(event) =>
                setPolicy({
                  ...policy,
                  audience: event.target.value as Policy['audience'],
                })
              }
            >
              <option value="all">{t('companyAccess.all')}</option>
              <option value="selected">{t('companyAccess.selected')}</option>
            </select>
          </label>
          {policy.audience === 'selected' ? (
            <>
              <div>
                <p>{t('companyAccess.users')}</p>
                <DirectoryPicker
                  key={`${appId}:people`}
                  token={token}
                  kind="people"
                  selectedIds={policy.user_ids ?? []}
                  onChange={(user_ids) => setPolicy({ ...policy, user_ids })}
                />
              </div>
              <div>
                <p>{t('companyAccess.groups')}</p>
                <DirectoryPicker
                  key={`${appId}:groups`}
                  token={token}
                  kind="groups"
                  selectedIds={policy.group_ids ?? []}
                  onChange={(group_ids) => setPolicy({ ...policy, group_ids })}
                />
              </div>
              <p className="app-text-caption text-app-ink/60">
                {t('companyAccess.selectedRule')}
              </p>
            </>
          ) : null}
          <p className="app-text-caption text-app-ink/60">
            {t('companyAccess.resourceRule')}
          </p>
          <Button onClick={() => void save()} disabled={saving}>
            {t('companyAccess.save')}
          </Button>
        </fieldset>
      ) : null}
    </div>
  );
}

export function AppControlsSection({ token }: { token: string }) {
  return <AppControlsContent key={token} token={token} />;
}
