import { useCallback, useEffect, useRef, useState } from 'react';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import {
  listAdminUsers,
  listOrganizationUnits,
  listWorkspaces,
  type AdminUsersQuery,
  type AdminUsersResponse,
  type OrganizationUnitItem,
  type WorkspaceItem,
} from './admin-api';
import {
  ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
  getErrorMessage,
} from './admin-shared';

export interface AdminPeopleDirectoryClient {
  listUsers(token: string, query: AdminUsersQuery): Promise<AdminUsersResponse>;
  listOrganizationUnits(token: string): Promise<OrganizationUnitItem[]>;
  listWorkspaces(token: string): Promise<WorkspaceItem[]>;
}

export interface AdminPeopleDirectoryMessages {
  workspaceListLoadFailed: string;
  organizationListLoadFailed: string;
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
    organizationUnitId: string;
    organizationUnits: OrganizationUnitItem[];
    includeDescendants: boolean;
    unassignedOnly: boolean;
    page: number;
    pageSize: number;
    search: string;
    totalUsers: number;
    users: AuthUser[];
    workspaces: WorkspaceItem[];
  };
  actions: {
    reloadUsers(nextPage: number): Promise<void>;
    organizationUnitChanged(organizationUnitId: string): void;
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
  organizationUnitId,
  includeDescendants,
  unassignedOnly,
}: {
  page: number;
  pageSize: number;
  search: string;
  organizationUnitId: string;
  includeDescendants: boolean;
  unassignedOnly: boolean;
}): AdminUsersQuery {
  return {
    page,
    page_size: pageSize,
    q: search,
    ...(unassignedOnly
      ? { unassigned_only: true }
      : organizationUnitId
        ? {
            organization_unit_id: organizationUnitId,
            include_descendants: includeDescendants,
          }
        : {}),
  };
}

export const adminPeopleDirectoryClient: AdminPeopleDirectoryClient = {
  listUsers: listAdminUsers,
  listOrganizationUnits: (token) =>
    listOrganizationUnits(token, { includeInactive: true }),
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
  const [organizationUnits, setOrganizationUnits] = useState<
    OrganizationUnitItem[]
  >([]);
  const [organizationUnitId, setOrganizationUnitId] = useState('');
  const [includeDescendants, setIncludeDescendants] = useState(true);
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const searchRef = useRef(search);
  searchRef.current = search;
  const organizationUnitIdRef = useRef(organizationUnitId);
  organizationUnitIdRef.current = organizationUnitId;
  const includeDescendantsRef = useRef(includeDescendants);
  includeDescendantsRef.current = includeDescendants;
  const unassignedOnlyRef = useRef(unassignedOnly);
  unassignedOnlyRef.current = unassignedOnly;

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

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const items = await client.listOrganizationUnits(token);
        if (!cancelled) setOrganizationUnits(items);
      } catch (caughtError) {
        if (!cancelled) {
          setError(
            getErrorMessage(caughtError, messages.organizationListLoadFailed),
          );
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [client, messages.organizationListLoadFailed, token]);

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
            organizationUnitId: organizationUnitIdRef.current,
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
              organizationUnitId,
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
    organizationUnitId,
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

  const organizationUnitChanged = useCallback((nextId: string) => {
    setOrganizationUnitId(nextId);
    if (nextId) setUnassignedOnly(false);
    setPage(1);
  }, []);

  const unassignedOnlyChanged = useCallback((nextValue: boolean) => {
    setUnassignedOnly(nextValue);
    if (nextValue) setOrganizationUnitId('');
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
      organizationUnitId,
      organizationUnits,
      includeDescendants,
      unassignedOnly,
      page,
      pageSize,
      search,
      totalUsers,
      users,
      workspaces,
    },
    actions: {
      reloadUsers,
      organizationUnitChanged,
      searchChanged,
      setIncludeDescendants: includeDescendantsChanged,
      setPage,
      setPageSize: pageSizeChanged,
      setUnassignedOnly: unassignedOnlyChanged,
    },
  };
}
