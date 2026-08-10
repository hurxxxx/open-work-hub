import { useCallback } from 'react';

import {
  type RemoteUserSearchLoadContext,
  useRemoteUserSearchSession,
} from '@/src/platform/users/remote-user-search-session';
import { listMeetingUsers, type MeetingUser } from '../../api/meeting-api';

const MEETING_USER_SEARCH_DEBOUNCE_MS = 100;

interface MeetingUserSearchHandlers {
  onIdle: () => void;
  onLoaded: (users: MeetingUser[]) => void;
  onFailed: () => void;
  onStarted: () => void;
}

interface UseMeetingUserSearchArgs extends MeetingUserSearchHandlers {
  focused: boolean;
  isOpen: boolean;
  query: string;
  searchUsers?: typeof listMeetingUsers;
  token: string | null | undefined;
  workspaceSlug: string;
}

export function useMeetingUserSearch({
  focused,
  isOpen,
  onFailed,
  onIdle,
  onLoaded,
  onStarted,
  query,
  searchUsers = listMeetingUsers,
  token,
  workspaceSlug,
}: UseMeetingUserSearchArgs) {
  const loadUsers = useCallback(
    ({
      query: trimmedQuery,
      token: sessionToken,
    }: RemoteUserSearchLoadContext) =>
      searchUsers(sessionToken, workspaceSlug, { q: trimmedQuery, limit: 30 }),
    [searchUsers, workspaceSlug],
  );

  useRemoteUserSearchSession<MeetingUser>({
    debounceMs: MEETING_USER_SEARCH_DEBOUNCE_MS,
    enabled: isOpen && focused,
    onFailed,
    onIdle,
    onLoaded,
    onStarted,
    query,
    searchUsers: loadUsers,
    token,
  });
}
