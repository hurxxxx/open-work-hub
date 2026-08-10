import type { ReactNode } from 'react';
import { Check, Search, X } from 'lucide-react';

import {
  userOptionAvatarColorClass,
  userOptionAvatarInitials,
  userOptionDepartmentName,
  userOptionDisplayName,
  userOptionMetaParts,
  type UserOptionLike,
} from './user-option-picker-model';

export type UserSearchMultiSelectLabels = {
  currentUser?: string;
  lockedLabel?: string;
  noUserMatch: string;
  removeItem: (name: string) => string;
  searchPlaceholder: string;
  searchPrompt: string;
  searching: string;
};

type UserOptionDensity = 'default' | 'compact';

type UserSearchMultiSelectProps<TUser extends UserOptionLike> = {
  autoFocus?: boolean;
  candidates: readonly TUser[];
  density?: UserOptionDensity;
  disabled?: boolean;
  inputId?: string;
  labels: UserSearchMultiSelectLabels;
  loading?: boolean;
  currentUserId?: string | null;
  lockedUserIds?: ReadonlySet<string>;
  onAddUser: (user: TUser) => void;
  onQueryChange: (query: string) => void;
  onQueryFocusChange: (focused: boolean) => void;
  onRemoveUser: (userId: string) => void;
  query: string;
  queryFocused: boolean;
  renderCandidateTrailing?: (user: TUser) => ReactNode;
  selectedUsers: readonly UserOptionLike[];
};

export function UserOptionAvatar({
  className = '',
  sizeClassName = 'size-7',
  user,
}: {
  className?: string;
  sizeClassName?: string;
  user: UserOptionLike;
}) {
  return (
    <span
      className={`flex ${sizeClassName} shrink-0 items-center justify-center rounded-full border border-app-border text-[10px] font-semibold text-white ${userOptionAvatarColorClass(user.id)} ${className}`}
    >
      {userOptionAvatarInitials(user)}
    </span>
  );
}

export function UserOptionRow<TUser extends UserOptionLike>({
  currentUserLabel,
  currentUserId,
  density = 'default',
  disabled = false,
  onClick,
  selected = false,
  trailing,
  user,
}: {
  currentUserLabel?: string;
  currentUserId?: string | null;
  density?: UserOptionDensity;
  disabled?: boolean;
  onClick?: () => void;
  selected?: boolean;
  trailing?: ReactNode;
  user: TUser;
}) {
  const name = userOptionDisplayName(user);
  const metaParts = userOptionMetaParts(user);
  const isCurrentUser = Boolean(currentUserId && user.id === currentUserId);
  const compact = density === 'compact';

  return (
    <button
      type="button"
      disabled={disabled}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
      className={
        compact
          ? 'app-menu-item gap-2.5'
          : 'app-text-control flex w-full items-center gap-2.5 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover disabled:cursor-not-allowed disabled:opacity-50'
      }
    >
      <UserOptionAvatar
        sizeClassName={compact ? 'size-6' : 'size-7'}
        user={user}
      />
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="block truncate">{name}</span>
          {isCurrentUser && currentUserLabel ? (
            <span className="app-text-micro shrink-0 rounded-full bg-app-accent/10 px-1.5 py-0.5 text-app-accent">
              {currentUserLabel}
            </span>
          ) : null}
        </span>
        {metaParts.length > 0 ? (
          <span className="app-text-caption block truncate text-app-ink/40">
            {metaParts.join(' · ')}
          </span>
        ) : null}
      </span>
      {selected ? (
        <Check size={14} className="shrink-0 text-app-accent" />
      ) : (
        trailing
      )}
    </button>
  );
}

export function UserSearchMultiSelect<TUser extends UserOptionLike>({
  autoFocus = false,
  candidates,
  density = 'default',
  disabled = false,
  inputId,
  labels,
  loading = false,
  currentUserId,
  lockedUserIds,
  onAddUser,
  onQueryChange,
  onQueryFocusChange,
  onRemoveUser,
  query,
  queryFocused,
  renderCandidateTrailing,
  selectedUsers,
}: UserSearchMultiSelectProps<TUser>) {
  return (
    <div className="space-y-2">
      {selectedUsers.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {selectedUsers.map((user) => {
            const name = userOptionDisplayName(user);
            const department = userOptionDepartmentName(user);
            const locked = lockedUserIds?.has(user.id) ?? false;
            return (
              <span
                key={user.id}
                className="app-text-caption inline-flex max-w-full items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink"
              >
                <UserOptionAvatar
                  className="text-[7px]"
                  sizeClassName="size-4"
                  user={user}
                />
                <span className="max-w-[10rem] truncate">{name}</span>
                {department ? (
                  <span className="max-w-[8rem] truncate text-app-ink/40">
                    · {department}
                  </span>
                ) : null}
                {locked ? (
                  labels.lockedLabel ? (
                    <span className="text-app-ink/40">
                      · {labels.lockedLabel}
                    </span>
                  ) : null
                ) : (
                  <button
                    type="button"
                    aria-label={labels.removeItem(name)}
                    disabled={disabled}
                    onClick={() => onRemoveUser(user.id)}
                    className="text-app-ink/40 hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <X size={12} />
                  </button>
                )}
              </span>
            );
          })}
        </div>
      ) : null}

      <div
        className={`flex items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-app-ink focus-within:border-app-accent focus-within:ring-2 focus-within:ring-app-accent/15 ${
          disabled ? 'opacity-60' : ''
        } ${density === 'compact' ? 'min-h-9' : 'min-h-10'}`.trim()}
      >
        <Search
          size={14}
          className="pointer-events-none shrink-0 text-app-ink/35"
        />
        <input
          id={inputId}
          type="text"
          autoFocus={autoFocus}
          value={query}
          aria-label={labels.searchPlaceholder}
          disabled={disabled}
          onChange={(event) => onQueryChange(event.target.value)}
          onFocus={() => onQueryFocusChange(true)}
          onBlur={() => {
            window.setTimeout(() => onQueryFocusChange(false), 150);
          }}
          placeholder={labels.searchPlaceholder}
          className={`${
            density === 'compact' ? 'app-text-body-sm' : 'app-text-body'
          } min-w-0 flex-1 bg-transparent py-1.5 text-app-ink outline-none placeholder:text-app-ink/40 disabled:cursor-not-allowed`}
        />
      </div>

      {queryFocused ? (
        <div className="max-h-44 overflow-y-auto rounded-md border border-app-border bg-app-surface">
          {loading && candidates.length === 0 ? (
            <div className="app-text-caption px-3 py-2 text-app-ink/40">
              {labels.searching}
            </div>
          ) : candidates.length === 0 ? (
            <div className="app-text-caption px-3 py-2 text-app-ink/40">
              {query.trim() ? labels.noUserMatch : labels.searchPrompt}
            </div>
          ) : (
            <ul>
              {candidates.map((user) => {
                const selected = selectedUsers.some(
                  (selectedUser) => selectedUser.id === user.id,
                );
                return (
                  <li key={user.id}>
                    <UserOptionRow
                      currentUserId={currentUserId}
                      currentUserLabel={labels.currentUser}
                      density={density}
                      onClick={() => onAddUser(user)}
                      selected={selected}
                      trailing={renderCandidateTrailing?.(user)}
                      user={user}
                    />
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
