import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';

const CommunityView = lazy(() =>
  import('./views/CommunityView').then((module) => ({
    default: module.CommunityView,
  })),
);

export const communityGlobalRoutes: StaticRouteDefinition[] = [
  {
    chrome: getAppRouteChrome('community.root'),
    path: getAppRoutePattern('community.root'),
    element: lazyRoute(createElement(CommunityView)),
  },
  {
    chrome: getAppRouteChrome('community.post'),
    path: getAppRoutePattern('community.post'),
    element: lazyRoute(createElement(CommunityView)),
  },
];
