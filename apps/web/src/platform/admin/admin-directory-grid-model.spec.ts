import { createAuthUser } from '../../../tests/fixtures/company';
import { describe, expect, it } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';

import {
  buildPeopleDirectoryPagination,
  buildPeopleDirectoryUserRow,
  INITIAL_PEOPLE_DIRECTORY_GRID_STATE,
  peopleDirectoryGridReducer,
} from './admin-directory-grid-model';
import type { SubjectSelectionState } from './admin-shared-model';

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return createAuthUser({
    id: 'user-1',
    login_id: 'ada',
    email: 'ada@example.test',
    full_name: 'Ada Lovelace',
    display_name: '',
    status: 'active',
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    date_format: 'korean',
    system_roles: [],
    group_ids: [],
    managed_organization_unit_ids: [],
    must_change_password: false,
    last_login_at: null,
    created_at: undefined,
    ...overrides,
  });
}

describe('admin directory grid model', () => {
  it('applies search, page, and load transitions', () => {
    const searched = peopleDirectoryGridReducer(
      INITIAL_PEOPLE_DIRECTORY_GRID_STATE,
      { type: 'setSearch', search: '  ada  ' },
    );
    expect(searched).toMatchObject({
      search: '  ada  ',
      debouncedSearch: '',
      page: 1,
    });

    const paged = peopleDirectoryGridReducer(
      { ...searched, page: 3 },
      { type: 'commitSearch', search: 'ada' },
    );
    expect(paged).toMatchObject({ debouncedSearch: 'ada', page: 1 });

    const moved = peopleDirectoryGridReducer(paged, {
      type: 'setPage',
      page: 2,
    });
    expect(moved.page).toBe(2);

    const loading = peopleDirectoryGridReducer(moved, { type: 'loadStarted' });
    expect(loading.loading).toBe(true);

    const loadedUser = user({ id: 'loaded' });
    const loaded = peopleDirectoryGridReducer(loading, {
      type: 'loadLoaded',
      users: [loadedUser],
      total: 21,
    });
    expect(loaded).toMatchObject({
      users: [loadedUser],
      total: 21,
      loading: false,
    });

    expect(
      peopleDirectoryGridReducer(loaded, { type: 'loadFailed' }),
    ).toMatchObject({ users: [], total: 0, loading: false });
  });

  it('builds empty, middle, and final pagination states', () => {
    expect(
      buildPeopleDirectoryPagination({
        page: 1,
        total: 0,
        pageSize: 20,
        loading: false,
      }),
    ).toMatchObject({
      totalPages: 1,
      rangeText: '0',
      previousDisabled: true,
      nextDisabled: true,
    });

    expect(
      buildPeopleDirectoryPagination({
        page: 2,
        total: 55,
        pageSize: 20,
        loading: false,
      }),
    ).toMatchObject({
      totalPages: 3,
      rangeText: '21-40 / 55',
      previousDisabled: false,
      nextDisabled: false,
    });

    expect(
      buildPeopleDirectoryPagination({
        page: 3,
        total: 55,
        pageSize: 20,
        loading: false,
      }),
    ).toMatchObject({
      totalPages: 3,
      rangeText: '41-55 / 55',
      previousDisabled: false,
      nextDisabled: true,
    });

    expect(
      buildPeopleDirectoryPagination({
        page: 2,
        total: 55,
        pageSize: 20,
        loading: true,
      }),
    ).toMatchObject({
      previousDisabled: true,
      nextDisabled: true,
    });
  });

  it('projects excluded row state with selection subject and fallbacks', () => {
    const selectedSubject = {
      id: 'user-1',
      kind: 'user' as const,
      label: 'Ada Lovelace',
      secondary: 'ada@example.test',
    };
    const selection: SubjectSelectionState = {
      users: new Map([['user-1', selectedSubject]]),
    };

    const row = buildPeopleDirectoryUserRow({
      user: user({
        display_name: '',
        full_name: 'Ada Lovelace',
        status: 'suspended',
      }),
      selection,
      excludeIds: new Set(['user-1']),
      locale: 'en-US',
    });

    expect(row).toMatchObject({
      id: 'user-1',
      name: 'Ada Lovelace',
      email: 'ada@example.test',
      checkboxLabel: 'Ada Lovelace',
      checked: true,
      disabled: true,
      subject: selectedSubject,
      statusKind: 'excluded',
      lastLoginLabel: '-',
    });
  });

  it('formats last login dates in the requested user timezone', () => {
    const row = buildPeopleDirectoryUserRow({
      user: user({ last_login_at: '2026-05-01T18:30:00Z' }),
      selection: { users: new Map() },
      excludeIds: new Set(),
      locale: 'en-US',
      timeZone: 'Asia/Seoul',
    });

    expect(row.lastLoginLabel).toBe('05/02/2026');
  });
});
