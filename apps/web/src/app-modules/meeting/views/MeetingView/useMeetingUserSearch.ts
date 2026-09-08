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
}: UseMeetingUserSearchArgs) {
  const loadUsers = useCallback(
    ({
      query: trimmedQuery,
      token: sessionToken,
    }: RemoteUserSearchLoadContext) =>
      searchUsers(sessionToken, { q: trimmedQuery, limit: 30 }),
    [searchUsers],
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
