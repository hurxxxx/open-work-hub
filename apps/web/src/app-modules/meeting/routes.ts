import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const MeetingView = lazy(() =>
  import('./views/MeetingView/MeetingView').then((module) => ({ default: module.MeetingView })),
);
const MeetingWorkspaceView = lazy(() =>
  import('./views/MeetingView/MeetingWorkspaceView').then((module) => ({
    default: module.MeetingWorkspaceView,
  })),
);

export const meetingWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'meeting',
    path: '/w/:workspaceSlug/meeting',
    element: lazyRoute(createElement(MeetingView)),
  },
  {
    appId: 'meeting',
    path: '/w/:workspaceSlug/meeting/:meetingId',
    element: lazyRoute(createElement(MeetingWorkspaceView)),
  },
];
