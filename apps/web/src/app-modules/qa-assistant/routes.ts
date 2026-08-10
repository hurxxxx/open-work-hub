import { createElement, lazy } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from '@/src/app/shell/route-types';

const QaAssistantView = lazy(() =>
  import('./views/QaAssistantView').then((module) => ({
    default: module.QaAssistantView,
  })),
);

const qaAssistantElement = lazyRoute(createElement(QaAssistantView));

function QaAssistantWorkspaceRedirect() {
  const location = useLocation();
  return createElement(Navigate, {
    replace: true,
    to: `/qa-assistant${location.search}`,
  });
}

export const qaAssistantToolViewRoutes: ToolViewRouteDefinition[] = [
  {
    appId: 'qa-assistant',
    element: qaAssistantElement,
    id: 'qa-assistant.main',
    match: ({ toolId }) => toolId === 'qa-assistant',
    toolIds: ['qa-assistant'],
    type: 'element',
  },
];

export const qaAssistantGlobalRoutes: StaticRouteDefinition[] = [
  {
    appId: 'ai',
    bootstrapAppId: 'qa-assistant',
    chrome: 'fullSurface',
    path: '/qa-assistant',
    subSidebar: 'hidden',
    element: qaAssistantElement,
  },
];

export const qaAssistantWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'qa-assistant',
    path: '/w/:workspaceSlug/qa-assistant/*',
    subSidebar: 'hidden',
    element: createElement(QaAssistantWorkspaceRedirect),
  },
];
