import { createRef, useRef, useState, type ComponentProps } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { AppBarDesktopRail } from './AppBarDesktopRail';
import { launcherGridColumnCount } from './AppBarLauncherMenus';
import type { AppBarTranslator } from './app-bar-model';

const currentUser = {
  display_name: '허건우',
  full_name: '허건우',
  system_roles: [],
  workspaces: [],
} as AuthUser;

const translate: AppBarTranslator = (key, options) =>
  (
    ({
      'auth:settings.mySettings': '내 설정',
      'shell:appBar.favorites': '즐겨찾기',
      'shell:appBar.primaryNavigation': '주요 앱 탐색',
      'shell:appLauncher.openApp': '앱 열기',
      'shell:helpCenter.open': '도움말',
      'shell:launcher.title': '앱',
      'shell:notifications.title': '알림',
      'shell:search.title': '통합검색',
    }) as Record<string, string>
  )[key] ??
  (typeof options?.defaultValue === 'string' ? options.defaultValue : key);

const collaborationCategory = {
  id: 'collaboration',
  key: 'collaboration',
  title: '협업',
  icon_key: 'users',
  position: 0,
  items: [
    {
      app_id: 'docs',
      title: '문서',
      route_base: '/apps/docs',
      icon_key: 'file-text',
      enabled: true,
    },
  ],
};

function railProps(
  overrides: Partial<ComponentProps<typeof AppBarDesktopRail>> = {},
): ComponentProps<typeof AppBarDesktopRail> {
  return {
    activeAppId: 'docs',
    appBarEditorOpen: false,
    appBarItems: [],
    appBarLayoutError: null,
    appBarLayoutSaving: false,
    canOpenWorkspaceSearch: false,
    categoryMenuId: null,
    currentPathname: '/apps/docs/workspaces/general',
    currentUser,
    draftItems: [],
    draftPinnedAppIds: [],
    favoritesOpen: false,
    fixedItems: [],
    moreMenuRef: createRef(),
    notificationsEnabled: false,
    onCloseEditor: vi.fn(),
    onCloseLauncherMenus: vi.fn(),
    onMovePinnedApp: vi.fn(),
    onOpenAccount: vi.fn(),
    onOpenEditor: vi.fn(),
    onOpenHelp: vi.fn(),
    onOpenWorkspaceSearch: vi.fn(),
    onResetDraft: vi.fn(),
    onSaveLayout: vi.fn(),
    onToggleCategoryMenu: vi.fn(),
    onToggleFavorites: vi.fn(),
    onToggleNotifications: vi.fn(),
    onTogglePinnedApp: vi.fn(),
    pinnedEligibleAppIds: new Set(),
    pinnedItems: [],
    resolveAppLink: (appId) => `/apps/${appId}`,
    t: translate,
    unreadCount: 0,
    workspaceAppBarCategories: [collaborationCategory],
    ...overrides,
  };
}

describe('AppBarDesktopRail', () => {
  it('expands launcher grids as the app count grows', () => {
    expect(launcherGridColumnCount(0)).toBe(3);
    expect(launcherGridColumnCount(9)).toBe(3);
    expect(launcherGridColumnCount(10)).toBe(4);
    expect(launcherGridColumnCount(16)).toBe(4);
    expect(launcherGridColumnCount(17)).toBe(5);
  });

  it('renders display categories without a global workspace switcher', () => {
    render(
      <MemoryRouter>
        <AppBarDesktopRail {...railProps()} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('button', { name: '협업 / 문서' })).toBeTruthy();
    expect(
      screen.getByRole('navigation', { name: '주요 앱 탐색' }),
    ).toBeTruthy();
    expect(screen.queryByRole('button', { name: '워크스페이스' })).toBeNull();
  });

  it('opens executable leaf apps through app entry routes', () => {
    render(
      <MemoryRouter>
        <AppBarDesktopRail
          {...railProps({ categoryMenuId: 'collaboration' })}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('menuitem', { name: '앱 열기' }).getAttribute('href'),
    ).toBe('/apps/docs');
  });

  it('closes an open launcher menu with Escape and restores trigger focus', async () => {
    function KeyboardHarness() {
      const [categoryMenuId, setCategoryMenuId] = useState<string | null>(
        'collaboration',
      );
      const menuRef = useRef<HTMLDivElement>(null);
      return (
        <AppBarDesktopRail
          {...railProps({
            categoryMenuId,
            moreMenuRef: menuRef,
            onCloseLauncherMenus: () => setCategoryMenuId(null),
          })}
        />
      );
    }

    render(
      <MemoryRouter>
        <KeyboardHarness />
      </MemoryRouter>,
    );

    const trigger = screen.getByRole('button', { name: '협업 / 문서' });
    trigger.focus();
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => {
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
      expect(document.activeElement).toBe(trigger);
    });
  });
});
