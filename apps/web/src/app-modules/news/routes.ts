import { createElement, lazy } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';

const NewsHubView = lazy(() =>
  import('./views/NewsHubView').then((module) => ({
    default: module.NewsHubView,
  })),
);

function LegacyNewsWorkspaceRedirect() {
  const location = useLocation();
  return createElement(Navigate, {
    replace: true,
    to: `/news${location.search}${location.hash}`,
  });
}

export const newsGlobalRoutes: StaticRouteDefinition[] = [
  {
    path: '/news',
    element: lazyRoute(createElement(NewsHubView)),
  },
  {
    path: '/w/:workspaceSlug/news',
    element: createElement(LegacyNewsWorkspaceRedirect),
  },
];
