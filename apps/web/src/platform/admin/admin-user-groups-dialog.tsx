import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Button,
  Dialog,
  SearchField,
  useConfirm,
  useFeedback,
} from '@open-work-hub/ui';
import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import type { AuthUser } from '@/src/platform/auth/auth-api';

type Group = ApiSchema<'GroupResponse'>;
type GroupList = ApiSchema<'GroupListResponse'>;

export function UserGroupsDialog({
  token,
  user,
  onClose,
  onChanged,
  onEditUser,
}: {
  token: string;
  user: AuthUser;
  onClose: () => void;
  onChanged: () => void;
  onEditUser: () => void;
}) {
  const { t } = useTranslation('shell');
  const feedback = useFeedback();
  const { confirm, confirmDialog } = useConfirm();
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [candidates, setCandidates] = useState<GroupList | null>(null);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setGroups(null);
    setError(null);
    const load = async () => {
      const items: Group[] = [];
      for (let currentPage = 1; ; currentPage += 1) {
        const params = new URLSearchParams({
          member_user_id: user.id,
          include_inactive: 'true',
          page_size: '200',
          page: String(currentPage),
        });
        const result = await apiFetchJson<GroupList>(
          `/api/v1/admin/groups?${params}`,
          token,
          { signal: controller.signal },
        );
        items.push(...result.items);
        if (items.length >= result.total || result.items.length === 0) break;
      }
      if (!controller.signal.aborted) setGroups(items);
    };
    void load().catch((caught: unknown) => {
      if (!controller.signal.aborted)
        setError(
          caught instanceof Error
            ? caught.message
            : t('companyGroups.loadFailed'),
        );
    });
    return () => controller.abort();
  }, [token, user.id, revision, t]);
  useEffect(() => {
    const controller = new AbortController();
    setCandidates(null);
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({
        source: 'local',
        q: query,
        page: String(page),
        page_size: '20',
      });
      void apiFetchJson<GroupList>(`/api/v1/admin/groups?${params}`, token, {
        signal: controller.signal,
      })
        .then((result) => {
          if (!controller.signal.aborted) setCandidates(result);
        })
        .catch((caught: unknown) => {
          if (!controller.signal.aborted)
            setError(
              caught instanceof Error
                ? caught.message
                : t('companyGroups.loadFailed'),
            );
        });
    }, 200);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [token, query, page, revision, t]);
  async function change(group: Group, assigned: boolean) {
    setSaving(true);
    try {
      if (
        !assigned &&
        !(await confirm({
          title: t('companyGroups.revokeTitle'),
          description: t('companyGroups.removeMembersNotice', { count: 1 }),
          confirmLabel: t('companyGroups.removeMember'),
          cancelLabel: t('common:actions.cancel'),
          variant: 'danger',
        }))
      )
        return;
      await apiFetchJson(
        `/api/v1/admin/groups/${group.id}/members/${user.id}`,
        token,
        {
          method: 'PUT',
          body: JSON.stringify({ assigned }),
        },
      );
      setRevision((value) => value + 1);
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
  }
  const canAdd = user.status === 'active' && !user.login_blocked;
  return (
    <>
      <Dialog
        open
        title={t('companyGroups.userGroups', { name: user.display_name })}
        closeLabel={t('directory.close')}
        onOpenChange={(open) => {
          if (!open && !saving) onClose();
        }}
        maxWidth="max-w-2xl"
      >
        <div className="space-y-5">
          {error ? (
            <div role="alert" className="text-app-danger-text">
              {error}
              <Button
                variant="ghost"
                onClick={() => setRevision((value) => value + 1)}
              >
                {t('directory.retry')}
              </Button>
            </div>
          ) : null}
          <section className="space-y-2">
            <h3 className="app-text-body-sm font-semibold">
              {t('companyGroups.assignedGroups')}
            </h3>
            {groups === null ? (
              <p role="status">{t('directory.loading')}</p>
            ) : groups.length === 0 ? (
              <p className="text-app-ink/60">
                {t('companyGroups.noAssignedGroups')}
              </p>
            ) : (
              <ul className="divide-y divide-app-border">
                {groups.map((group) => (
                  <li
                    key={group.id}
                    className="flex items-center justify-between gap-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="break-words font-medium">{group.name}</p>
                      <p className="app-text-caption text-app-ink/60">
                        {t(
                          group.source === 'hr'
                            ? 'companyGroups.hrAssignment'
                            : 'companyGroups.manualAssignment',
                        )}
                        {!group.active
                          ? ` · ${t('companyGroups.inactive')}`
                          : ''}
                      </p>
                    </div>
                    {group.source === 'local' ? (
                      <Button
                        variant="ghost"
                        disabled={saving}
                        onClick={() => void change(group, false)}
                      >
                        {t('companyGroups.removeMember')}
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        disabled={saving}
                        onClick={onEditUser}
                      >
                        {t('companyGroups.editAssignment')}
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="space-y-3 border-t border-app-border pt-4">
            <h3 className="app-text-body-sm font-semibold">
              {t('companyGroups.addToGroup')}
            </h3>
            <p className="app-text-caption text-app-ink/60">
              {t(
                canAdd
                  ? 'companyGroups.userGroupsHint'
                  : 'companyGroups.inactiveUserHint',
              )}
            </p>
            <SearchField
              aria-label={t('directory.searchGroups')}
              placeholder={t('directory.searchGroups')}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
            />
            {candidates === null ? (
              <p role="status">{t('directory.loading')}</p>
            ) : candidates.items.length === 0 ? (
              <p>{t('directory.noResults')}</p>
            ) : (
              <ul className="divide-y divide-app-border">
                {candidates.items.map((group) => {
                  const assigned = groups?.some((item) => item.id === group.id);
                  return (
                    <li
                      key={group.id}
                      className="flex items-center justify-between gap-3 py-2"
                    >
                      <span className="min-w-0 break-words">{group.name}</span>
                      <Button
                        variant="secondary"
                        disabled={!groups || saving || assigned || !canAdd}
                        onClick={() => void change(group, true)}
                      >
                        {t(
                          assigned
                            ? 'companyGroups.alreadyAssigned'
                            : 'companyGroups.addMember',
                        )}
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}
            {(candidates?.total ?? 0) > 20 || page > 1 ? (
              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  disabled={page === 1 || !candidates}
                  onClick={() => setPage(page - 1)}
                >
                  {t('directory.previous')}
                </Button>
                <Button
                  variant="ghost"
                  disabled={!candidates || page * 20 >= candidates.total}
                  onClick={() => setPage(page + 1)}
                >
                  {t('directory.next')}
                </Button>
              </div>
            ) : null}
          </section>
        </div>
      </Dialog>
      {confirmDialog}
    </>
  );
}
