import { describe, expect, it, vi } from 'vitest';

import type { AppSidebarActionContext } from '@/src/app/shell/sidebar-types';
import { collaborationSidebarConfig } from './sidebar';

describe('collaborationSidebarConfig', () => {
  it('delegates PMS category extensions for the PMS feature', () => {
    expect(
      collaborationSidebarConfig.extendCategories?.(['Personal'], {
        activeFeatureAppId: 'pms',
        canReadWorkspace: true,
      }),
    ).toEqual(['Spaces', 'Personal']);
  });

  it('delegates feature create actions for launcher feature routes', () => {
    expect(
      collaborationSidebarConfig
        .createActions?.(actionContext({ activeFeatureAppId: 'whiteboard' }))
        .map((action) => action.id),
    ).toEqual(['whiteboard-create']);

    expect(
      collaborationSidebarConfig
        .createActions?.(actionContext({ activeFeatureAppId: 'meeting' }))
        .map((action) => action.id),
    ).toEqual(['meeting-create']);
  });
});

function actionContext({
  activeFeatureAppId,
}: {
  activeFeatureAppId: string;
}): AppSidebarActionContext {
  return {
    activeAppId: 'collaboration',
    activeFeatureAppId,
    currentPathname: `/w/general/${activeFeatureAppId}`,
    currentWorkspaceSlug: 'general',
    enabledWorkspaceAppIds: ['collaboration', activeFeatureAppId],
    navigate: vi.fn(),
    user: null,
  };
}
