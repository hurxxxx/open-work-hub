import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import type {
  AdminUsersResponse,
  OrgUnitItem,
  WorkspaceItem,
} from './admin-api';
import { ADMIN_PEOPLE_DEFAULT_PAGE_SIZE } from './admin-shared';
import {
  useAdminPeopleDirectoryController,
  type AdminPeopleDirectoryClient,
} from './useAdminPeopleDirectoryController';

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    login_id: 'ada',
    email: 'ada@example.test',
    full_name: 'Ada Lovelace',
    display_name: 'Ada',
    auth_provider: 'local',
    status: 'active',
    login_blocked: false,
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    date_format: 'korean',
    primary_org_unit: null,
    system_roles: [],
    workspaces: [],
    workspace_roles: [],
    must_change_password: false,
    last_login_at: null,
    created_at: '2026-05-30T00:00:00Z',
    ...overrides,
  } as AuthUser;
}

function orgUnit(id = 'org-1'): OrgUnitItem {
  return {
    id,
    name: `Org ${id}`,
    slug: id,
    parent_id: null,
    active: true,
    source_type: 'manual',
  } as OrgUnitItem;
}

function workspace(id = 'workspace-1'): WorkspaceItem {
  return {
    id,
    key: id,
    name: `Workspace ${id}`,
    description: '',
    active: true,
    member_count: 0,
  } as WorkspaceItem;
}

function usersResponse(
  overrides: Partial<AdminUsersResponse> = {},
): AdminUsersResponse {
  return {
    items: [user()],
    total: 1,
    page: 1,
    page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
    ...overrides,
  } as AdminUsersResponse;
}

function client(
  overrides: Partial<AdminPeopleDirectoryClient> = {},
): AdminPeopleDirectoryClient {
  return {
    listUsers: vi.fn().mockResolvedValue(usersResponse()),
    listOrgUnits: vi.fn().mockResolvedValue([orgUnit()]),
    listWorkspaces: vi.fn().mockResolvedValue([workspace()]),
    ...overrides,
  };
}

function renderController(testClient = client()) {
  const rendered = renderHook(() =>
    useAdminPeopleDirectoryController({
      token: 'token-1',
      debounceMs: 0,
      messages: {
        directoryLoadFailed: 'directory failed',
        userListLoadFailed: 'users failed',
      },
      client: testClient,
    }),
  );
  return { ...rendered, client: testClient };
}

