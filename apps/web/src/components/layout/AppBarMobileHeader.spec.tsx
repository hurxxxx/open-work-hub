import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { AppBarMobileHeader } from './AppBarMobileHeader';

describe('AppBarMobileHeader', () => {
  it('exposes the mobile app bar as named primary navigation', () => {
    render(
      <AppBarMobileHeader
        activeContextLabel="Personal scope"
        activeAppTitle="Planner"
        canOpenWorkspaceSearch={false}
        currentUser={
          {
            display_name: 'Member',
            full_name: 'Workspace Member',
          } as AuthUser
        }
        labels={{
          accountTitle: 'Account',
          mobileMenuTitle: 'App menu',
          mobileNavigationOpen: 'Open navigation',
          notificationsTitle: 'Notifications',
          primaryNavigation: 'Primary apps',
          searchOpen: 'Open search',
          searchTitle: 'Search',
        }}
        notificationPanelOpen={false}
        notificationsEnabled={false}
        onOpenAccount={vi.fn()}
        onOpenMobileNavigation={vi.fn()}
        onOpenWorkspaceSearch={vi.fn()}
        onToggleNotifications={vi.fn()}
        unreadCount={0}
      />,
    );

    expect(
      screen.getByRole('navigation', { name: 'Primary apps' }),
    ).toBeTruthy();
    expect(screen.getByText('Personal scope')).toBeTruthy();
  });
});
