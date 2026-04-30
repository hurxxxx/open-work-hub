import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { WorkspaceGate } from './gates';

let currentUser: AuthUser | null = null;

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    user: currentUser,
  }),
}));

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'user@aidoo.local',
    full_name: 'Aidoo User',
    display_name: 'Aidoo User',
    status: 'active',
    theme_preference: 'system',
    primary_org_unit: null,
    workspaces: [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'Aidoo HQ',
        role: 'admin',
      },
    ],
    workspace_roles: [],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
    must_change_password: false,
    ...overrides,
  };
}

function renderWorkspaceGate({
  appId = 'ai',
  bootstrapAppIds = ['home', 'ai'],
  path = '/w/hq/ai',
}: {
  appId?: string;
  bootstrapAppIds?: string[] | null;
  path?: string;
} = {}) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/w/:workspaceSlug/:appId"
          element={(
            <WorkspaceGate
              appId={appId}
              bootstrapAppIds={bootstrapAppIds}
              bootstrapError={null}
              bootstrapLoading={false}
            >
              <div>Workspace app rendered</div>
            </WorkspaceGate>
          )}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('WorkspaceGate', () => {
  it('renders enabled workspace apps for workspace members', () => {
    currentUser = buildUser();

    renderWorkspaceGate();

    expect(screen.getByText('Workspace app rendered')).toBeTruthy();
  });

  it('blocks apps disabled by workspace bootstrap', () => {
    currentUser = buildUser();

    renderWorkspaceGate({ bootstrapAppIds: ['home', 'pms', 'docs'] });

    expect(screen.queryByText('Workspace app rendered')).toBeNull();
    expect(screen.getByText('접근 권한 없음')).toBeTruthy();
    expect(
      screen.getByText('현재 workspace에서는 이 앱이 활성화되어 있지 않습니다.'),
    ).toBeTruthy();
  });

  it('blocks users outside the requested workspace', () => {
    currentUser = buildUser({ workspaces: [] });

    renderWorkspaceGate();

    expect(screen.queryByText('Workspace app rendered')).toBeNull();
    expect(
      screen.getByText('현재 계정은 이 workspace에서 해당 앱을 사용할 수 없습니다.'),
    ).toBeTruthy();
  });
});
