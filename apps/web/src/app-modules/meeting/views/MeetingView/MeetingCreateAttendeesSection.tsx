import { UserSearchMultiSelect } from '@/src/platform/users/UserSearchMultiSelect';
import type { UserOptionLike } from '@/src/platform/users/user-option-picker-model';
import type { MeetingAttendeeInput, MeetingUser } from '../../api/meeting-api';

type AttendeesLabels = {
  attendees: string;
  autoIncluded: string;
  noUserMatch: string;
  removeItem: (name: string) => string;
  searchPlaceholder: string;
  searchPrompt: string;
  searching: string;
};

type AttendeesState = {
  filteredUsers: MeetingUser[];
  lockedLabel?: string;
  lockedUserIds?: Set<string>;
  userLookup: Map<string, MeetingUser>;
  userQuery: string;
  userQueryFocused: boolean;
  usersLoading: boolean;
  visibleAttendees: MeetingAttendeeInput[];
};

type AttendeesHandlers = {
  onAddAttendee: (user: MeetingUser) => void;
  onQueryChange: (query: string) => void;
  onQueryFocusChange: (focused: boolean) => void;
  onRemoveAttendee: (userId: string) => void;
};

type MeetingCreateAttendeesSectionProps = {
  handlers: AttendeesHandlers;
  labels: AttendeesLabels;
  state: AttendeesState;
};

export function MeetingCreateAttendeesSection({
  handlers,
  labels,
  state,
}: MeetingCreateAttendeesSectionProps) {
  const selectedUsers = state.visibleAttendees.map((attendee): UserOptionLike => {
    const user = state.userLookup.get(attendee.user_id);
    return {
      id: attendee.user_id,
      email: user?.email ?? '',
      full_name: user?.full_name ?? attendee.user_id,
      primary_org_unit_name: user?.primary_org_unit_name ?? null,
    };
  });

  return (
    <div className="space-y-2">
      <label className="app-text-control-sm text-app-ink/70">
        {labels.attendees}
      </label>
      {labels.autoIncluded ? (
        <p className="app-text-caption text-app-ink/40">
          {labels.autoIncluded}
        </p>
      ) : null}
      <UserSearchMultiSelect
        candidates={state.filteredUsers}
        labels={{
          lockedLabel: state.lockedLabel,
          noUserMatch: labels.noUserMatch,
          removeItem: labels.removeItem,
          searchPlaceholder: labels.searchPlaceholder,
          searchPrompt: labels.searchPrompt,
          searching: labels.searching,
        }}
        loading={state.usersLoading}
        lockedUserIds={state.lockedUserIds}
        onAddUser={handlers.onAddAttendee}
        onQueryChange={handlers.onQueryChange}
        onQueryFocusChange={handlers.onQueryFocusChange}
        onRemoveUser={handlers.onRemoveAttendee}
        query={state.userQuery}
        queryFocused={state.userQueryFocused}
        selectedUsers={selectedUsers}
      />
    </div>
  );
}
