import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';

const CommunityView = lazy(() =>
  import('./views/CommunityView').then((module) => ({
    default: module.CommunityView,
  })),
);

export const communityGlobalRoutes: StaticRouteDefinition[] = [
  {
    path: '/community',
    element: lazyRoute(createElement(CommunityView)),
  },
  {
    path: '/community/posts/:postId',
    element: lazyRoute(createElement(CommunityView)),
  },
];
