import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { AppBar } from './AppBar';
import type { AuthUser } from '@/src/domains/auth/auth-api';

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@aidoo.local',
    full_name: 'AIDOO Member',
    display_name: 'AIDOO Member',
    status: 'active',
    theme_preference: 'system',
    primary_org_unit: null,
    workspace_roles: [],
    group_ids: [],
    group_slugs: [],
    permissions: [],
    visible_features: ['nav.ai', 'nav.docs', 'nav.pms', 'nav.planner'],
    must_change_password: false,
    is_admin: false,
    last_login_at: null,
    created_at: '2026-04-08T00:00:00Z',
    ...overrides,
  };
}

describe('AppBar', () => {
  it('shows the settings app for users with admin section permissions and links to the first allowed section', () => {
    const onOpenAccount = vi.fn();

    render(
      <MemoryRouter>
        <AppBar
          activeAppId="settings"
          currentUser={buildUser({
            permissions: ['group.read'],
            visible_features: [],
          })}
          onOpenAccount={onOpenAccount}
        />
      </MemoryRouter>,
    );

    const settingsLink = screen.getByText('Settings').closest('a');
    expect(settingsLink).toBeTruthy();
    expect(settingsLink?.getAttribute('href')).toBe('/admin/security');
  });
});
