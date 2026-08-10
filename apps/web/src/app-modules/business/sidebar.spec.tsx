import { describe, expect, it, vi } from 'vitest';
import { Home } from 'lucide-react';

import type { AppSidebarRenderContext } from '@/src/app/shell/sidebar-types';
import { businessSidebarConfig } from './sidebar';

describe('businessSidebarConfig', () => {
  it('keeps ordinary feature categories unchanged', () => {
    expect(
      businessSidebarConfig.extendCategories?.(['Analytics'], {
        activeFeatureAppId: 'diagrams',
        canReadWorkspace: true,
      }),
    ).toEqual(['Analytics']);

    expect(
      businessSidebarConfig.renderCategory?.(
        'docs-root',
        renderContext({ activeFeatureAppId: 'diagrams' }),
      ),
    ).toBeUndefined();
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
    currentPathname: '/w/general/diagrams',
    currentWorkspaceSlug: 'general',
    enabledWorkspaceAppIds: ['business', activeFeatureAppId],
    filteredItems: [
      {
        appId: 'business',
        category: 'Analytics',
        icon: Home,
        id: 'diagrams',
        linkAppId: 'diagrams',
        pathSuffix: '/diagrams',
        title: '데이터 시각화',
      },
    ],
    isCategoryExpanded: () => true,
    navigate: vi.fn(),
    toggleCategory: vi.fn(),
    user: null,
  };
}
