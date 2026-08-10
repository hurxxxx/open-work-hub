import React, {
  type ClipboardEvent,
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { CircleHelp, Search, X } from 'lucide-react';

import { Tooltip } from '@open-work-hub/ui';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { UserSearchMultiSelect } from '@/src/platform/users/UserSearchMultiSelect';

import {
  listAdminUsers,
  type AiSecurityExternalTransferException,
  type AiSecurityPolicyRule,
  type WorkspaceItem,
} from './admin-api';
import {
  type AiSecurityAppOption,
  type AiSecurityConditionOption,
  aiSecurityMatchesSearch,
  aiSecurityNullable,
  aiSecurityPresent,
  aiSecurityTermsText,
  parseAiSecurityTerms,
} from './admin-ai-security-model';
import { Badge, FORM_FIELD_CLASS as fieldClassName } from './admin-shared';

export type AiSecuritySelectedUser = {
  id: string;
  full_name?: string | null;
  display_name?: string | null;
  email: string;
};

function aiSecuritySelectedUserFromAuthUser(
  user: AuthUser,
): AiSecuritySelectedUser {
  return {
    id: user.id,
    full_name: user.full_name,
    display_name: user.display_name,
    email: user.email,
  };
}

export function aiSecuritySelectedUserFromRule(
  rule: AiSecurityPolicyRule,
): AiSecuritySelectedUser | null {
  if (!rule.user_id) return null;
  return {
    id: rule.user_id,
    full_name: rule.user_name ?? rule.user_id,
    display_name: rule.user_name ?? rule.user_id,
    email: '',
  };
}

export function aiSecuritySelectedUserFromException(
  exception: AiSecurityExternalTransferException,
): AiSecuritySelectedUser | null {
  if (!exception.user_id) return null;
  return {
    id: exception.user_id,
    full_name: exception.user_name ?? exception.user_id,
    display_name: exception.user_name ?? exception.user_id,
    email: '',
  };
}

function AiSecurityHelpIcon({ content }: { content: string }) {
  return (
    <Tooltip content={content}>
      <button
        aria-label={content}
        className="inline-flex size-5 items-center justify-center rounded-full text-app-ink/45 hover:bg-app-surface-sidebar hover:text-app-ink"
        type="button"
      >
        <CircleHelp size={14} />
      </button>
    </Tooltip>
  );
}

export function AiSecurityFieldLabel({
  label,
  help,
}: {
  label: string;
  help?: string;
}) {
  return (
    <span className="app-text-control flex items-center gap-1.5 text-app-ink">
      <span>{label}</span>
      {help ? <AiSecurityHelpIcon content={help} /> : null}
    </span>
  );
}

export function AiSecurityConditionInput({
  help,
  label,
  listId,
  onChange,
  options,
  placeholder,
  value,
}: {
  help: string;
  label: string;
  listId: string;
  onChange: (value: string | null) => void;
  options: AiSecurityConditionOption[];
  placeholder: string;
  value: string | null | undefined;
}) {
  return (
    <label className="space-y-1">
      <AiSecurityFieldLabel help={help} label={label} />
      <input
        className={fieldClassName}
        list={options.length ? listId : undefined}
        onChange={(event) => onChange(aiSecurityNullable(event.target.value))}
        placeholder={placeholder}
        value={value ?? ''}
      />
      {options.length ? (
        <datalist id={listId}>
          {options.map((option) => (
            <option
              key={option.value}
              label={option.label ?? undefined}
              value={option.value}
            />
          ))}
        </datalist>
      ) : null}
    </label>
  );
}

export function AiSecurityTermsTagInput({
  emptyLabel,
  help,
  label,
  onChange,
  placeholder,
  removeLabel,
  summaryLabel,
  value,
}: {
  emptyLabel: string;
  help?: string;
  label?: string;
  onChange: (value: string) => void;
  placeholder: string;
  removeLabel: string;
  summaryLabel: string;
  value: string;
}) {
  const [draft, setDraft] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);
  const terms = useMemo(() => parseAiSecurityTerms(value), [value]);

  const updateTerms = useCallback(
    (nextTerms: string[]) => {
      onChange(aiSecurityTermsText(nextTerms));
    },
    [onChange],
  );

  const addTerms = useCallback(
    (rawValue: string) => {
      const nextTerms = parseAiSecurityTerms(rawValue);
      if (nextTerms.length === 0) return;
      updateTerms(Array.from(new Set([...terms, ...nextTerms])));
      setDraft('');
    },
    [terms, updateTerms],
  );

  const removeTerm = useCallback(
    (term: string) => {
      updateTerms(terms.filter((item) => item !== term));
    },
    [terms, updateTerms],
  );

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === 'Tab' || event.key === ',') {
      if (draft.trim()) {
        event.preventDefault();
        addTerms(draft);
      }
      return;
    }
    if (event.key === 'Backspace' && draft.length === 0 && terms.length > 0) {
      updateTerms(terms.slice(0, -1));
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>) => {
    const pastedText = event.clipboardData.getData('text');
    if (!/[\r\n,]/.test(pastedText)) return;
    event.preventDefault();
    addTerms(pastedText);
  };

  return (
    <div className="space-y-2">
      {label ? <AiSecurityFieldLabel help={help} label={label} /> : null}
      <div
        className="min-h-24 rounded-md border border-app-border bg-app-surface p-2 text-app-ink focus-within:border-app-accent focus-within:ring-2 focus-within:ring-app-accent/15"
        onClick={() => inputRef.current?.focus()}
      >
        <div className="flex max-h-56 flex-wrap gap-1.5 overflow-y-auto">
          {terms.map((term) => (
            <span
              className="app-text-caption inline-flex max-w-full items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
              key={term}
            >
              <span className="max-w-64 truncate">{term}</span>
              <button
                aria-label={`${removeLabel}: ${term}`}
                className="inline-flex size-4 items-center justify-center rounded-full text-app-ink/45 hover:bg-app-surface-hover hover:text-app-ink"
                onClick={(event) => {
                  event.stopPropagation();
                  removeTerm(term);
                }}
                type="button"
              >
                <X size={11} />
              </button>
            </span>
          ))}
          <input
            className="app-text-body-sm min-w-48 flex-1 bg-transparent px-1 py-1.5 text-app-ink outline-none placeholder:text-app-ink/40"
            onBlur={() => addTerms(draft)}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={placeholder}
            ref={inputRef}
            value={draft}
          />
        </div>
      </div>
      <p className="app-text-caption text-app-ink/55">
        {terms.length > 0 ? summaryLabel : emptyLabel}
      </p>
    </div>
  );
}

