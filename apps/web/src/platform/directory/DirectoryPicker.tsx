import { UserSearchMultiSelect } from '@/src/platform/users/UserSearchMultiSelect';
import { Button } from '@open-work-hub/ui';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  listDirectoryOptions,
  type DirectoryKind,
  type DirectoryOption,
} from './directory-api';

function DirectoryPickerContent({
  token,
  kind,
  selectedIds,
  onChange,
  disabled = false,
  single = false,
}: {
  token: string;
  kind: DirectoryKind;
  selectedIds: readonly string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  single?: boolean;
}) {
  const { t } = useTranslation('shell');
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<DirectoryOption[]>([]);
  const [labels, setLabels] = useState<Record<string, DirectoryOption>>({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const selectedKey = JSON.stringify(selectedIds);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const timer = window.setTimeout(() => {
      listDirectoryOptions(token, kind, {
        query,
        page,
        signal: controller.signal,
      })
        .then((response) => {
          if (controller.signal.aborted) return;
          setItems((previous) =>
            page === 1
              ? response.items
              : [
                  ...new Map(
                    [...previous, ...response.items].map((item) => [
                      item.id,
                      item,
                    ]),
                  ).values(),
                ],
          );
          setTotal(response.total);
          setLabels((previous) => ({
            ...previous,
            ...Object.fromEntries(
              response.items.map((item) => [item.id, item]),
            ),
          }));
        })
        .catch((caught: unknown) => {
          if (!controller.signal.aborted)
            setError(
              caught instanceof Error
                ? caught.message
                : t('directory.loadFailed'),
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
  }, [token, kind, query, page, retry, t]);

  useEffect(() => {
    const controller = new AbortController();
    const ids = JSON.parse(selectedKey) as string[];
    const load = async () => {
      for (let offset = 0; offset < ids.length; offset += 200) {
        const response = await listDirectoryOptions(token, kind, {
          ids: ids.slice(offset, offset + 200),
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setLabels((previous) => ({
          ...previous,
          ...Object.fromEntries(response.items.map((item) => [item.id, item])),
        }));
      }
    };
    void load().catch((caught: unknown) => {
      if (!controller.signal.aborted)
        setError(
          caught instanceof Error ? caught.message : t('directory.loadFailed'),
        );
    });
    return () => controller.abort();
  }, [token, kind, selectedKey, t]);

  const selected = useMemo(
    () =>
      selectedIds.map(
        (id) =>
          labels[id] ?? {
            id,
            display_name: t('directory.unavailableSelection'),
            email: '',
          },
      ),
    [selectedIds, labels, t],
  );
  return (
    <div className="space-y-2">
      <UserSearchMultiSelect
        candidates={items}
        selectedUsers={selected}
        disabled={disabled}
        loading={loading}
        query={query}
        queryFocused={focused}
        onQueryFocusChange={setFocused}
        onQueryChange={(value) => {
          setQuery(value);
          setPage(1);
          setItems([]);
        }}
        onAddUser={(item) => {
          setLabels((previous) => ({ ...previous, [item.id]: item }));
          onChange(
            single ? [item.id] : [...new Set([...selectedIds, item.id])],
          );
        }}
        onRemoveUser={(id) =>
          onChange(selectedIds.filter((value) => value !== id))
        }
        labels={{
          noUserMatch: t('directory.noResults'),
          removeItem: (name) => t('directory.remove', { name }),
          searchPlaceholder: t(
            kind === 'people'
              ? 'directory.searchPeople'
              : 'directory.searchGroups',
          ),
          searchPrompt: t('directory.searchPrompt'),
          searching: t('directory.loading'),
        }}
      />
      {error ? (
        <div role="alert" className="app-text-caption text-app-danger-text">
          {error}
          <Button
            variant="ghost"
            onClick={() => setRetry((value) => value + 1)}
          >
            {t('directory.retry')}
          </Button>
        </div>
      ) : null}
      {focused && items.length < total ? (
        <Button
          variant="ghost"
          disabled={loading || disabled}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setPage((value) => value + 1)}
        >
          {t('directory.loadMore')}
        </Button>
      ) : null}
    </div>
  );
}

export function DirectoryPicker(
  props: Parameters<typeof DirectoryPickerContent>[0],
) {
  return (
    <DirectoryPickerContent
      key={[props.token, props.kind].join(':')}
      {...props}
    />
  );
}
