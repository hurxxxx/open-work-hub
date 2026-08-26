import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Copy, Eye, KeyRound, Plus, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  Button,
  ContentState,
  ContextNote,
  Dialog,
  FormMessage,
  StatusSlot,
  useConfirm,
  useFeedback,
} from '@open-work-hub/ui';

import {
  createPlatformApiKey,
  listPlatformApiKeys,
  revealPlatformApiKey,
  revokePlatformApiKey,
  type PlatformApiKeyItem,
  type PlatformApiKeyListResponse,
  type PlatformApiKeySecretResponse,
} from './admin-api';
import {
  BodyCell,
  FORM_FIELD_CLASS as fieldClassName,
  HeadCell,
  getErrorMessage,
} from './admin-shared';

import { UserDateTime } from '@/src/components/date/UserDateTime';

export function AdminPlatformApiKeysSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const feedback = useFeedback();
  const { confirm, confirmDialog } = useConfirm();
  const [response, setResponse] = useState<PlatformApiKeyListResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [issueOpen, setIssueOpen] = useState(false);
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<string[]>([]);
  const [issuing, setIssuing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [secret, setSecret] = useState<PlatformApiKeySecretResponse | null>(
    null,
  );
  const [revealingId, setRevealingId] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setResponse(await listPlatformApiKeys(token));
    } catch (error) {
      setLoadError(
        getErrorMessage(error, t('admin.console.apiKeys.loadFailed')),
      );
    } finally {
      setLoading(false);
    }
  }, [t, token]);

  useEffect(() => {
    void load();
  }, [load]);

  function openIssueDialog() {
    setName('');
    setScopes([]);
    setFormError(null);
    setIssueOpen(true);
  }

  function closeSecretDialog() {
    setSecret(null);
  }

  function toggleScope(scope: string) {
    setScopes((current) =>
      current.includes(scope)
        ? current.filter((candidate) => candidate !== scope)
        : [...current, scope],
    );
  }

  async function issueKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIssuing(true);
    setFormError(null);
    try {
      const issued = await createPlatformApiKey(token, {
        name: name.trim(),
        scopes,
      });
      setIssueOpen(false);
      setSecret(issued);
      feedback.success(t('admin.console.apiKeys.issued'));
      await load();
    } catch (error) {
      setFormError(
        getErrorMessage(error, t('admin.console.apiKeys.issueFailed')),
      );
    } finally {
      setIssuing(false);
    }
  }

  async function revealKey(item: PlatformApiKeyItem) {
    setRevealingId(item.id);
    try {
      setSecret(await revealPlatformApiKey(token, item.id));
    } catch (error) {
      feedback.error(
        t('admin.console.apiKeys.revealFailed'),
        getErrorMessage(error, t('admin.console.apiKeys.revealFailed')),
      );
    } finally {
      setRevealingId(null);
    }
  }

  async function revokeKey(item: PlatformApiKeyItem) {
    const approved = await confirm({
      title: t('admin.console.apiKeys.revokeTitle'),
      description: t('admin.console.apiKeys.revokeDescription', {
        name: item.name,
      }),
      confirmLabel: t('admin.console.apiKeys.revoke'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!approved) return;

    setRevokingId(item.id);
    try {
      await revokePlatformApiKey(token, item.id);
      feedback.success(t('admin.console.apiKeys.revoked'));
      await load();
    } catch (error) {
      feedback.error(
        t('admin.console.apiKeys.revokeFailed'),
        getErrorMessage(error, t('admin.console.apiKeys.revokeFailed')),
      );
    } finally {
      setRevokingId(null);
    }
  }

  async function copySecret() {
    if (!secret) return;
    try {
      await navigator.clipboard.writeText(secret.api_key);
      feedback.success(t('admin.console.apiKeys.copied'));
    } catch {
      feedback.error(t('admin.console.apiKeys.copyFailed'));
    }
  }

  const items = response?.items ?? [];

  return (
    <div className="space-y-5">
      <ContextNote
        title={t('admin.console.apiKeys.boundaryTitle')}
        tone="warning"
      >
        {t('admin.console.apiKeys.boundaryDescription')}
      </ContextNote>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-app-border pb-4">
        <div className="flex flex-wrap items-center gap-3 app-text-body text-app-ink/55">
          <span>
            {t('admin.console.apiKeys.count', { count: items.length })}
          </span>
          {response ? (
            <>
              <a
                className="text-app-accent hover:underline"
                href={response.documentation.swagger_path}
                rel="noreferrer"
                target="_blank"
              >
                {t('admin.console.apiKeys.swagger')}
              </a>
              <a
                className="text-app-accent hover:underline"
                href={response.documentation.redoc_path}
                rel="noreferrer"
                target="_blank"
              >
                {t('admin.console.apiKeys.redoc')}
              </a>
              <a
                className="text-app-accent hover:underline"
                href={response.documentation.openapi_path}
                rel="noreferrer"
                target="_blank"
              >
                {t('admin.console.apiKeys.openapi')}
              </a>
            </>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button
            disabled={loading}
            onClick={() => void load()}
            variant="ghost"
          >
            <RefreshCw aria-hidden="true" size={14} />
            {t('common:actions.refresh')}
          </Button>
          <Button onClick={openIssueDialog} variant="primary">
            <Plus aria-hidden="true" size={14} />
            {t('admin.console.apiKeys.issue')}
          </Button>
        </div>
      </div>

      {response?.scope_specs.length ? (
        <section className="grid gap-2">
          <h2 className="app-text-title-md text-app-ink">
            {t('admin.console.apiKeys.scopeTitle')}
          </h2>
          <div className="grid gap-2 lg:grid-cols-2">
            {response.scope_specs.map((spec) => (
              <div
                className="rounded-lg border border-app-border bg-app-surface-sidebar p-3"
                key={spec.scope}
              >
                <code className="app-text-control font-semibold text-app-ink">
                  {spec.scope}
                </code>
                <ul className="mt-2 grid gap-1">
                  {spec.operations.map((operation) => (
                    <li
                      className="app-text-caption flex min-w-0 gap-2 text-app-ink/55"
                      key={operation.operation_id}
                    >
                      <span className="font-semibold text-app-ink">
                        {operation.method}
                      </span>
                      <code className="truncate">{operation.path}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {loading ? (
        <ContentState
          kind="loading"
          title={t('admin.console.apiKeys.loadingTitle')}
          description={t('admin.console.apiKeys.loadingDescription')}
        />
      ) : loadError ? (
        <ContentState
          action={{
            label: t('common:actions.retry'),
            onClick: () => void load(),
          }}
          kind="error"
          title={t('admin.console.apiKeys.loadFailed')}
          description={loadError}
        />
      ) : items.length === 0 ? (
        <ContentState
          action={{
            label: t('admin.console.apiKeys.issue'),
            onClick: openIssueDialog,
          }}
          kind="empty"
          title={t('admin.console.apiKeys.emptyTitle')}
          description={t('admin.console.apiKeys.emptyDescription')}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-app-border">
          <table className="w-full border-collapse">
            <thead className="bg-app-surface-sidebar">
              <tr>
                <HeadCell>{t('admin.console.apiKeys.columns.name')}</HeadCell>
                <HeadCell>{t('admin.console.apiKeys.columns.prefix')}</HeadCell>
                <HeadCell>{t('admin.console.apiKeys.columns.scopes')}</HeadCell>
                <HeadCell>{t('admin.console.apiKeys.columns.status')}</HeadCell>
                <HeadCell>
                  {t('admin.console.apiKeys.columns.created')}
                </HeadCell>
                <HeadCell>
                  {t('admin.console.apiKeys.columns.lastUsed')}
                </HeadCell>
                <HeadCell className="text-right">
                  {t('admin.console.apiKeys.columns.actions')}
                </HeadCell>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const isActive = item.status === 'active';
                return (
                  <tr className="border-t border-app-border" key={item.id}>
                    <BodyCell>
                      <div className="font-medium text-app-ink">
                        {item.name}
                      </div>
                      <div className="app-text-caption text-app-ink/55">
                        {t('admin.console.apiKeys.createdBy', {
                          name: item.created_by_name,
                        })}
                      </div>
                    </BodyCell>
                    <BodyCell className="font-mono text-app-ink/55">
                      {item.key_prefix}…
                    </BodyCell>
                    <BodyCell>
                      <div className="flex flex-wrap gap-1">
                        {item.scopes.map((scope) => (
                          <code
                            className="app-text-caption rounded border border-app-border px-1.5 py-0.5 text-app-ink/65"
                            key={scope}
                          >
                            {scope}
                          </code>
                        ))}
                      </div>
                    </BodyCell>
                    <BodyCell>
                      <span className="app-text-caption rounded border border-app-border px-1.5 py-0.5 text-app-ink/65">
                        {isActive
                          ? t('admin.console.apiKeys.active')
                          : t('admin.console.apiKeys.revokedStatus')}
                      </span>
                    </BodyCell>
                    <BodyCell className="whitespace-nowrap text-app-ink/55">
                      <UserDateTime
                        display="datetime"
                        value={item.created_at}
                      />
                    </BodyCell>
                    <BodyCell className="whitespace-nowrap text-app-ink/55">
                      {item.last_used_at ? (
                        <UserDateTime
                          display="datetime"
                          value={item.last_used_at}
                        />
                      ) : (
                        t('admin.console.apiKeys.neverUsed')
                      )}
                    </BodyCell>
                    <BodyCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          disabled={!isActive || revealingId === item.id}
                          onClick={() => void revealKey(item)}
                          variant="secondary"
                        >
                          <Eye aria-hidden="true" size={14} />
                          {t('admin.console.apiKeys.reveal')}
                        </Button>
                        <Button
                          disabled={!isActive || revokingId === item.id}
                          onClick={() => void revokeKey(item)}
                          variant="ghost"
                        >
                          {t('admin.console.apiKeys.revoke')}
                        </Button>
                      </div>
                    </BodyCell>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Dialog
        actions={
          <>
            <Button
              disabled={issuing}
              onClick={() => setIssueOpen(false)}
              variant="secondary"
            >
              {t('common:actions.cancel')}
            </Button>
            <Button
              disabled={issuing || scopes.length === 0}
              form="platform-api-key-form"
              type="submit"
              variant="primary"
            >
              {issuing
                ? t('admin.console.apiKeys.issuing')
                : t('admin.console.apiKeys.issue')}
            </Button>
          </>
        }
        closeLabel={t('common:actions.close')}
        description={t('admin.console.apiKeys.issueDescription')}
        dismissOnInteractOutside={false}
        onOpenChange={(open) => !issuing && setIssueOpen(open)}
        open={issueOpen}
        title={t('admin.console.apiKeys.issueTitle')}
      >
        <form
          className="grid gap-4"
          id="platform-api-key-form"
          onSubmit={(event) => void issueKey(event)}
        >
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.apiKeys.name')}
            </span>
            <input
              className={fieldClassName}
              maxLength={120}
              onChange={(event) => setName(event.target.value)}
              required
              value={name}
            />
          </label>
          <fieldset className="grid gap-2">
            <legend className="app-text-caption mb-1 text-app-ink/55">
              {t('admin.console.apiKeys.scopes')}
            </legend>
            {(response?.available_scopes ?? []).map((scope) => (
              <label
                className="app-text-control flex items-center gap-2 rounded-md border border-app-border px-3 py-2"
                key={scope}
              >
                <input
                  checked={scopes.includes(scope)}
                  onChange={() => toggleScope(scope)}
                  type="checkbox"
                />
                <code>{scope}</code>
              </label>
            ))}
          </fieldset>
          <FormMessage
            id="platform-api-key-form-error"
            message={formError}
            variant="form"
          />
        </form>
      </Dialog>

      <Dialog
        actions={
          <>
            <Button onClick={() => void copySecret()} variant="primary">
              <Copy aria-hidden="true" size={14} />
              {t('admin.console.apiKeys.copy')}
            </Button>
            <Button onClick={closeSecretDialog} variant="secondary">
              {t('common:actions.close')}
            </Button>
          </>
        }
        closeLabel={t('common:actions.close')}
        description={secret?.item.name}
        dismissOnInteractOutside={false}
        onOpenChange={(open) => !open && closeSecretDialog()}
        open={secret !== null}
        title={t('admin.console.apiKeys.secretTitle')}
      >
        <div className="grid gap-3">
          <StatusSlot
            message={t('admin.console.apiKeys.secretWarning')}
            size="regular"
            tone="warning"
          />
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.apiKeys.secretLabel')}
            </span>
            <textarea
              className="app-field-input min-h-24 resize-none font-mono"
              readOnly
              value={secret?.api_key ?? ''}
            />
          </label>
          <div className="app-text-caption flex items-center gap-2 text-app-ink/55">
            <KeyRound aria-hidden="true" size={14} />
            {t('admin.console.apiKeys.authorizationHint')}
          </div>
        </div>
      </Dialog>

      {confirmDialog}
    </div>
  );
}
