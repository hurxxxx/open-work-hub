import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, InlineNotice, useFeedback } from '@open-work-hub/ui';
import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { DirectoryPicker } from '@/src/platform/directory/DirectoryPicker';
type Grant = ApiSchema<'DocGroupShareResponse'>;
type Role = Grant['access_level'];
function DocsGroupSharingContent({
  token,
  resourceId,
  canManage,
  ownershipKind = 'personal',
}: {
  token: string;
  resourceId: string;
  canManage: boolean;
  ownershipKind?: 'personal' | 'company';
}) {
  const { t } = useTranslation('shell');
  const feedback = useFeedback();
  const [items, setItems] = useState<Grant[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [role, setRole] = useState<Role>('read');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const endpoint = `/api/v1/docs/items/${encodeURIComponent(resourceId)}/sharing/groups`;
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError(null);
    setItems([]);
    apiFetchJson<Grant[]>(endpoint, token, { signal: controller.signal })
      .then((rows) => {
        if (!controller.signal.aborted) setItems(rows);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error ? caught.message : t('groupSharing.failed'),
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [endpoint, revision, t, token]);
  async function change(groupId: string, nextRole: Role | null) {
    setBusy(true);
    setError(null);
    try {
      await apiFetchJson<Grant | void>(
        `${endpoint}/${encodeURIComponent(groupId)}`,
        token,
        {
          method: nextRole ? 'PUT' : 'DELETE',
          ...(nextRole
            ? { body: JSON.stringify({ access_level: nextRole }) }
            : {}),
        },
      );
      feedback.success(t('groupSharing.saved'));
      setSelectedIds([]);
      setRevision((value) => value + 1);
    } catch (caught) {
      feedback.error(
        caught instanceof Error ? caught.message : t('groupSharing.failed'),
      );
      setBusy(false);
    }
  }
  const roles: Role[] = ['read', 'edit'];
  return (
    <section className="space-y-3 rounded border border-app-border p-3">
      <h3 className="app-text-control-sm">{t('groupSharing.title')}</h3>
      <p className="app-text-caption text-app-ink/60">
        {t(
          ownershipKind === 'company'
            ? 'contentPublication.company'
            : 'contentPublication.personal',
        )}
      </p>
      <p className="app-text-caption text-app-ink/60">
        {t('groupSharing.description')}
      </p>
      {error ? (
        <InlineNotice tone="danger">
          {error}
          <Button onClick={() => setRevision((value) => value + 1)}>
            {t('common:actions.retry')}
          </Button>
        </InlineNotice>
      ) : null}
      {busy ? (
        <p>{t('common:feedback.loading')}</p>
      ) : items.length === 0 ? (
        <p>{t('groupSharing.empty')}</p>
      ) : null}
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.group_id} className="flex flex-wrap items-center gap-2">
            <span className="min-w-0 flex-1">
              {item.name +
                (item.active ? '' : ` (${t('groupSharing.inactive')})`)}
            </span>
            <span>{t(`groupSharing.roles.${item.access_level}`)}</span>
            {canManage ? (
              <>
                <select
                  aria-label={t('groupSharing.role')}
                  className="app-field-input-sm w-auto"
                  disabled={busy}
                  value={item.access_level}
                  onChange={(event) =>
                    void change(item.group_id, event.target.value as Role)
                  }
                >
                  {roles.map((value) => (
                    <option key={value} value={value}>
                      {t(`groupSharing.roles.${value}`)}
                    </option>
                  ))}
                </select>
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => void change(item.group_id, null)}
                >
                  {t('common:actions.remove')}
                </Button>
              </>
            ) : null}
          </li>
        ))}
      </ul>
      {canManage ? (
        <div className="space-y-2">
          <DirectoryPicker
            token={token}
            kind="groups"
            selectedIds={selectedIds}
            onChange={setSelectedIds}
            single
            disabled={busy}
          />
          <div className="flex items-center gap-2">
            <select
              aria-label={t('groupSharing.role')}
              className="app-field-input-sm w-auto"
              value={role}
              disabled={busy}
              onChange={(event) => setRole(event.target.value as Role)}
            >
              {roles.map((value) => (
                <option key={value} value={value}>
                  {t(`groupSharing.roles.${value}`)}
                </option>
              ))}
            </select>
            <Button
              disabled={busy || selectedIds.length !== 1}
              onClick={() => void change(selectedIds[0], role)}
            >
              {t('groupSharing.grant')}
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function DocsGroupSharing(
  props: Parameters<typeof DocsGroupSharingContent>[0],
) {
  return (
    <DocsGroupSharingContent
      key={[props.token, props.resourceId, props.canManage].join(':')}
      {...props}
    />
  );
}