function AiSecuritySearchSelect<TItem>({
  allLabel,
  clearLabel,
  filterItem,
  getItemId,
  help,
  label,
  noResultsLabel,
  onChange,
  renderOption,
  renderSelected,
  searchPlaceholder,
  selectedFallbackLabel,
  value,
  items,
}: {
  allLabel: string;
  clearLabel: string;
  filterItem: (item: TItem, query: string) => boolean;
  getItemId: (item: TItem) => string;
  help: string;
  label: string;
  noResultsLabel: string;
  onChange: (value: string | null) => void;
  renderOption: (item: TItem) => ReactNode;
  renderSelected: (item: TItem) => ReactNode;
  searchPlaceholder: string;
  selectedFallbackLabel?: string;
  value: string | null | undefined;
  items: readonly TItem[];
}) {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const selectedItem = value
    ? items.find((item) => getItemId(item) === value)
    : undefined;
  const normalizedQuery = query.trim().toLowerCase();
  const candidates = useMemo(
    () =>
      items
        .filter((item) =>
          normalizedQuery ? filterItem(item, normalizedQuery) : true,
        )
        .slice(0, 24),
    [filterItem, items, normalizedQuery],
  );

  useEffect(() => {
    setQuery('');
    setFocused(false);
  }, [value]);

  return (
    <div className="space-y-1">
      <AiSecurityFieldLabel help={help} label={label} />
      {selectedItem ? (
        <div className="app-text-caption flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink">
          <span className="min-w-0 flex-1">{renderSelected(selectedItem)}</span>
          <button
            aria-label={clearLabel}
            className="text-app-ink/45 hover:text-app-ink"
            onClick={() => onChange(null)}
            type="button"
          >
            <X size={13} />
          </button>
        </div>
      ) : value ? (
        <div className="app-text-caption flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink">
          <span className="min-w-0 flex-1 truncate">
            {selectedFallbackLabel ?? value}
          </span>
          <button
            aria-label={clearLabel}
            className="text-app-ink/45 hover:text-app-ink"
            onClick={() => onChange(null)}
            type="button"
          >
            <X size={13} />
          </button>
        </div>
      ) : (
        <div className="app-text-caption rounded-md border border-dashed border-app-border px-2 py-1 text-app-ink/45">
          {allLabel}
        </div>
      )}
      <div className="flex min-h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-app-ink focus-within:border-app-accent focus-within:ring-2 focus-within:ring-app-accent/15">
        <Search
          className="pointer-events-none shrink-0 text-app-ink/35"
          size={14}
        />
        <input
          className="app-text-body-sm min-w-0 flex-1 bg-transparent py-1.5 text-app-ink outline-none placeholder:text-app-ink/40"
          onBlur={() => {
            window.setTimeout(() => setFocused(false), 150);
          }}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setFocused(true)}
          placeholder={searchPlaceholder}
          value={query}
        />
      </div>
      {focused ? (
        <div className="max-h-52 overflow-y-auto rounded-md border border-app-border bg-app-surface">
          {candidates.length === 0 ? (
            <div className="app-text-caption px-3 py-2 text-app-ink/45">
              {noResultsLabel}
            </div>
          ) : (
            candidates.map((item) => {
              const itemId = getItemId(item);
              return (
                <button
                  className="app-text-body-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                  key={itemId}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    onChange(itemId);
                    setQuery('');
                    setFocused(false);
                  }}
                  type="button"
                >
                  {renderOption(item)}
                </button>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}

export function AiSecurityGuidance({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
      <div className="app-text-control text-app-ink">{title}</div>
      <p className="app-text-body-sm mt-1 text-app-ink/65">{description}</p>
    </div>
  );
}

export function AiSecurityFormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3 border-t border-app-border pt-4 first:border-t-0 first:pt-0">
      <div className="space-y-1">
        <div className="app-text-control text-app-ink">{title}</div>
        {description ? (
          <p className="app-text-body-sm text-app-ink/60">{description}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function AiSecurityWorkspacePicker({
  allLabel,
  clearLabel,
  help,
  label,
  noResultsLabel,
  onChange,
  searchPlaceholder,
  value,
  workspaces,
}: {
  allLabel: string;
  clearLabel: string;
  help: string;
  label: string;
  noResultsLabel: string;
  onChange: (value: string | null) => void;
  searchPlaceholder: string;
  value: string | null | undefined;
  workspaces: readonly WorkspaceItem[];
}) {
  const { t } = useTranslation('apps');
  return (
    <AiSecuritySearchSelect
      allLabel={allLabel}
      clearLabel={clearLabel}
      filterItem={(workspace, query) =>
        workspace.name.toLowerCase().includes(query) ||
        workspace.key.toLowerCase().includes(query) ||
        workspace.description.toLowerCase().includes(query)
      }
      getItemId={(workspace) => workspace.id}
      help={help}
      items={workspaces}
      label={label}
      noResultsLabel={noResultsLabel}
      onChange={onChange}
      renderOption={(workspace) => (
        <>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium">{workspace.name}</span>
            <span className="app-text-caption block truncate text-app-ink/45">
              {workspace.key}
              {workspace.description ? ` · ${workspace.description}` : ''}
            </span>
          </span>
          <Badge tone={workspace.active ? 'green' : 'amber'}>
            {t(
              workspace.active
                ? 'admin.console.workspaces.statusActive'
                : 'admin.console.workspaces.statusArchived',
            )}
          </Badge>
        </>
      )}
      renderSelected={(workspace) => (
        <span className="flex min-w-0 items-center gap-2">
          <span className="min-w-0 flex-1 truncate">{workspace.name}</span>
          <span className="shrink-0 text-app-ink/45">{workspace.key}</span>
        </span>
      )}
      searchPlaceholder={searchPlaceholder}
      selectedFallbackLabel={value ?? undefined}
      value={value}
    />
  );
}

export function AiSecurityUserPicker({
  help,
  label,
  onChange,
  selectedUser,
  token,
  value,
}: {
  help: string;
  label: string;
  onChange: (
    userId: string | null,
    user: AiSecuritySelectedUser | null,
  ) => void;
  selectedUser: AiSecuritySelectedUser | null;
  token: string;
  value: string | null | undefined;
}) {
  const { t } = useTranslation('apps');
  const [query, setQuery] = useState('');
  const [queryFocused, setQueryFocused] = useState(false);
  const [candidates, setCandidates] = useState<AuthUser[]>([]);
  const [searching, setSearching] = useState(false);
  const selectedUsers = useMemo(() => {
    if (selectedUser) return [selectedUser];
    if (!value) return [];
    return [
      {
        id: value,
        full_name: value,
        display_name: value,
        email: '',
      },
    ];
  }, [selectedUser, value]);

  useEffect(() => {
    if (!queryFocused) {
      setCandidates([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setSearching(true);
      void listAdminUsers(token, {
        page: 1,
        page_size: 10,
        q: query.trim() || undefined,
      })
        .then((response) => {
          if (!cancelled) {
            setCandidates(response.items);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setCandidates([]);
          }
        })
        .finally(() => {
          if (!cancelled) {
            setSearching(false);
          }
        });
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, queryFocused, token]);

  return (
    <div className="space-y-1">
      <AiSecurityFieldLabel help={help} label={label} />
      <UserSearchMultiSelect
        candidates={candidates}
        density="compact"
        labels={{
          currentUser: t('pms.taskDetail.me'),
          noUserMatch: t('admin.console.aiSecurity.rules.noUserResults'),
          removeItem: (name) =>
            t('admin.console.aiSecurity.rules.removeUser', { name }),
          searchPlaceholder: t(
            'admin.console.aiSecurity.rules.userSearchPlaceholder',
          ),
          searchPrompt: t('admin.console.aiSecurity.rules.userSearchPrompt'),
          searching: t('common:feedback.loading'),
        }}
        loading={searching}
        onAddUser={(candidate) => {
          onChange(candidate.id, aiSecuritySelectedUserFromAuthUser(candidate));
          setQuery('');
          setQueryFocused(false);
        }}
        onQueryChange={setQuery}
        onQueryFocusChange={setQueryFocused}
        onRemoveUser={() => onChange(null, null)}
        query={query}
        queryFocused={queryFocused}
        selectedUsers={selectedUsers}
      />
    </div>
  );
}

export function AiSecurityAppPicker({
  allLabel,
  clearLabel,
  help,
  label,
  noResultsLabel,
  onChange,
  options,
  searchPlaceholder,
  value,
}: {
  allLabel: string;
  clearLabel: string;
  help: string;
  label: string;
  noResultsLabel: string;
  onChange: (value: string | null) => void;
  options: readonly AiSecurityAppOption[];
  searchPlaceholder: string;
  value: string | null | undefined;
}) {
  return (
    <AiSecuritySearchSelect
      allLabel={allLabel}
      clearLabel={clearLabel}
      filterItem={(option, query) =>
        aiSecurityMatchesSearch(
          query,
          option.value,
          option.label,
          option.description,
        )
      }
      getItemId={(option) => option.value}
      help={help}
      items={options}
      label={label}
      noResultsLabel={noResultsLabel}
      onChange={onChange}
      renderOption={(option) => (
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">
            {option.label ?? option.value}
          </span>
          <span className="app-text-caption block truncate text-app-ink/45">
            {option.value}
            {option.description ? ` · ${option.description}` : ''}
          </span>
        </span>
      )}
      renderSelected={(option) => (
        <span className="flex min-w-0 items-center gap-2">
          <span className="min-w-0 flex-1 truncate">
            {option.label ?? option.value}
          </span>
          <span className="shrink-0 text-app-ink/45">{option.value}</span>
        </span>
      )}
      searchPlaceholder={searchPlaceholder}
      selectedFallbackLabel={value ?? undefined}
      value={value}
    />
  );
}

export function AiSecurityTaskKindPicker({
  allLabel,
  clearLabel,
  help,
  label,
  noResultsLabel,
  onChange,
  options,
  searchPlaceholder,
  value,
}: {
  allLabel: string;
  clearLabel: string;
  help: string;
  label: string;
  noResultsLabel: string;
  onChange: (value: string[]) => void;
  options: readonly AiSecurityConditionOption[];
  searchPlaceholder: string;
  value: readonly string[] | null | undefined;
}) {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const selectedValues = useMemo(
    () => Array.from(new Set((value ?? []).filter(aiSecurityPresent))),
    [value],
  );
  const optionByValue = useMemo(
    () => new Map(options.map((option) => [option.value, option])),
    [options],
  );
  const normalizedQuery = query.trim();
  const candidates = useMemo(
    () =>
      options
        .filter((option) => !selectedValues.includes(option.value))
        .filter((option) =>
          normalizedQuery
            ? aiSecurityMatchesSearch(
                normalizedQuery,
                option.value,
                option.label,
              )
            : true,
        )
        .slice(0, 24),
    [normalizedQuery, options, selectedValues],
  );

  return (
    <div className="space-y-1">
      <AiSecurityFieldLabel help={help} label={label} />
      {selectedValues.length > 0 ? (
        <div className="flex min-h-9 flex-wrap gap-1 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
          {selectedValues.map((taskKind) => {
            const option = optionByValue.get(taskKind);
            return (
              <span
                className="app-text-caption inline-flex max-w-full items-center gap-1 rounded border border-app-border bg-app-bg px-1.5 py-0.5 text-app-ink"
                key={taskKind}
              >
                <span className="max-w-[220px] truncate">
                  {option?.label ?? taskKind}
                </span>
                <button
                  aria-label={clearLabel}
                  className="text-app-ink/45 hover:text-app-ink"
                  onClick={() =>
                    onChange(selectedValues.filter((item) => item !== taskKind))
                  }
                  type="button"
                >
                  <X size={12} />
                </button>
              </span>
            );
          })}
        </div>
      ) : (
        <div className="app-text-caption rounded-md border border-dashed border-app-border px-2 py-1 text-app-ink/45">
          {allLabel}
        </div>
      )}
      <div className="flex min-h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-app-ink focus-within:border-app-accent focus-within:ring-2 focus-within:ring-app-accent/15">
        <Search
          className="pointer-events-none shrink-0 text-app-ink/35"
          size={14}
        />
        <input
          className="app-text-body-sm min-w-0 flex-1 bg-transparent py-1.5 text-app-ink outline-none placeholder:text-app-ink/40"
          onBlur={() => {
            window.setTimeout(() => setFocused(false), 150);
          }}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setFocused(true)}
          placeholder={searchPlaceholder}
          value={query}
        />
      </div>
      {focused ? (
        <div className="max-h-52 overflow-y-auto rounded-md border border-app-border bg-app-surface">
          {candidates.length === 0 ? (
            <div className="app-text-caption px-3 py-2 text-app-ink/45">
              {noResultsLabel}
            </div>
          ) : (
            candidates.map((option) => (
              <button
                className="app-text-body-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                key={option.value}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  onChange([...selectedValues, option.value]);
                  setQuery('');
                  setFocused(false);
                }}
                type="button"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">
                    {option.label ?? option.value}
                  </span>
                  <span className="app-text-caption block truncate text-app-ink/45">
                    {option.value}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
