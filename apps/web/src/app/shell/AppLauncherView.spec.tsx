import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import type { AppsBootstrapResponse } from '@/src/platform/workspaces/workspaces-api';
import { AppLauncherView } from './AppLauncherView';

const authState = vi.hoisted(() => ({ user: null as AuthUser | null }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ user: authState.user }),
}));

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    date_format: 'korean',
    display_name: 'Member',
    email: 'member@example.com',
    full_name: 'Member',
    id: 'user-1',
    locale: 'ko-KR',
    login_id: 'member',
    must_change_password: false,
    status: 'active',
    system_roles: [],
    theme_preference: 'system',
    time_zone: 'Asia/Seoul',
    workspaces: [],
    ...overrides,
  } as AuthUser;
}

function bootstrap(
  apps: AppsBootstrapResponse['apps'] = [],
): AppsBootstrapResponse {
  return {
    app_bar_categories: [],
    apps,
    global_route_app_ids: apps.map((app) => app.app_id),
    personal_tool_app_ids: apps.map((app) => app.app_id),
    principal: {
      kind: 'user',
      scope: 'personal',
      source: 'test',
      user_id: 'user-1',
      workspace_id: null,
    },
  };
}

beforeEach(() => {
  authState.user = user();
});

describe('AppLauncherView without workspace membership', () => {
  it('explains both the membership state and an empty company catalog', () => {
    render(
      <MemoryRouter>
        <AppLauncherView data={bootstrap()} error={null} loading={false} />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { name: 'launcher.noWorkspaceTitle' }),
    ).toBeTruthy();
    expect(screen.getByText('launcher.noWorkspaceDescription')).toBeTruthy();
    expect(
      screen.getByRole('heading', { name: 'launcher.noAppsTitle' }),
    ).toBeTruthy();
    expect(
      screen.queryByRole('link', { name: 'launcher.manageWorkspaces' }),
    ).toBeNull();
  });

  it('keeps platform apps available and gives a zero-workspace admin a setup path', () => {
    authState.user = user({ system_roles: ['platform_admin'] });
    render(
      <MemoryRouter>
        <AppLauncherView
          data={bootstrap([
            {
              app_id: 'planner',
              availability_scope: 'platform',
              coming_soon: false,
              eligible_workspace_count: 0,
              entry_route_id: 'planner.root',
              execution_context_kind: 'personal',
              icon_key: 'calendar',
              preferred_workspace: null,
              resource_scope: 'personal',
              route_base: '/apps/planner',
              single_eligible_workspace: null,
              title: 'Planner',
            },
          ])}
          error={null}
          loading={false}
        />
      </MemoryRouter>,
    );

    expect(
      screen
        .getByRole('link', { name: /apps\.planner/ })
        .getAttribute('href'),
    ).toBe('/apps/planner');
    expect(
      screen
        .getByRole('link', { name: 'launcher.manageWorkspaces' })
        .getAttribute('href'),
    ).toBe('/admin/workspaces');
  });
});
