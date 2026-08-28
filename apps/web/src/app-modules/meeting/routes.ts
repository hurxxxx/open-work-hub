import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const MeetingView = lazy(() =>
  import('./views/MeetingView/MeetingView').then((module) => ({
    default: module.MeetingView,
  })),
);
const MeetingWorkspaceView = lazy(() =>
  import('./views/MeetingView/MeetingWorkspaceView').then((module) => ({
    default: module.MeetingWorkspaceView,
  })),
);

export const meetingWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'meeting',
    chrome: getAppRouteChrome('meeting.root'),
    path: getAppRoutePattern('meeting.root'),
    element: lazyRoute(createElement(MeetingView)),
  },
  {
    appId: 'meeting',
    chrome: getAppRouteChrome('meeting.detail'),
    path: getAppRoutePattern('meeting.detail'),
    element: lazyRoute(createElement(MeetingWorkspaceView)),
  },
];
