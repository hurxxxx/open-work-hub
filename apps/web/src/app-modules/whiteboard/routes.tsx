import { lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const WhiteboardView = lazy(() =>
  import('./views/WhiteboardView').then((module) => ({ default: module.WhiteboardView })),
);

export const whiteboardToolElement = lazyRoute(<WhiteboardView />);

export const whiteboardWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'whiteboard',
    path: '/w/:workspaceSlug/whiteboard',
    element: whiteboardToolElement,
  },
  {
    appId: 'whiteboard',
    path: '/w/:workspaceSlug/whiteboard/:whiteboardId',
    element: whiteboardToolElement,
  },
];

