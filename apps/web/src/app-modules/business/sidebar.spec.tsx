import { describe, expect, it, vi } from 'vitest';
import { Home } from 'lucide-react';

import type { AppSidebarRenderContext } from '@/src/app/shell/sidebar-types';
import { businessSidebarConfig } from './sidebar';

describe('businessSidebarConfig', () => {
  it('keeps normal business feature categories outside legacy issues', () => {
    expect(
      businessSidebarConfig.extendCategories?.(['Analytics'], {
        activeFeatureAppId: 'data-viz',
        canReadWorkspace: true,
      }),
    ).toEqual(['Analytics']);

    expect(
      businessSidebarConfig.renderCategory?.(
        'legacy-issues-root',
        renderContext({ activeFeatureAppId: 'data-viz' }),
      ),
    ).toBeUndefined();
  });

  it('uses the legacy issues sidebar only for the legacy issues feature', () => {
    expect(
      businessSidebarConfig.extendCategories?.(['legacy-issues'], {
        activeFeatureAppId: 'legacy-issues',
        canReadWorkspace: true,
      }),
    ).toEqual(['legacy-issues-root']);

    expect(
      businessSidebarConfig.renderCategory?.(
        'legacy-issues-root',
        renderContext({ activeFeatureAppId: 'legacy-issues' }),
      ),
    ).not.toBeUndefined();
  });

  it('delegates learning sidebar extensions for the learning feature', () => {
    expect(
      businessSidebarConfig.afterCategories?.(
        renderContext({ activeFeatureAppId: 'learning' }),
      ),
    ).not.toBeUndefined();
  });
});

function renderContext({
  activeFeatureAppId,
}: {
  activeFeatureAppId: string;
}): AppSidebarRenderContext {
  return {
    activeAppId: 'business',
    activeFeatureAppId,
    activeNavItemId: '',
    canReadWorkspace: true,
    currentPathname: '/w/ai-tft/data-viz',
    currentWorkspaceSlug: 'ai-tft',
    enabledWorkspaceAppIds: ['business', activeFeatureAppId],
    filteredItems: [
      {
        appId: 'business',
        category: 'Analytics',
        icon: Home,
        id: 'data-viz',
        linkAppId: 'data-viz',
        pathSuffix: '/data-viz',
        title: '데이터 시각화',
      },
    ],
    isCategoryExpanded: () => true,
    navigate: vi.fn(),
    toggleCategory: vi.fn(),
    user: null,
  };
}
