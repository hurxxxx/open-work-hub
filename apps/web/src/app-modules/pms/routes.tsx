import { lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const AssignedToMeView = lazy(() =>
  import('./views/AssignedToMeView').then((module) => ({ default: module.AssignedToMeView })),
);
const PersonalListView = lazy(() =>
  import('./views/PersonalListView').then((module) => ({ default: module.PersonalListView })),
);
const PMSView = lazy(() =>
  import('./views/PMSView').then((module) => ({ default: module.PMSView })),
);
const TodayOverdueView = lazy(() =>
  import('./views/TodayOverdueView').then((module) => ({ default: module.TodayOverdueView })),
);

export const pmsToolElement = lazyRoute(<PMSView />);

export const pmsWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'pms',
    path: '/w/:workspaceSlug/pms',
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    path: '/w/:workspaceSlug/pms/assigned',
    element: lazyRoute(<AssignedToMeView />),
  },
  {
    appId: 'pms',
    path: '/w/:workspaceSlug/pms/today',
    element: lazyRoute(<TodayOverdueView />),
  },
  {
    appId: 'pms',
    path: '/w/:workspaceSlug/pms/personal',
    element: lazyRoute(<PersonalListView />),
  },
];
