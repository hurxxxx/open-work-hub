import { useCallback, useMemo } from 'react';

import {
  type RemoteUserSearchLoadContext,
  useRemoteUserSearchSession,
} from '@/src/platform/users/remote-user-search-session';
import type { DmUser } from '../api/dm-api';

type DmUserSearchState = {
  results: DmUser[];
  searching: boolean;
};

export type DmUserSearchLoader = (
  token: string,
  query: string,
  options?: { includeCurrent?: boolean },
) => Promise<DmUser[]>;

export type UseDmUserSearchOptions = {
  token: string | null | undefined;
  query: string;
  searchUsers: DmUserSearchLoader;
  includeCurrent?: boolean;
  debounceMs?: number;
  enabled?: boolean;
  excludeUserIds?: ReadonlySet<string>;
};

export type UseDmUserSearchResult = DmUserSearchState & {
  reset: () => void;
};

export function useDmUserSearch({
  token,
  query,
  searchUsers,
  includeCurrent = false,
  debounceMs = 250,
  enabled = true,
  excludeUserIds,
}: UseDmUserSearchOptions): UseDmUserSearchResult {
  const loadUsers = useCallback(
    ({
      query: trimmedQuery,
      token: sessionToken,
    }: RemoteUserSearchLoadContext) =>
      includeCurrent
        ? searchUsers(sessionToken, trimmedQuery, { includeCurrent: true })
        : searchUsers(sessionToken, trimmedQuery),
    [includeCurrent, searchUsers],
  );
  const searchSession = useRemoteUserSearchSession<DmUser>({
    debounceMs,
    enabled,
    query,
    searchUsers: loadUsers,
    token,
  });
  const results = useMemo(
    () =>
      excludeUserIds?.size
        ? searchSession.results.filter((item) => !excludeUserIds.has(item.id))
        : searchSession.results,
    [excludeUserIds, searchSession.results],
  );

  return {
    results,
    reset: searchSession.reset,
    searching: searchSession.searching,
  };
}
