import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { DirectoryPicker } from '@/src/platform/directory/DirectoryPicker';
import { Button, Dialog, useConfirm, useFeedback } from '@open-work-hub/ui';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FORM_FIELD_CLASS } from './admin-shared';

type Group = ApiSchema<'GroupResponse'>;
function GroupsSectionContent({ token }: { token: string }) {
  const { t } = useTranslation('shell');
  const feedback = useFeedback();
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [response, setResponse] =
    useState<ApiSchema<'GroupListResponse'> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<Group | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({
        q: query,
        page: String(page),
        page_size: '50',
        include_inactive: 'true',
      });
      apiFetchJson<ApiSchema<'GroupListResponse'>>(
        `/api/v1/admin/groups?${params}`,
        token,
        { signal: controller.signal },
      )
        .then((next) => {
          if (!controller.signal.aborted) setResponse(next);
        })
        .catch((caught: unknown) => {
          if (!controller.signal.aborted)
            setError(
              caught instanceof Error
                ? caught.message
                : t('companyGroups.loadFailed'),
            );
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 200);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, page, revision, token, t]);
  const create = async () => {
    setSaving(true);
    try {
      const group = await apiFetchJson<Group>('/api/v1/admin/groups', token, {
        method: 'POST',
        body: JSON.stringify({ name: newName.trim() }),
      });
      setCreating(false);
      setNewName('');
      setSelected(group);
      setRevision((value) => value + 1);
      feedback.success(t('companyGroups.created'));
    } catch (caught) {
      feedback.error(
        caught instanceof Error
          ? caught.message
          : t('companyGroups.saveFailed'),
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="space-y-4">
      <p className="app-text-caption text-app-ink/60">
        {t('companyGroups.policy')}
      </p>
      <div className="flex gap-2">
        <input
          className={FORM_FIELD_CLASS}
          value={query}
          aria-label={t('directory.searchGroups')}
          placeholder={t('directory.searchGroups')}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
        />
        <Button onClick={() => setCreating(true)}>
          {t('companyGroups.create')}
        </Button>
      </div>
      {error ? (
        <div role="alert">
          {error}
          <Button onClick={() => setRevision((value) => value + 1)}>
            {t('directory.retry')}
          </Button>
        </div>
      ) : null}
      {loading ? (
        <p role="status">{t('directory.loading')}</p>
      ) : !response?.items.length ? (
        <p>{t('directory.noResults')}</p>
      ) : (
        <table className="w-full text-left app-text-body-sm">
          <thead>
            <tr className="border-b border-app-border">
              <th className="py-2">{t('companyGroups.name')}</th>
              <th>{t('companyGroups.kind')}</th>
              <th>{t('companyGroups.status')}</th>
            </tr>
          </thead>
          <tbody>
            {response.items.map((group) => (
              <tr key={group.id} className="border-b border-app-border">
                <td className="py-2">
                  <button
                    className="text-app-accent"
                    onClick={() => setSelected(group)}
                  >
                    {group.name}
                  </button>
                </td>
                <td>
                  {t(
                    group.kind === 'organization'
                      ? 'companyGroups.organization'
                      : 'companyGroups.manual',
                  )}
                </td>
                <td>
                  {t(
                    group.active
                      ? 'companyGroups.active'
                      : 'companyGroups.inactive',
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="flex gap-2">
        <Button
          variant="ghost"
          disabled={page === 1 || loading}
          onClick={() => setPage((value) => value - 1)}
        >
          {t('directory.previous')}
        </Button>
        <Button
          variant="ghost"
          disabled={loading || page * 50 >= (response?.total ?? 0)}
          onClick={() => setPage((value) => value + 1)}
        >
          {t('directory.next')}
        </Button>
      </div>
      <Dialog
        open={creating}
        onOpenChange={(open) => {
          if (!saving) setCreating(open);
        }}
        title={t('companyGroups.create')}
        closeLabel={t('directory.close')}
        actions={
          <Button
            disabled={saving || !newName.trim()}
            onClick={() => void create()}
          >
            {t('companyGroups.create')}
          </Button>
        }
      >
        <label className="block">
          <span>{t('companyGroups.name')}</span>
          <input
            autoFocus
            className={FORM_FIELD_CLASS}
            maxLength={120}
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
          />
        </label>
      </Dialog>
      {selected ? (
        <GroupEditor
          key={selected.id}
          token={token}
          group={selected}
          onClose={() => setSelected(null)}
          onChanged={() => setRevision((value) => value + 1)}
        />
      ) : null}
    </div>
  );
}

export function GroupsSection({ token }: { token: string }) {
  return <GroupsSectionContent key={token} token={token} />;
}

function GroupEditor({
  token,
  group,
  onClose,
  onChanged,
}: {
  token: string;
  group: Group;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation('shell');
  const feedback = useFeedback();
  const { confirm, confirmDialog } = useConfirm();
  const persistedMembers = useRef<readonly string[]>([]);
  const persistedActive = useRef(group.active);
  const [name, setName] = useState(group.name);
  const [description, setDescription] = useState(group.description);
  const [active, setActive] = useState(group.active);
  const [members, setMembers] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [retry, setRetry] = useState(0);
  const manual = group.kind === 'manual';
  useEffect(() => {
    const controller = new AbortController();
    setMembers(null);
    setError(null);
    apiFetchJson<ApiSchema<'GroupMembersResponse'>>(
      `/api/v1/admin/groups/${group.id}/members`,
      token,
      { signal: controller.signal },
    )
      .then((response) => {
        if (!controller.signal.aborted) {
          persistedMembers.current = response.user_ids;
          setMembers(response.user_ids);
        }
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error
              ? caught.message
              : t('companyGroups.loadFailed'),
          );
      });
    return () => controller.abort();
  }, [group.id, token, retry, t]);
  const save = async (membership: boolean) => {
    setSaving(true);
    try {
      const removed = membership
        ? persistedMembers.current.filter((id) => !members?.includes(id)).length
        : 0;
      if (
        (membership && removed > 0) ||
        (!membership && persistedActive.current && !active)
      ) {
        const accepted = await confirm({
          title: t('companyGroups.revokeTitle'),
          description: t(
            membership
              ? 'companyGroups.removeMembersNotice'
              : 'companyGroups.deactivateNotice',
            { count: removed },
          ),
          confirmLabel: t('companyGroups.confirmRevocation'),
          cancelLabel: t('common:actions.cancel'),
          variant: 'danger',
        });
        if (!accepted) return;
      }
      await apiFetchJson(
        `/api/v1/admin/groups/${group.id}${membership ? '/members' : ''}`,
        token,
        {
          method: membership ? 'PUT' : 'PATCH',
          body: JSON.stringify(
            membership
              ? { user_ids: members }
              : { name: name.trim(), description, active },
          ),
        },
      );
      if (membership) persistedMembers.current = members ?? [];
      else persistedActive.current = active;
      onChanged();
      feedback.success(t('companyGroups.saved'));
    } catch (caught) {
      feedback.error(
        caught instanceof Error
          ? caught.message
          : t('companyGroups.saveFailed'),
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      <Dialog
        open
        onOpenChange={(open) => {
          if (!open && !saving) onClose();
        }}
        title={group.name}
        closeLabel={t('directory.close')}
        maxWidth="max-w-2xl"
      >
        <div className="space-y-4">
          {!manual ? (
            <p className="app-text-caption text-app-ink/60">
              {t('companyGroups.organizationRule')}
            </p>
          ) : (
            <fieldset disabled={saving} className="space-y-3">
              <label className="block">
                <span>{t('companyGroups.name')}</span>
                <input
                  className={FORM_FIELD_CLASS}
                  value={name}
                  maxLength={120}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label className="block">
                <span>{t('companyGroups.description')}</span>
                <textarea
                  className={FORM_FIELD_CLASS}
                  value={description}
                  maxLength={1000}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={active}
                  onChange={(event) => setActive(event.target.checked)}
                />
                {t('companyGroups.active')}
              </label>
              <Button
                disabled={saving || !name.trim()}
                onClick={() => void save(false)}
              >
                {t('companyGroups.saveDetails')}
              </Button>
            </fieldset>
          )}
          <div className="border-t border-app-border pt-4">
            <p>{t('companyGroups.members')}</p>
            {error ? (
              <div role="alert">
                {error}
                <Button onClick={() => setRetry((value) => value + 1)}>
                  {t('directory.retry')}
                </Button>
              </div>
            ) : members ? (
              <DirectoryPicker
                token={token}
                kind="people"
                selectedIds={members}
                disabled={!manual || saving}
                onChange={setMembers}
              />
            ) : (
              <p role="status">{t('directory.loading')}</p>
            )}
            {manual ? (
              <Button
                disabled={saving || members === null}
                onClick={() => void save(true)}
              >
                {t('companyGroups.saveMembers')}
              </Button>
            ) : null}
          </div>
        </div>
      </Dialog>
      {confirmDialog}
    </>
  );
}
