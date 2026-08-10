import { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { AppBarDesktopRail } from './AppBarDesktopRail';
import { launcherGridColumnCount } from './AppBarLauncherMenus';
import type { AppBarTranslator } from './app-bar-model';

const workspace: AuthUser['workspaces'][number] = {
  id: 'workspace-1',
  name: 'General Workspace',
  role: 'member',
  slug: 'general',
};

const currentUser = {
  app_bar_layout: null,
  default_workspace_id: null,
  display_name: '허건우',
  full_name: '허건우',
  system_roles: [],
  workspaces: [workspace],
} as AuthUser;

const resolveAppLink = (appId: string) => `/w/${workspace.slug}/${appId}`;

const translate: AppBarTranslator = (key, options) =>
  (
    ({
      'auth:settings.mySettings': '내 설정',
      'common:labels.workspaces': '워크스페이스',
      'shell:appBar.favorites': '즐겨찾기',
      'shell:appLauncher.openApp': '앱 열기',
      'shell:helpCenter.open': '도움말',
      'shell:notifications.title': '알림',
      'shell:search.title': '통합검색',
      'shell:workspaceSwitcher.currentTitle': 'General Workspace 워크스페이스',
      'shell:workspaceSwitcher.switch': '워크스페이스 전환',
    }) as Record<string, string>
  )[key] ??
  (typeof options?.defaultValue === 'string' ? options.defaultValue : key);

describe('AppBarDesktopRail', () => {
  it('expands launcher grids as the app count grows', () => {
    expect(launcherGridColumnCount(0)).toBe(3);
    expect(launcherGridColumnCount(9)).toBe(3);
    expect(launcherGridColumnCount(10)).toBe(4);
    expect(launcherGridColumnCount(16)).toBe(4);
    expect(launcherGridColumnCount(17)).toBe(5);
  });

  it('renders the workspace switcher popover outside the rail clipping context', () => {
    render(
      <AppBarDesktopRail
        activeAppId="home"
        appBarEditorOpen={false}
        appBarItems={[]}
        appBarLayoutError={null}
        appBarLayoutSaving={false}
        canCreateWorkspace={false}
        canManageCurrentWorkspace={false}
        canOpenWorkspaceSearch={false}
        currentPathname="/"
        currentUser={currentUser}
        currentWorkspace={workspace}
        currentWorkspaceName={workspace.name}
        defaultWorkspaceOptions={[workspace]}
        defaultWorkspaceSaving={false}
        draftItems={[]}
        draftPinnedAppIds={[]}
        fixedItems={[]}
        categoryMenuId={null}
        favoritesOpen={false}
        moreMenuRef={createRef()}
        normalizedDefaultWorkspaceId={null}
        notificationsEnabled={false}
        onCloseEditor={vi.fn()}
        onCloseLauncherMenus={vi.fn()}
        onCreateWorkspace={vi.fn()}
        onDefaultWorkspaceChange={vi.fn()}
        onManageCurrentWorkspace={vi.fn()}
        onMovePinnedApp={vi.fn()}
        onOpenAccount={vi.fn()}
        onOpenEditor={vi.fn()}
        onOpenHelp={vi.fn()}
        onOpenWorkspaceSearch={vi.fn()}
        onResetDraft={vi.fn()}
        onSaveLayout={vi.fn()}
        onSearchQueryChange={vi.fn()}
        onSelectWorkspace={vi.fn()}
        onToggleCategoryMenu={vi.fn()}
        onToggleFavorites={vi.fn()}
        onToggleNotifications={vi.fn()}
        onTogglePinnedApp={vi.fn()}
        onToggleWorkspaceSwitcher={vi.fn()}
        otherWorkspaces={[]}
        pinnedEligibleAppIds={new Set()}
        pinnedItems={[]}
        pinnedWorkspace={workspace}
        resolveAppLink={resolveAppLink}
        t={translate}
        unreadCount={0}
        workspaceAppBarCategories={[]}
        workspacePreferenceError={null}
        workspaceQuery=""
        workspaceSwitcherOpen
        workspaceSwitcherRef={createRef()}
      />,
    );

    const workspaceDialog = screen.getByRole('dialog', {
      name: '워크스페이스',
    });
    expect(workspaceDialog.className).toContain('fixed');
    expect(workspaceDialog.className).not.toContain('absolute');
  });

  it('uses the active app as its category launcher icon', () => {
    render(
      <MemoryRouter>
        <AppBarDesktopRail
          activeAppId="docs"
          appBarEditorOpen={false}
          appBarItems={[]}
          appBarLayoutError={null}
          appBarLayoutSaving={false}
          canCreateWorkspace={false}
          canManageCurrentWorkspace={false}
          canOpenWorkspaceSearch={false}
          currentPathname="/w/general/docs"
          currentUser={currentUser}
          currentWorkspace={workspace}
          currentWorkspaceName={workspace.name}
          defaultWorkspaceOptions={[workspace]}
          defaultWorkspaceSaving={false}
          draftItems={[]}
          draftPinnedAppIds={[]}
          fixedItems={[]}
          categoryMenuId={null}
          favoritesOpen={false}
          moreMenuRef={createRef()}
          normalizedDefaultWorkspaceId={null}
          notificationsEnabled={false}
          onCloseEditor={vi.fn()}
          onCloseLauncherMenus={vi.fn()}
          onCreateWorkspace={vi.fn()}
          onDefaultWorkspaceChange={vi.fn()}
          onManageCurrentWorkspace={vi.fn()}
          onMovePinnedApp={vi.fn()}
          onOpenAccount={vi.fn()}
          onOpenEditor={vi.fn()}
          onOpenHelp={vi.fn()}
          onOpenWorkspaceSearch={vi.fn()}
          onResetDraft={vi.fn()}
          onSaveLayout={vi.fn()}
          onSearchQueryChange={vi.fn()}
          onSelectWorkspace={vi.fn()}
          onToggleCategoryMenu={vi.fn()}
          onToggleFavorites={vi.fn()}
          onToggleNotifications={vi.fn()}
          onTogglePinnedApp={vi.fn()}
          onToggleWorkspaceSwitcher={vi.fn()}
          otherWorkspaces={[]}
          pinnedEligibleAppIds={new Set()}
          pinnedItems={[]}
          pinnedWorkspace={workspace}
          resolveAppLink={resolveAppLink}
          t={translate}
          unreadCount={0}
          workspaceAppBarCategories={[
            {
              id: 'collaboration',
              key: 'collaboration',
              title: '협업',
              icon_key: 'users',
              position: 0,
              items: [
                {
                  app_id: 'docs',
                  title: '문서',
                  route_base: '/docs',
                  icon_key: 'file-text',
                  enabled: true,
                },
              ],
            },
          ]}
          workspacePreferenceError={null}
          workspaceQuery=""
          workspaceSwitcherOpen={false}
          workspaceSwitcherRef={createRef()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole('button', { name: '협업 / 문서' })).toBeTruthy();
    expect(screen.queryByRole('link', { name: '앱 열기' })).toBeNull();
  });
});
