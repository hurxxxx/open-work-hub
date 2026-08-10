import { useEffect, useMemo, useState } from 'react';
import { Users } from 'lucide-react';

import {
  UserOptionAvatar,
  UserSearchMultiSelect,
} from '@/src/platform/users/UserSearchMultiSelect';
import { selectUserOptionsForPicker } from '@/src/platform/users/user-option-picker-model';
import type { PmsTaskListMember } from '../api/pms-api';

type UserRolePickerOption = {
  id: string;
  email: string;
  full_name: string;
};

export function UserRolePicker({
  canEdit,
  currentUserId,
  currentUserLabel,
  emptyLabel,
  isOpen,
  label,
  members,
  noMatchesLabel,
  noMembersLabel,
  onOpenChange,
  onToggle,
  removeItemLabel,
  searchPlaceholder,
  selectedIds,
  selectedNames,
}: {
  canEdit: boolean;
  currentUserId?: string | null;
  currentUserLabel?: string;
  emptyLabel: string;
  isOpen: boolean;
  label: string;
  members: PmsTaskListMember[];
  noMatchesLabel: string;
  noMembersLabel: string;
  onOpenChange: (open: boolean) => void;
  onToggle: (userId: string) => void;
  removeItemLabel: (name: string) => string;
  searchPlaceholder: string;
  selectedIds: string[];
  selectedNames: string[];
}) {
  const [query, setQuery] = useState('');
  const [queryFocused, setQueryFocused] = useState(false);
  const memberOptions = useMemo<UserRolePickerOption[]>(
    () =>
      members.map((member) => ({
        id: member.user_id,
        email: member.email,
        full_name: member.full_name,
      })),
    [members],
  );
  const memberOptionsById = useMemo(
    () => new Map(memberOptions.map((member) => [member.id, member])),
    [memberOptions],
  );
  const selectedUsers = useMemo(
    () =>
      selectedIds.map(
        (userId, index) =>
          memberOptionsById.get(userId) ?? {
            id: userId,
            email: '',
            full_name: selectedNames[index] ?? userId,
          },
      ),
    [memberOptionsById, selectedIds, selectedNames],
  );
  const candidateUsers = useMemo(
    () =>
      selectUserOptionsForPicker({
        users: memberOptions,
        query,
        currentUserId,
        excludeIds: new Set(selectedIds),
        limit: 8,
      }),
    [currentUserId, memberOptions, query, selectedIds],
  );

  useEffect(() => {
    if (isOpen) {
      setQueryFocused(true);
      return;
    }

    setQuery('');
    setQueryFocused(false);
  }, [isOpen]);

  return (
    <div className="relative min-w-0">
      <button
        type="button"
        aria-expanded={canEdit ? isOpen : undefined}
        aria-haspopup="menu"
        aria-label={label}
        onClick={() => {
          if (canEdit) onOpenChange(!isOpen);
        }}
        className={`flex min-h-[32px] w-full min-w-0 flex-wrap items-center gap-1 rounded-md border border-app-border px-2 py-1 text-left transition-colors ${
          canEdit
            ? 'hover:border-app-ink/30 hover:bg-app-surface-hover/50'
            : 'cursor-default opacity-80'
        }`}
        disabled={!canEdit}
      >
        {selectedIds.length > 0 ? (
          selectedUsers.map((selectedUser, index) => (
            <span
              key={selectedUser.id}
              className="app-text-caption inline-flex max-w-full items-center gap-1 rounded-full bg-app-surface-hover px-2 py-0.5 text-app-ink"
            >
              <UserOptionAvatar
                className="text-[7px]"
                sizeClassName="size-4"
                user={selectedUser}
              />
              <span className="truncate">
                {selectedNames[index] ?? selectedUser.full_name}
              </span>
            </span>
          ))
        ) : (
          <span className="app-text-body flex min-w-0 items-center gap-1 text-app-ink/40">
            <Users size={12} className="shrink-0" />
            <span className="truncate">{emptyLabel}</span>
          </span>
        )}
      </button>
      {isOpen && canEdit && (
        <>
          <button
            type="button"
            aria-label={label}
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => onOpenChange(false)}
          />
          <div
            role="dialog"
            aria-label={label}
            className="absolute left-0 top-9 z-20 w-80 max-w-[min(20rem,calc(100vw-2rem))] rounded-lg border border-app-border bg-app-bg p-2 shadow-xl"
          >
            <UserSearchMultiSelect
              autoFocus
              candidates={candidateUsers}
              density="compact"
              labels={{
                currentUser: currentUserLabel,
                noUserMatch: noMatchesLabel,
                removeItem: removeItemLabel,
                searchPlaceholder,
                searchPrompt: noMembersLabel,
                searching: searchPlaceholder,
              }}
              currentUserId={currentUserId}
              onAddUser={(user) => onToggle(user.id)}
              onQueryChange={setQuery}
              onQueryFocusChange={setQueryFocused}
              onRemoveUser={onToggle}
              query={query}
              queryFocused={queryFocused}
              selectedUsers={selectedUsers}
            />
          </div>
        </>
      )}
    </div>
  );
}