describe('useAdminPeopleDirectoryController', () => {
  it('loads directory options and defaults the selected org unit', async () => {
    const testClient = client({
      listOrgUnits: vi.fn().mockResolvedValue([orgUnit('org-a'), orgUnit('org-b')]),
      listWorkspaces: vi.fn().mockResolvedValue([workspace('workspace-a')]),
    });
    const { result } = renderController(testClient);

    await waitFor(() => expect(result.current.state.orgUnits).toHaveLength(2));

    expect(testClient.listOrgUnits).toHaveBeenCalledWith('token-1', {
      includeInactive: false,
    });
    expect(testClient.listWorkspaces).toHaveBeenCalledWith('token-1');
    expect(result.current.state.selectedOrgUnitId).toBe('');
    expect(result.current.state.workspaces).toHaveLength(1);
  });

  it('filters users by selected org unit with optional descendants', async () => {
    const testClient = client();
    const { result } = renderController(testClient);

    await waitFor(() => expect(testClient.listUsers).toHaveBeenCalledTimes(1));
    vi.mocked(testClient.listUsers).mockClear();

    act(() => {
      result.current.actions.setSelectedOrgUnitId('org-a');
    });

    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenCalledWith('token-1', {
        page: 1,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: '',
        org_unit_id: 'org-a',
        include_descendants: true,
      });
    });
    vi.mocked(testClient.listUsers).mockClear();

    act(() => {
      result.current.actions.setIncludeDescendants(false);
    });

    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenCalledWith('token-1', {
        page: 1,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: '',
        org_unit_id: 'org-a',
        include_descendants: false,
      });
    });
  });

  it('reloads org units with inactive toggle and clears hidden selection', async () => {
    const activeOrg = orgUnit('org-active');
    const inactiveOrg = { ...orgUnit('org-inactive'), active: false };
    const testClient = client({
      listOrgUnits: vi
        .fn()
        .mockResolvedValueOnce([activeOrg])
        .mockResolvedValueOnce([activeOrg, inactiveOrg])
        .mockResolvedValueOnce([activeOrg]),
    });
    const { result } = renderController(testClient);

    await waitFor(() => expect(result.current.state.orgUnits).toHaveLength(1));

    act(() => {
      result.current.actions.setIncludeInactiveOrgUnits(true);
    });

    await waitFor(() => {
      expect(testClient.listOrgUnits).toHaveBeenLastCalledWith('token-1', {
        includeInactive: true,
      });
      expect(result.current.state.orgUnits).toHaveLength(2);
    });

    act(() => {
      result.current.actions.setSelectedOrgUnitId('org-inactive');
    });
    expect(result.current.state.selectedOrgUnitId).toBe('org-inactive');

    act(() => {
      result.current.actions.setIncludeInactiveOrgUnits(false);
    });

    await waitFor(() => {
      expect(testClient.listOrgUnits).toHaveBeenLastCalledWith('token-1', {
        includeInactive: false,
      });
      expect(result.current.state.orgUnits).toHaveLength(1);
      expect(result.current.state.selectedOrgUnitId).toBe('');
    });
  });

  it('debounces user list loading and sends page size, page, and query', async () => {
    const testClient = client();
    const { result } = renderController(testClient);

    await waitFor(() => expect(testClient.listUsers).toHaveBeenCalledTimes(1));
    vi.mocked(testClient.listUsers).mockClear();

    act(() => {
      result.current.actions.setPage(3);
    });
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenCalledWith('token-1', {
        page: 3,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: '',
      });
    });
    vi.mocked(testClient.listUsers).mockClear();

    act(() => {
      result.current.actions.searchChanged('ada');
    });

    expect(result.current.state.page).toBe(1);
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenCalledWith('token-1', {
        page: 1,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: 'ada',
      });
    });
  });

  it('resets to first page and reloads when page size changes', async () => {
    const testClient = client();
    const { result } = renderController(testClient);

    await waitFor(() => expect(testClient.listUsers).toHaveBeenCalledTimes(1));
    vi.mocked(testClient.listUsers).mockClear();

    act(() => {
      result.current.actions.setPage(3);
    });
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenCalledWith('token-1', {
        page: 3,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: '',
      });
    });
    vi.mocked(testClient.listUsers).mockClear();

    act(() => {
      result.current.actions.setPageSize(50);
    });

    expect(result.current.state.page).toBe(1);
    expect(result.current.state.pageSize).toBe(50);
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenCalledWith('token-1', {
        page: 1,
        page_size: 50,
        q: '',
      });
    });
  });

  it('reloads users with the latest search and applies the server page', async () => {
    const testClient = client({
      listUsers: vi.fn().mockResolvedValue(usersResponse({ page: 2, total: 21 })),
    });
    const { result } = renderController(testClient);

    await waitFor(() => expect(testClient.listUsers).toHaveBeenCalledTimes(1));
    act(() => {
      result.current.actions.searchChanged('roadmap');
    });
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenLastCalledWith('token-1', {
        page: 1,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: 'roadmap',
      });
    });

    await act(async () => {
      await result.current.actions.reloadUsers(2);
    });

    expect(testClient.listUsers).toHaveBeenLastCalledWith('token-1', {
      page: 2,
      page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
      q: 'roadmap',
    });
    expect(result.current.state.page).toBe(2);
    expect(result.current.state.totalUsers).toBe(21);
  });

  it('routes directory and user load failures to the controller error state', async () => {
    const testClient = client({
      listOrgUnits: vi.fn().mockRejectedValue('no orgs'),
      listUsers: vi.fn().mockRejectedValue('no users'),
    });
    const { result } = renderController(testClient);

    await waitFor(() => expect(result.current.state.error).toBe('users failed'));

    await act(async () => {
      await result.current.actions.reloadDirectoryOptions();
    });

    expect(result.current.state.error).toBe('directory failed');
    expect(result.current.state.isLoadingUsers).toBe(false);
  });
});
