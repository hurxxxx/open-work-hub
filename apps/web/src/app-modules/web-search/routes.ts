import { createElement, lazy } from 'react';
import { BookOpen, Scale } from 'lucide-react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const WebSearchView = lazy(() =>
  import('./views/WebSearchView').then((module) => ({
    default: module.WebSearchView,
  })),
);
const WebSearchExperienceView = lazy(() =>
  import('./views/WebSearchView').then((module) => ({
    default: module.WebSearchExperienceView,
  })),
);

const webSearchElement = lazyRoute(createElement(WebSearchView));
const researchTrendsElement = lazyRoute(
  createElement(WebSearchExperienceView, {
    experience: {
      apiPrefix: '/api/v1/research-trends',
      conversationScopeRef: 'research_trends',
      icon: BookOpen,
      i18nKey: 'ai.researchTrends',
      maxUses: 8,
    },
  }),
);
const standardsMonitorElement = lazyRoute(
  createElement(WebSearchExperienceView, {
    experience: {
      apiPrefix: '/api/v1/standards-monitor',
      conversationScopeRef: 'standards_monitor',
      icon: Scale,
      i18nKey: 'ai.standardsMonitor',
      maxUses: 8,
    },
  }),
);

export const webSearchWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'web-search',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/web-search',
    subSidebar: 'hidden',
    element: webSearchElement,
  },
];

export const researchTrendsWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'research-trends',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/research-trends',
    subSidebar: 'hidden',
    element: researchTrendsElement,
  },
];

export const standardsMonitorWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'standards-monitor',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/standards-monitor',
    subSidebar: 'hidden',
    element: standardsMonitorElement,
  },
];
