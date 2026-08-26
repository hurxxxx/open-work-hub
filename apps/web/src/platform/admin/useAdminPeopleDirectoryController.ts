import { useCallback, useEffect, useRef, useState } from 'react';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import {
  listAdminUsers,
  listWorkspaces,
  type AdminUsersQuery,
  type AdminUsersResponse,
  type WorkspaceItem,
} from './admin-api';
import {
  ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
  getErrorMessage,
} from './admin-shared';

export interface AdminPeopleDirectoryClient {
  listUsers(token: string, query: AdminUsersQuery): Promise<AdminUsersResponse>;
  listWorkspaces(token: string): Promise<WorkspaceItem[]>;
}

export interface AdminPeopleDirectoryMessages {
  workspaceListLoadFailed: string;
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
    page: number;
    pageSize: number;
    search: string;
    totalUsers: number;
    users: AuthUser[];
    workspaces: WorkspaceItem[];
  };
  actions: {
    reloadUsers(nextPage: number): Promise<void>;
    searchChanged(search: string): void;
    setPage(page: number | ((current: number) => number)): void;
    setPageSize(pageSize: number): void;
  };
}

export const adminPeopleDirectoryClient: AdminPeopleDirectoryClient = {
  listUsers: listAdminUsers,
  listWorkspaces,
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
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const searchRef = useRef(search);
  searchRef.current = search;

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const workspaceItems = await client.listWorkspaces(token);
        if (!cancelled) {
          setWorkspaces(workspaceItems);
        }
      } catch (caughtError) {
        if (!cancelled) {
          setError(
            getErrorMessage(caughtError, messages.workspaceListLoadFailed),
          );
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [client, messages.workspaceListLoadFailed, token]);

  const reloadUsers = useCallback(
    async (nextPage: number) => {
      setIsLoadingUsers(true);
      try {
        const userResponse = await client.listUsers(token, {
          page: nextPage,
          page_size: pageSize,
          q: searchRef.current,
        });
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
          const userResponse = await client.listUsers(token, {
            page,
            page_size: pageSize,
            q: search,
          });
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
    page,
    pageSize,
    search,
    token,
  ]);

  const searchChanged = useCallback((nextSearch: string) => {
    setSearch(nextSearch);
    setPage(1);
  }, []);

  const pageSizeChanged = useCallback((nextPageSize: number) => {
    setPageSize(nextPageSize);
    setPage(1);
  }, []);

  return {
    state: {
      error,
      isLoadingUsers,
      page,
      pageSize,
      search,
      totalUsers,
      users,
      workspaces,
    },
    actions: {
      reloadUsers,
      searchChanged,
      setPage,
      setPageSize: pageSizeChanged,
    },
  };
}
