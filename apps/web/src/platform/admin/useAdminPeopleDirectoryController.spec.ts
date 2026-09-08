import { createAuthUser } from '../../../tests/fixtures/company';
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import type { AdminUsersResponse, OrganizationUnitItem } from './admin-api';
import { ADMIN_PEOPLE_DEFAULT_PAGE_SIZE } from './admin-shared';
import {
  useAdminPeopleDirectoryController,
  type AdminPeopleDirectoryClient,
} from './useAdminPeopleDirectoryController';

function user(): AuthUser {
  return createAuthUser({
    id: 'user-1',
    login_id: 'ada',
    email: 'ada@example.test',
    full_name: 'Ada Lovelace',
    display_name: 'Ada',
    status: 'active',
    login_blocked: false,
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    date_format: 'korean',
    system_roles: [],
    group_ids: [],
    managed_organization_unit_ids: [],
    must_change_password: false,
    last_login_at: null,
    created_at: '2026-05-30T00:00:00Z',
  });
}

function organizationUnit(): OrganizationUnitItem {
  return {
    id: 'organization-1',
    name: 'Research',
    slug: 'research',
    unit_type: 'department',
    parent_id: null,
    active: true,
    created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z',
  };
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
    listOrganizationUnits: vi.fn().mockResolvedValue([organizationUnit()]),
    ...overrides,
  };
}

function renderController(testClient = client()) {
  const rendered = renderHook(() =>
    useAdminPeopleDirectoryController({
      token: 'token-1',
      debounceMs: 0,
      messages: {
        organizationListLoadFailed: 'organizations failed',
        userListLoadFailed: 'users failed',
      },
      client: testClient,
    }),
  );
  return { ...rendered, client: testClient };
}

describe('useAdminPeopleDirectoryController', () => {
  it('loads users and organization units on mount', async () => {
    const testClient = client();
    const { result } = renderController(testClient);

    await waitFor(() => expect(result.current.state.users).toHaveLength(1));
    await waitFor(() =>
      expect(result.current.state.organizationUnits).toHaveLength(1),
    );

    expect(testClient.listUsers).toHaveBeenCalledWith('token-1', {
      page: 1,
      page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
      q: '',
    });
    expect(testClient.listOrganizationUnits).toHaveBeenCalledWith('token-1');
  });

  it('applies mutually exclusive organization and unassigned filters', async () => {
    const testClient = client();
    const { result } = renderController(testClient);
    await waitFor(() => expect(testClient.listUsers).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.actions.organizationUnitChanged('organization-1');
    });
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenLastCalledWith('token-1', {
        page: 1,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: '',
        organization_unit_id: 'organization-1',
        include_descendants: true,
      });
    });

    act(() => {
      result.current.actions.setUnassignedOnly(true);
    });
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenLastCalledWith('token-1', {
        page: 1,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: '',
        unassigned_only: true,
      });
    });
    expect(result.current.state.organizationUnitId).toBe('');
  });

  it('resets pagination when search or page size changes', async () => {
    const testClient = client();
    const { result } = renderController(testClient);
    await waitFor(() => expect(testClient.listUsers).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.actions.setPage(3);
    });
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenLastCalledWith('token-1', {
        page: 3,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: '',
      });
    });

    act(() => {
      result.current.actions.searchChanged('ada');
    });
    expect(result.current.state.page).toBe(1);
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenLastCalledWith('token-1', {
        page: 1,
        page_size: ADMIN_PEOPLE_DEFAULT_PAGE_SIZE,
        q: 'ada',
      });
    });

    act(() => {
      result.current.actions.setPageSize(50);
    });
    await waitFor(() => {
      expect(testClient.listUsers).toHaveBeenLastCalledWith('token-1', {
        page: 1,
        page_size: 50,
        q: 'ada',
      });
    });
  });

  it('reloads with the latest search and applies the server page', async () => {
    const testClient = client({
      listUsers: vi
        .fn()
        .mockResolvedValue(usersResponse({ page: 2, total: 21 })),
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
    expect(result.current.state.page).toBe(2);
    expect(result.current.state.totalUsers).toBe(21);
  });

  it('routes load failures to the controller error state', async () => {
    const testClient = client({
      listUsers: vi.fn().mockRejectedValue('no users'),
      listOrganizationUnits: vi.fn().mockRejectedValue('no organizations'),
    });
    const { result } = renderController(testClient);

    await waitFor(() => expect(result.current.state.error).not.toBeNull());
    expect(['users failed', 'organizations failed']).toContain(
      result.current.state.error,
    );
    expect(result.current.state.isLoadingUsers).toBe(false);
  });
});
