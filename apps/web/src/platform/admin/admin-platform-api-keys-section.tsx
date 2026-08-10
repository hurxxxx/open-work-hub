import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import { Copy, Eye, KeyRound, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  Badge,
  Button,
  DataTable,
  Dialog,
  InlineNotice,
  Input,
  type DataTableColumn,
} from '@open-alm/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';

import {
  createAdminPlatformApiKey,
  listAdminPlatformApiKeys,
  revealAdminPlatformApiKey,
  revokeAdminPlatformApiKey,
  type AdminPlatformApiKeyItem,
  type AdminPlatformApiKeysResponse,
} from './admin-platform-api-keys-api';
import { getErrorMessage } from './admin-shared';

type SecretDialogKind = 'create' | 'reveal';

function SecretField({
  copied,
  onCopy,
  secret,
}: {
  copied: boolean;
  onCopy: () => void;
  secret: string;
}) {
  const { t } = useTranslation('apps');

  return (
    <div className="space-y-2">
      <label
        className="app-text-label block text-app-ink"
        htmlFor="platform-api-key-secret"
      >
        {t('admin.console.apiKeys.secret.label')}
      </label>
      <div className="flex min-w-0 gap-2">
        <Input
          autoComplete="off"
          className="min-w-0 font-mono"
          id="platform-api-key-secret"
          readOnly
          value={secret}
        />
        <Button
          aria-label={
            copied
              ? t('admin.console.apiKeys.secret.copied')
              : t('admin.console.apiKeys.secret.copy')
          }
          onClick={onCopy}
          variant="secondary"
        >
          <Copy aria-hidden="true" size={14} />
          {copied
            ? t('admin.console.apiKeys.secret.copied')
            : t('admin.console.apiKeys.secret.copy')}
        </Button>
      </div>
    </div>
  );
}

export function AdminPlatformApiKeysSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const [response, setResponse] = useState<AdminPlatformApiKeysResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [selectedScopes, setSelectedScopes] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const [revealTarget, setRevealTarget] =
    useState<AdminPlatformApiKeyItem | null>(null);
  const [revealing, setRevealing] = useState(false);
  const [revealedSecret, setRevealedSecret] = useState<string | null>(null);
  const [revealError, setRevealError] = useState<string | null>(null);

  const [revokeTarget, setRevokeTarget] =
    useState<AdminPlatformApiKeyItem | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  const [copiedKind, setCopiedKind] = useState<SecretDialogKind | null>(null);
  const createRequestId = useRef(0);
  const revealRequestId = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setResponse(await listAdminPlatformApiKeys(token));
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

  useEffect(
    () => () => {
      createRequestId.current += 1;
      revealRequestId.current += 1;
    },
    [],
  );

  const clearCreateDialog = useCallback(() => {
    createRequestId.current += 1;
    setCreateOpen(false);
    setName('');
    setSelectedScopes([]);
    setCreating(false);
    setCreatedSecret(null);
    setCreateError(null);
    setCopiedKind(null);
  }, []);

  const openCreateDialog = useCallback(() => {
    createRequestId.current += 1;
    setName('');
    setSelectedScopes(
      response?.available_scopes.includes('hr:read') ? ['hr:read'] : [],
    );
    setCreating(false);
    setCreatedSecret(null);
    setCreateError(null);
    setCopiedKind(null);
    setCreateOpen(true);
  }, [response]);

  const clearRevealDialog = useCallback(() => {
    revealRequestId.current += 1;
    setRevealTarget(null);
    setRevealing(false);
    setRevealedSecret(null);
    setRevealError(null);
    setCopiedKind(null);
  }, []);

  const openRevealDialog = useCallback(
    async (item: AdminPlatformApiKeyItem) => {
      const requestId = ++revealRequestId.current;
      setRevealTarget(item);
      setRevealing(true);
      setRevealedSecret(null);
      setRevealError(null);
      setCopiedKind(null);

      try {
        const result = await revealAdminPlatformApiKey(token, item.id);
        if (revealRequestId.current !== requestId) {
          return;
        }
        setRevealedSecret(result.api_key);
      } catch (error) {
        if (revealRequestId.current !== requestId) {
          return;
        }
        setRevealError(
          getErrorMessage(error, t('admin.console.apiKeys.reveal.failed')),
        );
      } finally {
        if (revealRequestId.current === requestId) {
          setRevealing(false);
        }
      }
    },
    [t, token],
  );

  const handleCreate = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmedName = name.trim();
      if (!trimmedName || selectedScopes.length === 0) {
        return;
      }
      const requestId = ++createRequestId.current;
      setCreating(true);
      setCreateError(null);

      try {
        const result = await createAdminPlatformApiKey(token, {
          name: trimmedName,
          scopes: selectedScopes,
        });
        if (createRequestId.current !== requestId) {
          return;
        }
        setCreatedSecret(result.api_key);
        setResponse((current) => ({
          available_scopes:
            current?.available_scopes ?? [...selectedScopes].sort(),
          items: [
            result.item,
            ...(current?.items.filter((item) => item.id !== result.item.id) ??
              []),
          ],
        }));
      } catch (error) {
        if (createRequestId.current !== requestId) {
          return;
        }
        setCreateError(
          getErrorMessage(error, t('admin.console.apiKeys.create.failed')),
        );
      } finally {
        if (createRequestId.current === requestId) {
          setCreating(false);
        }
      }
    },
    [name, selectedScopes, t, token],
  );

  const handleCopy = useCallback(
    async (kind: SecretDialogKind, secret: string) => {
      try {
        if (!navigator.clipboard) {
          throw new Error(t('admin.console.apiKeys.secret.copyFailed'));
        }
        await navigator.clipboard.writeText(secret);
        setCopiedKind(kind);
        if (kind === 'create') {
          setCreateError(null);
        } else {
          setRevealError(null);
        }
      } catch (error) {
        const message = getErrorMessage(
          error,
          t('admin.console.apiKeys.secret.copyFailed'),
        );
        if (kind === 'create') {
          setCreateError(message);
        } else {
          setRevealError(message);
        }
      }
    },
    [t],
  );

  const clearRevokeDialog = useCallback(() => {
    setRevokeTarget(null);
    setRevoking(false);
    setRevokeError(null);
  }, []);

  const handleRevoke = useCallback(async () => {
    if (!revokeTarget) {
      return;
    }
    setRevoking(true);
    setRevokeError(null);
    try {
      await revokeAdminPlatformApiKey(token, revokeTarget.id);
      clearRevokeDialog();
      await load();
    } catch (error) {
      setRevokeError(
        getErrorMessage(error, t('admin.console.apiKeys.revoke.failed')),
      );
      setRevoking(false);
    }
  }, [clearRevokeDialog, load, revokeTarget, t, token]);

  const columns = useMemo<DataTableColumn<AdminPlatformApiKeyItem>[]>(
    () => [
      {
        accessorKey: 'name',
        header: t('admin.console.apiKeys.columns.name'),
        cell: ({ row }) => (
          <span className="font-medium text-app-ink">{row.original.name}</span>
        ),
      },
      {
        accessorKey: 'key_prefix',
        header: t('admin.console.apiKeys.columns.prefix'),
        cell: ({ row }) => (
          <code className="app-text-caption whitespace-nowrap">
            {row.original.key_prefix}
          </code>
        ),
      },
      {
        id: 'scopes',
        header: t('admin.console.apiKeys.columns.scopes'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {row.original.scopes.map((scope) => (
              <Badge className="whitespace-nowrap" key={scope} tone="neutral">
                {scope}
              </Badge>
            ))}
          </div>
        ),
      },
      {
        accessorKey: 'created_by_name',
        header: t('admin.console.apiKeys.columns.issuer'),
        cell: ({ row }) => row.original.created_by_name || '-',
      },
      {
        accessorKey: 'created_at',
        header: t('admin.console.apiKeys.columns.issuedAt'),
        cell: ({ row }) => (
          <UserDateTime
            display="datetime"
            fallback="-"
            value={row.original.created_at}
          />
        ),
      },
      {
        accessorKey: 'last_used_at',
        header: t('admin.console.apiKeys.columns.lastUsedAt'),
        cell: ({ row }) =>
          row.original.last_used_at ? (
            <UserDateTime
              display="datetime"
              fallback="-"
              value={row.original.last_used_at}
            />
          ) : (
            t('admin.console.apiKeys.neverUsed')
          ),
      },
      {
        id: 'status',
        header: t('admin.console.apiKeys.columns.status'),
        cell: ({ row }) => (
          <Badge
            className="whitespace-nowrap"
            tone={row.original.revoked_at ? 'neutral' : 'success'}
          >
            {t(
              row.original.revoked_at
                ? 'admin.console.apiKeys.status.revoked'
                : 'admin.console.apiKeys.status.active',
            )}
          </Badge>
        ),
      },
      {
        id: 'actions',
        header: t('admin.console.apiKeys.columns.actions'),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.revoked_at ? (
            <span className="app-text-caption text-app-ink/45">-</span>
          ) : (
            <div className="flex flex-nowrap gap-1.5">
              <Button
                onClick={(event) => {
                  event.stopPropagation();
                  void openRevealDialog(row.original);
                }}
                size="dense"
                variant="secondary"
              >
                <Eye aria-hidden="true" size={14} />
                {t('admin.console.apiKeys.actions.reveal')}
              </Button>
              <Button
                onClick={(event) => {
                  event.stopPropagation();
                  setRevokeError(null);
                  setRevokeTarget(row.original);
                }}
                size="dense"
                variant="ghost"
              >
                <Trash2 aria-hidden="true" size={14} />
                {t('admin.console.apiKeys.actions.revoke')}
              </Button>
            </div>
          ),
      },
    ],
    [openRevealDialog, t],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 border-b border-app-border pb-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="app-text-body-sm max-w-3xl text-app-ink/55">
          {t('admin.console.apiKeys.notice')}
        </p>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            disabled={loading}
            onClick={() => void load()}
            variant="secondary"
          >
            <RefreshCw
              aria-hidden="true"
              className={loading ? 'animate-spin' : ''}
              size={14}
            />
            {t('admin.console.apiKeys.actions.refresh')}
          </Button>
          <Button onClick={openCreateDialog} variant="primary">
            <Plus aria-hidden="true" size={14} />
            {t('admin.console.apiKeys.actions.create')}
          </Button>
        </div>
      </div>

      {loadError ? (
        <InlineNotice role="alert" tone="danger">
          {loadError}
        </InlineNotice>
      ) : null}

      <DataTable
        columns={columns}
        density="dense"
        emptyState={
          <div className="space-y-1 py-5 text-center">
            <KeyRound
              aria-hidden="true"
              className="mx-auto mb-2 text-app-ink/35"
              size={22}
            />
            <div className="app-text-body font-medium text-app-ink">
              {t('admin.console.apiKeys.empty.title')}
            </div>
            <div className="app-text-body-sm text-app-ink/55">
              {t('admin.console.apiKeys.empty.description')}
            </div>
          </div>
        }
        loading={loading}
        loadingLabel={t('admin.console.apiKeys.loading')}
        rows={response?.items ?? []}
      />

      <Dialog
        actions={
          createdSecret ? (
            <Button onClick={clearCreateDialog} variant="primary">
              {t('admin.console.apiKeys.actions.close')}
            </Button>
          ) : (
            <>
              <Button
                disabled={creating}
                onClick={clearCreateDialog}
                variant="secondary"
              >
                {t('admin.console.apiKeys.actions.cancel')}
              </Button>
              <Button
                disabled={
                  creating || !name.trim() || selectedScopes.length === 0
                }
                form="create-platform-api-key-form"
                type="submit"
                variant="primary"
              >
                {creating
                  ? t('admin.console.apiKeys.create.creating')
                  : t('admin.console.apiKeys.create.submit')}
              </Button>
            </>
          )
        }
        closeLabel={t('admin.console.apiKeys.actions.close')}
        description={
          createdSecret
            ? t('admin.console.apiKeys.secret.description')
            : t('admin.console.apiKeys.create.description')
        }
        onOpenChange={(open) => {
          if (!open && !creating) {
            clearCreateDialog();
          }
        }}
        open={createOpen}
        title={
          createdSecret
            ? t('admin.console.apiKeys.secret.createdTitle')
            : t('admin.console.apiKeys.create.title')
        }
      >
        {createdSecret ? (
          <div className="space-y-4">
            <InlineNotice tone="warning">
              {t('admin.console.apiKeys.secret.createdNotice')}
            </InlineNotice>
            {createError ? (
              <InlineNotice role="alert" tone="danger">
                {createError}
              </InlineNotice>
            ) : null}
            <SecretField
              copied={copiedKind === 'create'}
              onCopy={() => void handleCopy('create', createdSecret)}
              secret={createdSecret}
            />
          </div>
        ) : (
          <form
            className="space-y-4"
            id="create-platform-api-key-form"
            onSubmit={(event) => void handleCreate(event)}
          >
            {createError ? (
              <InlineNotice role="alert" tone="danger">
                {createError}
              </InlineNotice>
            ) : null}
            <div className="space-y-2">
              <label
                className="app-text-label block text-app-ink"
                htmlFor="platform-api-key-name"
              >
                {t('admin.console.apiKeys.create.nameLabel')}
              </label>
              <Input
                autoComplete="off"
                autoFocus
                id="platform-api-key-name"
                maxLength={120}
                onChange={(event) => setName(event.target.value)}
                placeholder={t('admin.console.apiKeys.create.namePlaceholder')}
                value={name}
              />
            </div>
            <fieldset className="space-y-2">
              <legend className="app-text-label text-app-ink">
                {t('admin.console.apiKeys.create.scopesLabel')}
              </legend>
              <div className="grid gap-2">
                {response?.available_scopes.map((scope) => (
                  <label
                    className="flex items-start gap-3 rounded-lg border border-app-border px-3 py-2.5"
                    key={scope}
                  >
                    <input
                      checked={selectedScopes.includes(scope)}
                      className="mt-0.5 size-4 accent-app-accent"
                      onChange={(event) =>
                        setSelectedScopes((current) =>
                          event.target.checked
                            ? [...new Set([...current, scope])]
                            : current.filter((item) => item !== scope),
                        )
                      }
                      type="checkbox"
                    />
                    <span className="grid gap-0.5">
                      <code className="app-text-body-sm text-app-ink">
                        {scope}
                      </code>
                      <span className="app-text-caption text-app-ink/55">
                        {scope === 'hr:read'
                          ? t('admin.console.apiKeys.scopes.hrRead')
                          : scope}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </form>
        )}
      </Dialog>

      <Dialog
        actions={
          <Button onClick={clearRevealDialog} variant="primary">
            {t('admin.console.apiKeys.actions.close')}
          </Button>
        }
        closeLabel={t('admin.console.apiKeys.actions.close')}
        description={t('admin.console.apiKeys.reveal.description', {
          name: revealTarget?.name ?? '',
        })}
        onOpenChange={(open) => {
          if (!open) {
            clearRevealDialog();
          }
        }}
        open={Boolean(revealTarget)}
        title={t('admin.console.apiKeys.reveal.title')}
      >
        <div className="space-y-4">
          {revealing ? (
            <output className="app-text-body-sm text-app-ink/55">
              {t('admin.console.apiKeys.reveal.loading')}
            </output>
          ) : null}
          {revealError ? (
            <InlineNotice role="alert" tone="danger">
              {revealError}
            </InlineNotice>
          ) : null}
          {revealedSecret ? (
            <>
              <InlineNotice tone="warning">
                {t('admin.console.apiKeys.secret.sensitiveNotice')}
              </InlineNotice>
              <SecretField
                copied={copiedKind === 'reveal'}
                onCopy={() => void handleCopy('reveal', revealedSecret)}
                secret={revealedSecret}
              />
            </>
          ) : null}
        </div>
      </Dialog>

      <Dialog
        actions={
          <>
            <Button
              disabled={revoking}
              onClick={clearRevokeDialog}
              variant="secondary"
            >
              {t('admin.console.apiKeys.actions.cancel')}
            </Button>
            <Button
              className="border-app-danger bg-app-danger text-white hover:bg-app-danger/90"
              disabled={revoking}
              onClick={() => void handleRevoke()}
              variant="primary"
            >
              {revoking
                ? t('admin.console.apiKeys.revoke.revoking')
                : t('admin.console.apiKeys.revoke.submit')}
            </Button>
          </>
        }
        closeLabel={t('admin.console.apiKeys.actions.close')}
        description={t('admin.console.apiKeys.revoke.description', {
          name: revokeTarget?.name ?? '',
        })}
        onOpenChange={(open) => {
          if (!open && !revoking) {
            clearRevokeDialog();
          }
        }}
        open={Boolean(revokeTarget)}
        title={t('admin.console.apiKeys.revoke.title')}
      >
        {revokeError ? (
          <InlineNotice role="alert" tone="danger">
            {revokeError}
          </InlineNotice>
        ) : (
          <InlineNotice tone="warning">
            {t('admin.console.apiKeys.revoke.notice')}
          </InlineNotice>
        )}
      </Dialog>
    </div>
  );
}
