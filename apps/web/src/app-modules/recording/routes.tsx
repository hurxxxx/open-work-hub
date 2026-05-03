import { lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const RecordingView = lazy(() =>
  import('./views/RecordingView').then((module) => ({ default: module.RecordingView })),
);
const RecordingDetailView = lazy(() =>
  import('./views/RecordingDetailView').then((module) => ({ default: module.RecordingDetailView })),
);

export const recordingWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'recording',
    path: '/w/:workspaceSlug/recording',
    element: lazyRoute(<RecordingView />),
  },
  {
    appId: 'recording',
    path: '/w/:workspaceSlug/recording/:recordingId',
    element: lazyRoute(<RecordingDetailView />),
  },
];
