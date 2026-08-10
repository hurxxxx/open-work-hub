import { describe, expect, it } from 'vitest';

import { resolveActiveFeatureAppId } from './sub-sidebar-feature-model';

const navItems = [
  {
    appId: 'collaboration',
    id: 'pms-inbox',
    linkAppId: 'pms',
  },
  {
    appId: 'collaboration',
    id: 'docs-all',
    linkAppId: 'docs',
  },
  {
    appId: 'collaboration',
    id: 'whiteboard-all',
    linkAppId: 'whiteboard',
  },
] as const;

describe('sub sidebar feature model', () => {
  it('resolves feature apps from collaboration workspace paths', () => {
    expect(
      resolveActiveFeatureAppId({
        activeAppId: 'collaboration',
        activeNavItemId: 'pms-inbox',
        navItems,
        pathname: '/w/ai-tft/pms',
      }),
    ).toBe('pms');
  });

  it('resolves PMS feature sidebar context from PMS workspace detail routes', () => {
    expect(
      resolveActiveFeatureAppId({
        activeAppId: 'collaboration',
        activeNavItemId: 'pms-list-a5c123fe-b403-4d88-92b6-ed7ebbcf7607',
        navItems,
        pathname: '/w/ai-tft/pms/lists/a5c123fe-b403-4d88-92b6-ed7ebbcf7607',
      }),
    ).toBe('pms');
  });

  it('resolves collaboration document tool features without workspace paths', () => {
    expect(
      resolveActiveFeatureAppId({
        activeAppId: 'collaboration',
        activeNavItemId: 'docs-all',
        navItems,
        pathname: '/tool/docs-all/doc-1?workspace=ai-tft',
      }),
    ).toBe('docs');
    expect(
      resolveActiveFeatureAppId({
        activeAppId: 'collaboration',
        activeNavItemId: 'whiteboard-all',
        navItems,
        pathname: '/tool/whiteboard-all/board-1?workspace=ai-tft',
      }),
    ).toBe('whiteboard');
  });

  it('does not infer feature context for non-collaboration tool routes', () => {
    expect(
      resolveActiveFeatureAppId({
        activeAppId: 'business',
        activeNavItemId: 'pms-list-a5c123fe',
        navItems,
        pathname: '/tool/business-tool?workspace=ai-tft',
      }),
    ).toBeNull();
  });
});
