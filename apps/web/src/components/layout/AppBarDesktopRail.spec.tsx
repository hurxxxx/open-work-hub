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
  name: 'AI TFT',
  role: 'member',
  slug: 'ai-tft',
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
      'shell:businessSites.description': '자주 쓰는 사내 업무 사이트를 엽니다.',
      'shell:businessSites.groupwareDescription':
        '전자결재, 게시판, 사내 업무 시스템',
      'shell:businessSites.groupwareTitle': 'Open ALM 그룹웨어',
      'shell:businessSites.open': '업무 사이트 링크',
      'shell:businessSites.title': '업무 사이트',
      'shell:businessSites.welfareMallDescription': '복지 혜택 및 상품 이용',
      'shell:businessSites.welfareMallTitle': 'Open ALM 복지몰',
      'shell:helpCenter.open': '도움말',
      'shell:notifications.title': '알림',
      'shell:search.title': '통합검색',
      'shell:workspaceSwitcher.currentTitle': 'AI TFT 워크스페이스',
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

  it('renders the business sites launcher with groupware and welfare mall links', () => {
    render(
      <AppBarDesktopRail
        activeAppId="home"
        appBarEditorOpen={false}
        appBarItems={[]}
        appBarLayoutError={null}
        appBarLayoutSaving={false}
        businessSitesMenuRef={createRef()}
        businessSitesOpen
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
        onCloseBusinessSites={vi.fn()}
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
        onToggleBusinessSites={vi.fn()}
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
        workspaceSwitcherOpen={false}
        workspaceSwitcherRef={createRef()}
      />,
    );

    expect(
      screen
        .getByRole('button', { name: '업무 사이트 링크' })
        .getAttribute('aria-expanded'),
    ).toBe('true');

    const groupwareLink = screen.getByRole('menuitem', {
      name: /Open ALM 그룹웨어/,
    });
    expect(groupwareLink.getAttribute('href')).toBe(
      'http://gw.example.com/index.aspx',
    );
    expect(groupwareLink.getAttribute('target')).toBe('_blank');
    expect(groupwareLink.getAttribute('rel')).toBe('noreferrer');

    const welfareMallLink = screen.getByRole('menuitem', {
      name: /Open ALM 복지몰/,
    });
    expect(welfareMallLink.getAttribute('href')).toBe(
      'https://open-alm.ezwel.com/pc/mypage/auth/login/pc/product/main/welfare-mall',
    );
    expect(welfareMallLink.getAttribute('target')).toBe('_blank');
    expect(welfareMallLink.getAttribute('rel')).toBe('noreferrer');
  });

  it('renders the workspace switcher popover outside the rail clipping context', () => {
    render(
      <AppBarDesktopRail
        activeAppId="home"
        appBarEditorOpen={false}
        appBarItems={[]}
        appBarLayoutError={null}
        appBarLayoutSaving={false}
        businessSitesMenuRef={createRef()}
        businessSitesOpen={false}
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
        onCloseBusinessSites={vi.fn()}
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
        onToggleBusinessSites={vi.fn()}
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
          businessSitesMenuRef={createRef()}
          businessSitesOpen={false}
          canCreateWorkspace={false}
          canManageCurrentWorkspace={false}
          canOpenWorkspaceSearch={false}
          currentPathname="/w/ai-tft/docs"
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
          onCloseBusinessSites={vi.fn()}
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
          onToggleBusinessSites={vi.fn()}
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
