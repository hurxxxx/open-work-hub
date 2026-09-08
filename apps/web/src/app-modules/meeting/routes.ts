import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const MeetingView = lazy(() =>
  import('./views/MeetingView/MeetingView').then((module) => ({
    default: module.MeetingView,
  })),
);
const MeetingDetailView = lazy(() =>
  import('./views/MeetingView/MeetingDetailView').then((module) => ({
    default: module.MeetingDetailView,
  })),
);

export const meetingAppRoutes: AppRouteDefinition[] = [
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
    element: lazyRoute(createElement(MeetingDetailView)),
  },
];
