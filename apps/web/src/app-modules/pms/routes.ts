import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const AssignedToMeView = lazy(() =>
  import('./views/AssignedToMeView').then((module) => ({
    default: module.AssignedToMeView,
  })),
);
const PMSView = lazy(() =>
  import('./views/PMSView').then((module) => ({ default: module.PMSView })),
);
const TodayOverdueView = lazy(() =>
  import('./views/TodayOverdueView').then((module) => ({
    default: module.TodayOverdueView,
  })),
);

export const pmsToolElement = lazyRoute(createElement(PMSView));

export const pmsWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'pms',
    chrome: getAppRouteChrome('pms.root'),
    path: getAppRoutePattern('pms.root'),
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: getAppRouteChrome('pms.assigned'),
    path: getAppRoutePattern('pms.assigned'),
    element: lazyRoute(createElement(AssignedToMeView)),
  },
  {
    appId: 'pms',
    chrome: getAppRouteChrome('pms.today'),
    path: getAppRoutePattern('pms.today'),
    element: lazyRoute(createElement(TodayOverdueView)),
  },
  {
    appId: 'pms',
    chrome: getAppRouteChrome('pms.list'),
    path: getAppRoutePattern('pms.list'),
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: getAppRouteChrome('pms.space'),
    path: getAppRoutePattern('pms.space'),
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: getAppRouteChrome('pms.space-docs'),
    path: getAppRoutePattern('pms.space-docs'),
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: getAppRouteChrome('pms.space-doc'),
    path: getAppRoutePattern('pms.space-doc'),
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: getAppRouteChrome('pms.space-whiteboards'),
    path: getAppRoutePattern('pms.space-whiteboards'),
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: getAppRouteChrome('pms.space-whiteboard'),
    path: getAppRoutePattern('pms.space-whiteboard'),
    element: pmsToolElement,
  },
];
