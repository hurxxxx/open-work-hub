import { useCallback, useEffect, useRef, useState } from 'react';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import {
  listAdminUsers,
  listHrGroups,
  type AdminUsersQuery,
  type AdminUsersResponse,
  type HrGroupItem,
} from './admin-api';
import {
  ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
  getErrorMessage,
} from './admin-shared';

export interface AdminPeopleDirectoryClient {
  listUsers(token: string, query: AdminUsersQuery): Promise<AdminUsersResponse>;
  listHrGroups(token: string): Promise<HrGroupItem[]>;
}

export interface AdminPeopleDirectoryMessages {
  hrGroupListLoadFailed: string;
  userListLoadFailed: string;
}

export interface AdminPeopleDirectoryControllerOptions {
  token: string;
  messages: AdminPeopleDirectoryMessages;
  client?: AdminPeopleDirectoryClient;
  debounceMs?: number;
}

export interface AdminPeopleDirectoryController {
  state: {
    error: string | null;
    isLoadingUsers: boolean;
    hrGroupId: string;
    hrGroups: HrGroupItem[];
    includeDescendants: boolean;
    unassignedOnly: boolean;
    page: number;
    pageSize: number;
    search: string;
    totalUsers: number;
    users: AuthUser[];
  };
  actions: {
    reloadUsers(nextPage: number): Promise<void>;
    hrGroupChanged(hrGroupId: string): void;
    setIncludeDescendants(includeDescendants: boolean): void;
    setUnassignedOnly(unassignedOnly: boolean): void;
    searchChanged(search: string): void;
    setPage(page: number | ((current: number) => number)): void;
    setPageSize(pageSize: number): void;
  };
}

function queryWithFilters({
  page,
  pageSize,
  search,
  hrGroupId,
  includeDescendants,
  unassignedOnly,
}: {
  page: number;
  pageSize: number;
  search: string;
  hrGroupId: string;
  includeDescendants: boolean;
  unassignedOnly: boolean;
}): AdminUsersQuery {
  return {
    page,
    page_size: pageSize,
    q: search,
    ...(unassignedOnly
      ? { unassigned_only: true }
      : hrGroupId
        ? {
            organization_unit_id: hrGroupId,
            include_descendants: includeDescendants,
          }
        : {}),
  };
}

export const adminPeopleDirectoryClient: AdminPeopleDirectoryClient = {
  listUsers: listAdminUsers,
  listHrGroups: (token) => listHrGroups(token, { includeInactive: true }),
};

export function useAdminPeopleDirectoryController({
  token,
  messages,
  client = adminPeopleDirectoryClient,
  debounceMs = 250,
}: AdminPeopleDirectoryControllerOptions): AdminPeopleDirectoryController {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(ADMIN_PEOPLE_DEFAULT_PAGE_SIZE);
  const [hrGroups, setHrGroups] = useState<HrGroupItem[]>([]);
  const [hrGroupId, setHrGroupId] = useState('');
  const [includeDescendants, setIncludeDescendants] = useState(true);
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const searchRef = useRef(search);
  searchRef.current = search;
  const hrGroupIdRef = useRef(hrGroupId);
  hrGroupIdRef.current = hrGroupId;
  const includeDescendantsRef = useRef(includeDescendants);
  includeDescendantsRef.current = includeDescendants;
  const unassignedOnlyRef = useRef(unassignedOnly);
  unassignedOnlyRef.current = unassignedOnly;

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const items = await client.listHrGroups(token);
        if (!cancelled) setHrGroups(items);
      } catch (caughtError) {
        if (!cancelled) {
          setError(
            getErrorMessage(caughtError, messages.hrGroupListLoadFailed),
          );
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [client, messages.hrGroupListLoadFailed, token]);

  const reloadUsers = useCallback(
    async (nextPage: number) => {
      setIsLoadingUsers(true);
      try {
        const userResponse = await client.listUsers(
          token,
          queryWithFilters({
            page: nextPage,
            pageSize,
            search: searchRef.current,
            hrGroupId: hrGroupIdRef.current,
            includeDescendants: includeDescendantsRef.current,
            unassignedOnly: unassignedOnlyRef.current,
          }),
        );
        setUsers(userResponse.items);
        setTotalUsers(userResponse.total);
        setPage(userResponse.page);
      } catch (caughtError) {
        setError(getErrorMessage(caughtError, messages.userListLoadFailed));
      } finally {
        setIsLoadingUsers(false);
      }
    },
    [client, messages.userListLoadFailed, pageSize, token],
  );

  useEffect(() => {
    let cancelled = false;
    const handle = window.setTimeout(() => {
      async function load() {
        setIsLoadingUsers(true);
        try {
          const userResponse = await client.listUsers(
            token,
            queryWithFilters({
              page,
              pageSize,
              search,
              hrGroupId,
              includeDescendants,
              unassignedOnly,
            }),
          );
          if (!cancelled) {
            setUsers(userResponse.items);
            setTotalUsers(userResponse.total);
          }
        } catch (caughtError) {
          if (!cancelled) {
            setError(getErrorMessage(caughtError, messages.userListLoadFailed));
          }
        } finally {
          if (!cancelled) {
            setIsLoadingUsers(false);
          }
        }
      }

      void load();
    }, debounceMs);

    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [
    client,
    debounceMs,
    messages.userListLoadFailed,
    hrGroupId,
    page,
    pageSize,
    search,
    token,
    includeDescendants,
    unassignedOnly,
  ]);

  const searchChanged = useCallback((nextSearch: string) => {
    setSearch(nextSearch);
    setPage(1);
  }, []);

  const pageSizeChanged = useCallback((nextPageSize: number) => {
    setPageSize(nextPageSize);
    setPage(1);
  }, []);

  const hrGroupChanged = useCallback((nextId: string) => {
    setHrGroupId(nextId);
    if (nextId) setUnassignedOnly(false);
    setPage(1);
  }, []);

  const unassignedOnlyChanged = useCallback((nextValue: boolean) => {
    setUnassignedOnly(nextValue);
    if (nextValue) setHrGroupId('');
    setPage(1);
  }, []);

  const includeDescendantsChanged = useCallback((nextValue: boolean) => {
    setIncludeDescendants(nextValue);
    setPage(1);
  }, []);

  return {
    state: {
      error,
      isLoadingUsers,
      hrGroupId,
      hrGroups,
      includeDescendants,
      unassignedOnly,
      page,
      pageSize,
      search,
      totalUsers,
      users,
    },
    actions: {
      reloadUsers,
      hrGroupChanged,
      searchChanged,
      setIncludeDescendants: includeDescendantsChanged,
      setPage,
      setPageSize: pageSizeChanged,
      setUnassignedOnly: unassignedOnlyChanged,
    },
  };
}
