import { fireEvent, render, screen } from '@testing-library/react';
import { CarFront, Cog, Fan, UserCog, Zap } from 'lucide-react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { AppSidebarRenderContext } from '@/src/app/shell/sidebar-types';
import {
  LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_NAV_ITEM_ID,
  LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_PATH_SUFFIX,
  LEGACY_ISSUE_VEHICLE_MANAGEMENT_NAV_ITEM_ID,
  LEGACY_ISSUE_VEHICLE_MANAGEMENT_PATH_SUFFIX,
  LEGACY_ISSUE_VIEWS,
} from './core/public-api';
import { legacyIssuesSidebarConfig } from './sidebar';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      key === 'categories.legacy-issues-compressor' ? '컴프레서' : key,
  }),
}));

describe('legacyIssuesSidebarConfig', () => {
  it('shows the heat exchanger module in the master section', () => {
    renderSidebar(renderContext());

    expect(screen.getByRole('link', { name: '열교환기' })).not.toBeNull();
  });

  it('groups the mechanical and electric compressor views in a collapsible section', () => {
    renderSidebar(renderContext());

    expect(screen.getByRole('link', { name: '기계' })).not.toBeNull();
    expect(screen.getByRole('link', { name: '전동' })).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '컴프레서' }));

    expect(screen.queryByRole('link', { name: '기계' })).toBeNull();
    expect(screen.queryByRole('link', { name: '전동' })).toBeNull();
  });

  it('keeps the compressor children visible while a compressor route is active', () => {
    renderSidebar(
      renderContext({
        activeNavItemId: LEGACY_ISSUE_VIEWS['compressor-electric'].navItemId,
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: '컴프레서' }));

    expect(screen.getByRole('link', { name: '기계' })).not.toBeNull();
    expect(screen.getByRole('link', { name: '전동' })).not.toBeNull();
  });

  it('shows direct edit settings only to platform administrators', () => {
    const { unmount } = renderSidebar(renderContext({ platformAdmin: true }));
    expect(
      screen.getByRole('link', { name: '모듈별 직접 수정 권한' }),
    ).not.toBeNull();
    unmount();

    renderSidebar(renderContext({ platformAdmin: false }));
    expect(
      screen.queryByRole('link', { name: '모듈별 직접 수정 권한' }),
    ).toBeNull();
  });

  it('shows vehicle management to workspace members', () => {
    renderSidebar(
      renderContext({ platformAdmin: false, workspaceRole: 'member' }),
    );

    expect(screen.getByRole('link', { name: '차종 관리' })).not.toBeNull();
  });
});

function renderSidebar(context: AppSidebarRenderContext) {
  return render(
    <MemoryRouter>
      {legacyIssuesSidebarConfig.renderCategory?.(
        'legacy-issues-root',
        context,
      )}
    </MemoryRouter>,
  );
}

function renderContext({
  activeNavItemId = '',
  platformAdmin,
  workspaceRole = 'admin',
}: {
  activeNavItemId?: string;
  platformAdmin?: boolean;
  workspaceRole?: 'admin' | 'member';
} = {}): AppSidebarRenderContext {
  return {
    activeAppId: 'legacy-issues',
    activeNavItemId,
    canReadWorkspace: true,
    currentPathname: '/w/research/legacy-issues/common-master',
    currentWorkspaceSlug: 'research',
    enabledWorkspaceAppIds: ['legacy-issues'],
    filteredItems: [
      {
        appId: 'legacy-issues',
        category: 'legacy-issues',
        icon: CarFront,
        id: LEGACY_ISSUE_VEHICLE_MANAGEMENT_NAV_ITEM_ID,
        pathSuffix: LEGACY_ISSUE_VEHICLE_MANAGEMENT_PATH_SUFFIX,
        title: '차종 관리',
      },
      {
        appId: 'legacy-issues',
        category: 'legacy-issues',
        icon: Fan,
        id: LEGACY_ISSUE_VIEWS['heat-exchanger'].navItemId,
        pathSuffix: LEGACY_ISSUE_VIEWS['heat-exchanger'].pathSuffix,
        title: '열교환기',
      },
      {
        appId: 'legacy-issues',
        category: 'legacy-issues-compressor',
        icon: Cog,
        id: LEGACY_ISSUE_VIEWS['compressor-mechanical'].navItemId,
        pathSuffix: LEGACY_ISSUE_VIEWS['compressor-mechanical'].pathSuffix,
        title: '기계',
      },
      {
        appId: 'legacy-issues',
        category: 'legacy-issues-compressor',
        icon: Zap,
        id: LEGACY_ISSUE_VIEWS['compressor-electric'].navItemId,
        pathSuffix: LEGACY_ISSUE_VIEWS['compressor-electric'].pathSuffix,
        title: '전동',
      },
      {
        appId: 'legacy-issues',
        category: 'legacy-issues',
        icon: UserCog,
        id: LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_NAV_ITEM_ID,
        pathSuffix: LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_PATH_SUFFIX,
        title: '모듈별 직접 수정 권한',
      },
    ],
    isCategoryExpanded: () => true,
    navigate: vi.fn(),
    onNavigate: vi.fn(),
    toggleCategory: vi.fn(),
    user:
      platformAdmin === undefined
        ? null
        : ({
            system_roles: platformAdmin ? ['platform_admin'] : [],
            workspaces: [{ role: workspaceRole, slug: 'research' }],
          } as AppSidebarRenderContext['user']),
  };
}
