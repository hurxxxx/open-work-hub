import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const RecordingView = lazy(() =>
  import('./views/RecordingView').then((module) => ({
    default: module.RecordingView,
  })),
);
const RecordingDetailView = lazy(() =>
  import('./views/RecordingDetailView').then((module) => ({
    default: module.RecordingDetailView,
  })),
);

export const recordingAppRoutes: AppRouteDefinition[] = [
  {
    appId: 'recording',
    chrome: getAppRouteChrome('recording.root'),
    path: getAppRoutePattern('recording.root'),
    element: lazyRoute(createElement(RecordingView)),
  },
  {
    appId: 'recording',
    chrome: getAppRouteChrome('recording.detail'),
    path: getAppRoutePattern('recording.detail'),
    element: lazyRoute(createElement(RecordingDetailView)),
  },
];
