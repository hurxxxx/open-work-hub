import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, SearchField } from '@open-work-hub/ui';
import type { ApiSchema } from '@/src/platform/api/types';
import { DirectoryPicker } from '@/src/platform/directory/DirectoryPicker';
import { listDirectoryOptions } from '@/src/platform/directory/directory-api';

type Member = ApiSchema<'GroupMemberResponse'>;

export function GroupMembers({
  token,
  ids,
  items,
  onChange,
  readOnly,
  disabled,
  active,
}: {
  token: string;
  ids: string[];
  items: Member[];
  onChange: (ids: string[]) => void;
  readOnly: boolean;
  disabled: boolean;
  active: boolean;
}) {
  const { t } = useTranslation('shell');
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState(false);
  const [retry, setRetry] = useState(0);
  const itemById = new Map(items.map((item) => [item.id, item]));
  const missingKey = JSON.stringify(ids.filter((id) => !itemById.has(id)));
  useEffect(() => {
    const controller = new AbortController();
    setLoadError(false);
    const load = async () => {
      const missing = JSON.parse(missingKey) as string[];
      for (let offset = 0; offset < missing.length; offset += 200) {
        const result = await listDirectoryOptions(token, 'people', {
          ids: missing.slice(offset, offset + 200),
          signal: controller.signal,
        });
        if (!controller.signal.aborted)
          setLabels((previous) => ({
            ...previous,
            ...Object.fromEntries(
              result.items.map((item) => [item.id, item.display_name]),
            ),
          }));
      }
    };
    void load().catch(() => {
      if (!controller.signal.aborted) setLoadError(true);
    });
    return () => controller.abort();
  }, [missingKey, token, retry]);
  const members = ids
    .map((id) => ({
      id,
      item: itemById.get(id),
      name:
        itemById.get(id)?.display_name ??
        labels[id] ??
        t('directory.unavailableSelection'),
    }))
    .filter((member) =>
      `${member.name} ${member.item?.login_id ?? ''}`
        .toLocaleLowerCase()
        .includes(query.trim().toLocaleLowerCase()),
    );
  const currentPage = Math.min(
    page,
    Math.max(1, Math.ceil(members.length / 20)),
  );
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="app-text-body-sm font-semibold">
          {t('companyGroups.memberCount', { count: ids.length })}
        </h3>
        {!readOnly ? (
          <Button
            variant="secondary"
            disabled={disabled || !active}
            aria-expanded={adding}
            onClick={() => setAdding(!adding)}
          >
            {t(
              adding ? 'companyGroups.closePicker' : 'companyGroups.addMembers',
            )}
          </Button>
        ) : null}
      </div>
      {!readOnly && !active ? (
        <p className="app-text-caption text-app-ink/60">
          {t('companyGroups.inactiveGroupHint')}
        </p>
      ) : null}
      {adding && !readOnly ? (
        <DirectoryPicker
          token={token}
          kind="people"
          selectedIds={ids}
          disabled={disabled}
          onChange={onChange}
        />
      ) : null}
      {loadError ? (
        <div role="alert">
          {t('directory.loadFailed')}
          <Button variant="ghost" onClick={() => setRetry(retry + 1)}>
            {t('directory.retry')}
          </Button>
        </div>
      ) : null}
      {ids.length > 0 ? (
        <SearchField
          aria-label={t('companyGroups.searchMembers')}
          placeholder={t('companyGroups.searchMembers')}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
        />
      ) : null}
      {ids.length === 0 ? (
        <p className="py-4 text-app-ink/60">
          {t(
            readOnly ? 'companyGroups.noHrMembers' : 'companyGroups.noMembers',
          )}
        </p>
      ) : members.length === 0 ? (
        <p>{t('directory.noResults')}</p>
      ) : (
        <ul className="divide-y divide-app-border">
          {members
            .slice((currentPage - 1) * 20, currentPage * 20)
            .map(({ id, item, name }) => (
              <li
                key={id}
                className="flex items-center justify-between gap-3 py-2"
              >
                <div className="min-w-0">
                  <p className="break-words font-medium">{name}</p>
                  <p className="app-text-caption text-app-ink/60">
                    {item?.login_id}
                    {item && (item.status !== 'active' || item.login_blocked)
                      ? ` · ${t('companyGroups.memberAccessInactive')}`
                      : ''}
                  </p>
                </div>
                {!readOnly ? (
                  <Button
                    variant="ghost"
                    disabled={disabled}
                    aria-label={t('companyGroups.removeNamedMember', { name })}
                    onClick={() =>
                      onChange(ids.filter((value) => value !== id))
                    }
                  >
                    {t('companyGroups.removeMember')}
                  </Button>
                ) : null}
              </li>
            ))}
        </ul>
      )}
      {members.length > 20 ? (
        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            disabled={currentPage === 1}
            onClick={() => setPage(currentPage - 1)}
          >
            {t('directory.previous')}
          </Button>
          <Button
            variant="ghost"
            disabled={currentPage * 20 >= members.length}
            onClick={() => setPage(currentPage + 1)}
          >
            {t('directory.next')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
