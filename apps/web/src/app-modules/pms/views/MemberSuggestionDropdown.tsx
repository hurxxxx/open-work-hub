import { type ReactNode } from 'react';

import { UserOptionRow } from '@/src/platform/users/UserSearchMultiSelect';
import type { PmsUserSummary } from '../api/pms-api';

type MemberSuggestionDropdownProps = {
  candidates: PmsUserSummary[];
  currentUserId?: string | null;
  currentUserLabel?: string;
  isCandidateDisabled?: (user: PmsUserSummary) => boolean;
  noMatchingLabel: string;
  noUsersLabel: string;
  onSelect: (user: PmsUserSummary) => void;
  open: boolean;
  query: string;
  renderTrailing?: (user: PmsUserSummary) => ReactNode;
};

type MemberSuggestionItemViewModel = {
  candidate: PmsUserSummary;
  disabled: boolean;
};

type MemberSuggestionDropdownViewModel = {
  emptyLabel: string | null;
  suggestions: MemberSuggestionItemViewModel[];
};

function createMemberSuggestionDropdownViewModel({
  candidates,
  isCandidateDisabled,
  noMatchingLabel,
  noUsersLabel,
  query,
}: Pick<
  MemberSuggestionDropdownProps,
  | 'candidates'
  | 'isCandidateDisabled'
  | 'noMatchingLabel'
  | 'noUsersLabel'
  | 'query'
>): MemberSuggestionDropdownViewModel {
  if (candidates.length === 0) {
    return {
      emptyLabel: query.trim() ? noMatchingLabel : noUsersLabel,
      suggestions: [],
    };
  }

  return {
    emptyLabel: null,
    suggestions: candidates.map((candidate) => ({
      candidate,
      disabled: isCandidateDisabled?.(candidate) ?? false,
    })),
  };
}

export function MemberSuggestionDropdown({
  candidates,
  currentUserId,
  currentUserLabel,
  isCandidateDisabled,
  noMatchingLabel,
  noUsersLabel,
  onSelect,
  open,
  query,
  renderTrailing,
}: MemberSuggestionDropdownProps) {
  if (!open) return null;

  const viewModel = createMemberSuggestionDropdownViewModel({
    candidates,
    isCandidateDisabled,
    noMatchingLabel,
    noUsersLabel,
    query,
  });

  return (
    <div className="relative z-[10000] mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-app-border bg-app-surface shadow-lg">
      {viewModel.emptyLabel !== null ? (
        <div className="app-text-caption p-3 text-app-ink/40">
          {viewModel.emptyLabel}
        </div>
      ) : (
        <ul>
          {viewModel.suggestions.map(
            ({ candidate, disabled }) => (
              <li key={candidate.id}>
                <div
                  className={disabled ? 'pointer-events-none opacity-50' : ''}
                  onPointerDown={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    if (!disabled) onSelect(candidate);
                  }}
                >
                  <UserOptionRow
                    currentUserId={currentUserId}
                    currentUserLabel={currentUserLabel}
                    density="compact"
                    disabled={disabled}
                    onClick={() => {
                      if (!disabled) onSelect(candidate);
                    }}
                    trailing={renderTrailing?.(candidate)}
                    user={candidate}
                  />
                </div>
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  );
}
