import { useCallback, useEffect, useRef, useState } from 'react';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import {
  listAdminUsers,
  listOrgUnits,
  listWorkspaces,
  type AdminUsersQuery,
  type AdminUsersResponse,
  type OrgUnitItem,
  type WorkspaceItem,
} from './admin-api';
import {
  ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
  getErrorMessage,
} from './admin-shared';

export interface AdminPeopleDirectoryClient {
  listUsers(token: string, query: AdminUsersQuery): Promise<AdminUsersResponse>;
  listOrgUnits(
    token: string,
    options?: { includeInactive?: boolean },
  ): Promise<OrgUnitItem[]>;
  listWorkspaces(token: string): Promise<WorkspaceItem[]>;
}

export interface AdminPeopleDirectoryMessages {
  directoryLoadFailed: string;
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
    orgUnits: OrgUnitItem[];
    page: number;
    pageSize: number;
    search: string;
    includeDescendants: boolean;
    includeInactiveOrgUnits: boolean;
    selectedOrgUnitId: string;
    totalUsers: number;
    users: AuthUser[];
    workspaces: WorkspaceItem[];
  };
  actions: {
    reloadDirectoryOptions(): Promise<void>;
    reloadUsers(nextPage: number): Promise<void>;
    searchChanged(search: string): void;
    setError(error: string | null): void;
    setIncludeDescendants(includeDescendants: boolean): void;
    setIncludeInactiveOrgUnits(includeInactiveOrgUnits: boolean): void;
    setPage(page: number | ((current: number) => number)): void;
    setPageSize(pageSize: number): void;
    setSelectedOrgUnitId(orgUnitId: string): void;
  };
}

export const adminPeopleDirectoryClient: AdminPeopleDirectoryClient = {
  listUsers: listAdminUsers,
  listOrgUnits,
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
  const [orgUnits, setOrgUnits] = useState<OrgUnitItem[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [search, setSearch] = useState('');
  const [includeDescendants, setIncludeDescendants] = useState(true);
  const [includeInactiveOrgUnits, setIncludeInactiveOrgUnits] = useState(false);
  const [selectedOrgUnitId, setSelectedOrgUnitId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const searchRef = useRef(search);
  searchRef.current = search;

  const applyDirectoryOptions = useCallback(
    ({
      orgUnitItems,
      workspaceItems,
    }: {
      orgUnitItems: OrgUnitItem[];
      workspaceItems: WorkspaceItem[];
    }) => {
      setOrgUnits(orgUnitItems);
      setSelectedOrgUnitId((current) => {
        if (!current) return current;
        if (orgUnitItems.some((item) => item.id === current)) return current;
        return '';
      });
      setWorkspaces(workspaceItems);
    },
    [],
  );

  const reloadDirectoryOptions = useCallback(async () => {
    try {
      const [orgUnitItems, workspaceItems] = await Promise.all([
        client.listOrgUnits(token, {
          includeInactive: includeInactiveOrgUnits,
        }),
        client.listWorkspaces(token),
      ]);
      applyDirectoryOptions({ orgUnitItems, workspaceItems });
    } catch (caughtError) {
      setError(getErrorMessage(caughtError, messages.directoryLoadFailed));
    }
  }, [
    applyDirectoryOptions,
    client,
    includeInactiveOrgUnits,
    messages.directoryLoadFailed,
    token,
  ]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [orgUnitItems, workspaceItems] = await Promise.all([
          client.listOrgUnits(token, {
            includeInactive: includeInactiveOrgUnits,
          }),
          client.listWorkspaces(token),
        ]);
        if (!cancelled) {
          applyDirectoryOptions({ orgUnitItems, workspaceItems });
        }
      } catch (caughtError) {
        if (!cancelled) {
          setError(getErrorMessage(caughtError, messages.directoryLoadFailed));
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [
    applyDirectoryOptions,
    client,
    includeInactiveOrgUnits,
    messages.directoryLoadFailed,
    token,
  ]);

  const reloadUsers = useCallback(
    async (nextPage: number) => {
      setIsLoadingUsers(true);
      try {
        const userResponse = await client.listUsers(token, {
          page: nextPage,
          page_size: pageSize,
          q: searchRef.current,
          ...(selectedOrgUnitId
            ? {
                org_unit_id: selectedOrgUnitId,
                include_descendants: includeDescendants,
              }
            : {}),
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
    [
      client,
      includeDescendants,
      messages.userListLoadFailed,
      pageSize,
      selectedOrgUnitId,
      token,
    ],
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
            ...(selectedOrgUnitId
              ? {
                  org_unit_id: selectedOrgUnitId,
                  include_descendants: includeDescendants,
                }
              : {}),
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
    includeDescendants,
    messages.userListLoadFailed,
    page,
    pageSize,
    search,
    selectedOrgUnitId,
    token,
  ]);

  const searchChanged = useCallback((nextSearch: string) => {
    setSearch(nextSearch);
    setPage(1);
  }, []);

  const orgUnitChanged = useCallback((orgUnitId: string) => {
    setSelectedOrgUnitId(orgUnitId);
    setPage(1);
  }, []);

  const includeDescendantsChanged = useCallback((nextInclude: boolean) => {
    setIncludeDescendants(nextInclude);
    setPage(1);
  }, []);

  const includeInactiveOrgUnitsChanged = useCallback((nextInclude: boolean) => {
    setIncludeInactiveOrgUnits(nextInclude);
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
      orgUnits,
      page,
      pageSize,
      search,
      includeDescendants,
      includeInactiveOrgUnits,
      selectedOrgUnitId,
      totalUsers,
      users,
      workspaces,
    },
    actions: {
      reloadDirectoryOptions,
      reloadUsers,
      searchChanged,
      setError,
      setIncludeDescendants: includeDescendantsChanged,
      setIncludeInactiveOrgUnits: includeInactiveOrgUnitsChanged,
      setPage,
      setPageSize: pageSizeChanged,
      setSelectedOrgUnitId: orgUnitChanged,
    },
  };
}
