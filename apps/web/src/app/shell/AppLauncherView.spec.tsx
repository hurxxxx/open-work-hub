import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import type { AppsBootstrapResponse } from '@/src/platform/workspaces/workspaces-api';
import { AppLauncherView } from './AppLauncherView';

const authState = vi.hoisted(() => ({ user: null as AuthUser | null }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      [key, ...Object.values(options ?? {})].join(' '),
  }),
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
      screen.getByRole('link', { name: /apps\.planner/ }).getAttribute('href'),
    ).toBe('/apps/planner');
    expect(
      screen
        .getByRole('link', { name: 'launcher.manageWorkspaces' })
        .getAttribute('href'),
    ).toBe('/admin/workspaces');
  });

  it('groups apps by execution scope and previews workspace destinations', () => {
    authState.user = user({
      workspaces: [
        {
          id: 'workspace-general',
          name: 'General',
          role: 'member',
          slug: 'general',
        },
      ],
    });
    render(
      <MemoryRouter>
        <AppLauncherView
          data={bootstrap([
            {
              app_id: 'docs',
              availability_scope: 'workspace',
              coming_soon: false,
              eligible_workspace_count: 2,
              entry_route_id: 'docs.root',
              execution_context_kind: 'workspace',
              icon_key: 'copy',
              preferred_workspace: {
                id: 'workspace-general',
                name: 'General',
                slug: 'general',
              },
              resource_scope: 'workspace',
              route_base: '/apps/docs',
              single_eligible_workspace: null,
              title: 'Docs',
            },
            {
              app_id: 'community',
              availability_scope: 'platform',
              coming_soon: false,
              eligible_workspace_count: 0,
              entry_route_id: 'community.root',
              execution_context_kind: 'company',
              icon_key: 'users',
              preferred_workspace: null,
              resource_scope: 'company',
              route_base: '/apps/community',
              single_eligible_workspace: null,
              title: 'Community',
            },
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
      screen.getByRole('heading', { name: 'launcher.workspaceApp' }),
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', { name: 'launcher.companyApp' }),
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', { name: 'launcher.personalApp' }),
    ).toBeTruthy();
    expect(
      screen.getByText(/shell:launcher\.opensInWorkspace General/),
    ).toBeTruthy();
    expect(screen.getByText('shell:launcher.companyScope')).toBeTruthy();
    expect(screen.getByText('shell:launcher.personalScope')).toBeTruthy();
    expect(
      screen.getByRole('link', { name: /apps\.docs/ }).getAttribute('href'),
    ).toBe('/apps/docs');
  });
});
